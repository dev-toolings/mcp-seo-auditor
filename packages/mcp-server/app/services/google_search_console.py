"""Google Search Console API service."""

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters"]
INDEXING_SCOPE = "https://www.googleapis.com/auth/indexing"

google_auth = None
googleapiclient = None
google_auth_oauthlib = None


def _load_google_libs():
    """Lazy load Google libraries."""
    global google_auth, googleapiclient, google_auth_oauthlib
    if google_auth is None:
        try:
            import google_auth_oauthlib.flow as _oauthlib
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            google_auth = service_account
            googleapiclient = build
            google_auth_oauthlib = _oauthlib
            return True
        except ImportError:
            logger.warning(
                "Google API libraries not installed. Run: pip install google-auth google-api-python-client google-auth-oauthlib"
            )
            return False
    return True


@dataclass
class PerformanceData:
    """Search performance data."""

    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass
class PagePerformance:
    """Performance data for a specific page."""

    url: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass
class QueryPerformance:
    """Performance data for a search query."""

    query: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


@dataclass
class CrawlError:
    """Crawl error from Search Console."""

    url: str
    category: str
    platform: str
    last_crawled: Optional[datetime] = None
    first_detected: Optional[datetime] = None
    response_code: Optional[int] = None


@dataclass
class SitemapInfo:
    """Sitemap information from Search Console."""

    path: str
    last_submitted: Optional[datetime] = None
    last_downloaded: Optional[datetime] = None
    is_pending: bool = False
    is_sitemaps_index: bool = False
    warnings: int = 0
    errors: int = 0


class _RateLimiter:
    """Sliding-window rate limiter (per-minute)."""

    def __init__(self, rpm: int):
        self._rpm = rpm
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            window = now - 60.0
            while self._timestamps and self._timestamps[0] <= window:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._rpm:
                sleep_for = self._timestamps[0] - window
                logger.debug("GSC rate limit: sleeping %.1fs", sleep_for)
                await asyncio.sleep(sleep_for)
                now = time.monotonic()
                window = now - 60.0
                while self._timestamps and self._timestamps[0] <= window:
                    self._timestamps.popleft()
            self._timestamps.append(time.monotonic())


class GoogleSearchConsoleService:
    """Service to interact with Google Search Console API."""

    def __init__(self, credentials_path: Optional[str] = None):
        self.credentials_path = credentials_path or settings.GOOGLE_CREDENTIALS_PATH
        self.oauth_client_secrets = os.environ.get("GSC_OAUTH_CLIENT_SECRETS_FILE")
        self.oauth_token_file = os.environ.get("GSC_OAUTH_TOKEN_FILE", "token.json")
        self.skip_oauth = os.environ.get("GSC_SKIP_OAUTH", "").lower() in ("true", "1", "yes")
        self._service = None
        self._indexing_service = None
        self._rate_limiter = _RateLimiter(settings.GSC_REQUESTS_PER_MINUTE)
        self._inspection_limiter = _RateLimiter(settings.GSC_INSPECTION_RPM)

    @property
    def is_credentials_available(self) -> bool:
        """Check if GSC credentials are configured (auto-detect)."""
        if not _load_google_libs():
            return False
        if self.skip_oauth:
            return bool(self.credentials_path)
        if self.oauth_client_secrets and os.path.exists(self.oauth_client_secrets):
            return True
        return bool(self.credentials_path)

    def _get_service(self):
        """Get or create the Search Console service with OAuth or service account."""
        if self._service is not None:
            return self._service

        if not _load_google_libs():
            raise RuntimeError("Google API libraries not available")

        credentials = None

        if not self.skip_oauth:
            try:
                credentials = self._get_oauth_credentials()
            except Exception as e:
                logger.warning(f"OAuth failed, trying service account: {e}")

        if not credentials and self.credentials_path:
            try:
                credentials = google_auth.Credentials.from_service_account_file(
                    self.credentials_path,
                    scopes=SCOPES,
                )
            except Exception as e:
                logger.error(f"Service account auth failed: {e}")
                raise RuntimeError(f"Failed to authenticate: {e}")

        if not credentials:
            raise RuntimeError(
                "No valid credentials found. Set GSC_CREDENTIALS_PATH or GSC_OAUTH_CLIENT_SECRETS_FILE"
            )

        try:
            self._service = googleapiclient(
                "searchconsole",
                "v1",
                credentials=credentials,
                cache_discovery=False,
            )
            return self._service
        except Exception as e:
            logger.error(f"Failed to initialize Google Search Console: {e}")
            raise

    def _get_oauth_credentials(self):
        """Get OAuth credentials, handling token refresh and flow."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as OAuthCredentials

        if not self.oauth_client_secrets or not os.path.exists(self.oauth_client_secrets):
            return None

        creds = None
        token_path = os.path.join(os.getcwd(), self.oauth_token_file)

        if os.path.exists(token_path):
            try:
                creds = OAuthCredentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                os.remove(token_path)
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_path, "w") as f:
                        f.write(creds.to_json())
                    return creds
                except Exception:
                    os.remove(token_path)

            flow = google_auth_oauthlib.InstalledAppFlow.from_client_secrets_file(
                self.oauth_client_secrets, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(token_path, "w") as f:
                f.write(creds.to_json())

        return creds

    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _execute_with_retry(request):
        """Execute a Google API request with retry on transient errors."""
        return request.execute()

    async def list_sites(self) -> list[dict[str, Any]]:
        """List all GSC properties accessible to the service account."""
        await self._rate_limiter.acquire()
        service = self._get_service()
        request = service.sites().list()
        response = self._execute_with_retry(request)
        sites = []
        for site in response.get("siteEntry", []):
            sites.append(
                {
                    "site_url": site.get("siteUrl", ""),
                    "permission_level": site.get("permissionLevel", ""),
                }
            )
        return sites

    @staticmethod
    def _normalize_row(row: dict) -> dict:
        """Normalize a GSC row: CTR to percentage, position to 1 decimal."""
        return {
            **row,
            "ctr": round(row.get("ctr", 0) * 100, 2),
            "position": round(row.get("position", 0), 1),
        }

    async def get_performance(
        self,
        days: int = 28,
        dimensions: Optional[list[str]] = None,
        site_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Get search performance data.

        Args:
            days: Number of days to look back (max 16 months)
            dimensions: List of dimensions (query, page, country, device, date)
            site_url: GSC property URL (overrides default)
        """
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured or site_url missing"}

        await self._rate_limiter.acquire()
        service = self._get_service()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        request_body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": dimensions or [],
            "rowLimit": 1000,
        }

        try:
            request = service.searchanalytics().query(
                siteUrl=site_url,
                body=request_body,
            )
            response = self._execute_with_retry(request)
            rows = [self._normalize_row(r) for r in response.get("rows", [])]

            result = {
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "rows": rows,
                "response_aggregation_type": response.get("responseAggregationType"),
            }

            if not (dimensions or []):
                trend_body = {
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["date"],
                    "rowLimit": 1000,
                }
                try:
                    await self._rate_limiter.acquire()
                    trend_req = service.searchanalytics().query(siteUrl=site_url, body=trend_body)
                    trend_resp = self._execute_with_retry(trend_req)
                    trend_rows = trend_resp.get("rows", [])
                    trend_rows.sort(key=lambda r: r.get("keys", [""])[0])
                    result["daily_trend"] = [
                        {
                            "date": r["keys"][0],
                            "clicks": r.get("clicks", 0),
                            "impressions": r.get("impressions", 0),
                            "ctr": round(r.get("ctr", 0) * 100, 2),
                            "position": round(r.get("position", 0), 1),
                        }
                        for r in trend_rows
                    ]
                except Exception as e:
                    logger.warning(f"GSC daily trend query failed: {e}")

            return result
        except Exception as e:
            logger.error(f"GSC performance query failed: {e}")
            return {"error": str(e)}

    async def get_top_pages(
        self,
        days: int = 28,
        limit: int = 100,
        site_url: Optional[str] = None,
    ) -> list[PagePerformance]:
        """Get top performing pages."""
        result = await self.get_performance(days=days, dimensions=["page"], site_url=site_url)

        if "error" in result:
            return []

        pages = []
        for row in result.get("rows", [])[:limit]:
            pages.append(
                PagePerformance(
                    url=row["keys"][0],
                    clicks=row.get("clicks", 0),
                    impressions=row.get("impressions", 0),
                    ctr=row.get("ctr", 0.0),
                    position=row.get("position", 0.0),
                )
            )

        return pages

    async def get_top_queries(
        self,
        days: int = 28,
        limit: int = 100,
        site_url: Optional[str] = None,
    ) -> list[QueryPerformance]:
        """Get top search queries."""
        result = await self.get_performance(days=days, dimensions=["query"], site_url=site_url)

        if "error" in result:
            return []

        queries = []
        for row in result.get("rows", [])[:limit]:
            queries.append(
                QueryPerformance(
                    query=row["keys"][0],
                    clicks=row.get("clicks", 0),
                    impressions=row.get("impressions", 0),
                    ctr=row.get("ctr", 0.0),
                    position=row.get("position", 0.0),
                )
            )

        return queries

    async def get_page_queries(
        self,
        page_url: str,
        days: int = 28,
        limit: int = 50,
        site_url: Optional[str] = None,
    ) -> list[QueryPerformance]:
        """Get queries for a specific page."""
        if not self.is_credentials_available or not site_url:
            return []

        await self._rate_limiter.acquire()
        service = self._get_service()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        request_body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["query"],
            "dimensionFilterGroups": [
                {
                    "filters": [
                        {
                            "dimension": "page",
                            "operator": "equals",
                            "expression": page_url,
                        }
                    ]
                }
            ],
            "rowLimit": limit,
        }

        try:
            request = service.searchanalytics().query(
                siteUrl=site_url,
                body=request_body,
            )
            response = self._execute_with_retry(request)

            queries = []
            for row in response.get("rows", []):
                queries.append(
                    QueryPerformance(
                        query=row["keys"][0],
                        clicks=row.get("clicks", 0),
                        impressions=row.get("impressions", 0),
                        ctr=round(row.get("ctr", 0.0) * 100, 2),
                        position=round(row.get("position", 0.0), 1),
                    )
                )
            return queries

        except Exception as e:
            logger.error(f"GSC page queries failed: {e}")
            return []

    async def get_sitemaps(self, site_url: Optional[str] = None) -> list[SitemapInfo]:
        """Get list of submitted sitemaps."""
        if not self.is_credentials_available or not site_url:
            return []

        await self._rate_limiter.acquire()
        service = self._get_service()

        try:
            request = service.sitemaps().list(siteUrl=site_url)
            response = self._execute_with_retry(request)

            sitemaps = []
            for sitemap in response.get("sitemap", []):
                sitemaps.append(
                    SitemapInfo(
                        path=sitemap.get("path", ""),
                        last_submitted=self._parse_datetime(sitemap.get("lastSubmitted")),
                        last_downloaded=self._parse_datetime(sitemap.get("lastDownloaded")),
                        is_pending=sitemap.get("isPending", False),
                        is_sitemaps_index=sitemap.get("isSitemapsIndex", False),
                        warnings=sitemap.get("warnings", 0),
                        errors=sitemap.get("errors", 0),
                    )
                )
            return sitemaps

        except Exception as e:
            logger.error(f"GSC sitemaps query failed: {e}")
            return []

    async def get_indexing_status(self, site_url: Optional[str] = None) -> dict[str, Any]:
        """Get URL inspection / indexing status summary."""
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        service = self._get_service()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=28)

        try:
            # Get total pages with impressions (indexed and appearing in search)
            request = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["page"],
                    "rowLimit": 25000,
                },
            )
            response = self._execute_with_retry(request)

            rows = response.get("rows", [])
            total_pages = len(rows)
            total_clicks = sum(r.get("clicks", 0) for r in rows)
            total_impressions = sum(r.get("impressions", 0) for r in rows)

            return {
                "indexed_pages_with_impressions": total_pages,
                "total_clicks_28d": total_clicks,
                "total_impressions_28d": total_impressions,
                "average_ctr": total_clicks / total_impressions if total_impressions > 0 else 0,
            }

        except Exception as e:
            logger.error(f"GSC indexing status failed: {e}")
            return {"error": str(e)}

    async def find_cannibalization_from_gsc(
        self,
        min_impressions: int = 100,
        site_url: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Find keyword cannibalization using real GSC data.

        Looks for queries where multiple pages rank.
        """
        if not self.is_credentials_available or not site_url:
            return []

        await self._rate_limiter.acquire()
        service = self._get_service()

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=28)

        try:
            # Get query + page data
            request = service.searchanalytics().query(
                siteUrl=site_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["query", "page"],
                    "rowLimit": 10000,
                },
            )
            response = self._execute_with_retry(request)

            # Group by query
            query_pages: dict[str, list[dict]] = {}
            for row in response.get("rows", []):
                query = row["keys"][0]
                page = row["keys"][1]

                if query not in query_pages:
                    query_pages[query] = []

                query_pages[query].append(
                    {
                        "page": page,
                        "clicks": row.get("clicks", 0),
                        "impressions": row.get("impressions", 0),
                        "position": row.get("position", 0),
                    }
                )

            # Find cannibalization (multiple pages for same query)
            cannibalization = []
            for query, pages in query_pages.items():
                if len(pages) < 2:
                    continue

                total_impressions = sum(p["impressions"] for p in pages)
                if total_impressions < min_impressions:
                    continue

                # Sort by position (lower = better)
                pages_sorted = sorted(pages, key=lambda x: x["position"])

                cannibalization.append(
                    {
                        "query": query,
                        "pages": pages_sorted,
                        "total_impressions": total_impressions,
                        "total_clicks": sum(p["clicks"] for p in pages),
                        "recommendation": f"Consolider vers {pages_sorted[0]['page']} (position {pages_sorted[0]['position']:.1f})",
                    }
                )

            # Sort by impressions (most impactful first)
            cannibalization.sort(key=lambda x: x["total_impressions"], reverse=True)

            return cannibalization[:50]  # Top 50

        except Exception as e:
            logger.error(f"GSC cannibalization analysis failed: {e}")
            return []

    async def add_site(self, site_url: str) -> dict[str, Any]:
        """Add a site to GSC properties."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured", "success": False}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            response = service.sites().add(siteUrl=site_url).execute()
            permission = response.get("permissionLevel") if isinstance(response, dict) else None
            return {
                "success": True,
                "site_url": site_url,
                "permission_level": permission,
            }
        except Exception as e:
            error_msg = str(e)
            if "409" in error_msg:
                return {"success": False, "error": f"Site {site_url} already exists in GSC"}
            return {"success": False, "error": error_msg}

    async def delete_site(self, site_url: str) -> dict[str, Any]:
        """Remove a site from GSC properties."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured", "success": False}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            service.sites().delete(siteUrl=site_url).execute()
            return {"success": True, "site_url": site_url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_site_details(self, site_url: str) -> dict[str, Any]:
        """Get detailed information about a GSC property."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            site_info = service.sites().get(siteUrl=site_url).execute()
            return {
                "site_url": site_url,
                "permission_level": site_info.get("permissionLevel"),
                "verification_state": site_info.get("siteVerificationInfo", {}).get(
                    "verificationState"
                ),
                "verified_user": site_info.get("siteVerificationInfo", {}).get("verifiedUser"),
            }
        except Exception as e:
            return {"error": str(e)}

    async def submit_sitemap(self, site_url: str, sitemap_url: str) -> dict[str, Any]:
        """Submit a sitemap to GSC."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured", "success": False}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            service.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
            return {"success": True, "sitemap_url": sitemap_url, "site_url": site_url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_sitemap_details(self, site_url: str, sitemap_url: str) -> dict[str, Any]:
        """Get details about a specific sitemap."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            response = service.sitemaps().get(siteUrl=site_url, feedpath=sitemap_url).execute()
            return {
                "path": response.get("path"),
                "type": response.get("type"),
                "errors": response.get("errors", 0),
                "warnings": response.get("warnings", 0),
                "last_submitted": response.get("lastSubmitted"),
                "last_downloaded": response.get("lastDownloaded"),
                "is_pending": response.get("isPending", False),
            }
        except Exception as e:
            return {"error": str(e)}

    def _get_indexing_service(self):
        """Build the Indexing API (v3) client.

        The Indexing API requires a service account key (not OAuth) and the
        service account must be an Owner of the GSC property. The SA can mint
        the indexing scope from its own key, so no consent screen is involved.
        """
        if self._indexing_service is not None:
            return self._indexing_service

        if not _load_google_libs():
            raise RuntimeError("Google API libraries not available")

        if not self.credentials_path or not os.path.exists(self.credentials_path):
            raise RuntimeError(
                "Indexing API requires a service account key (GOOGLE_CREDENTIALS_PATH). "
                "The service account must also be an Owner of the GSC property."
            )

        credentials = google_auth.Credentials.from_service_account_file(
            self.credentials_path, scopes=[INDEXING_SCOPE]
        )
        self._indexing_service = googleapiclient(
            "indexing", "v3", credentials=credentials, cache_discovery=False
        )
        return self._indexing_service

    async def notify_index_update(self, url: str, type_: str = "URL_UPDATED") -> dict[str, Any]:
        """Notify Google (Indexing API) that a URL was updated or deleted.

        type_: 'URL_UPDATED' (page created/changed) or 'URL_DELETED'.
        NOTE: Google officially honours the Indexing API only for JobPosting and
        BroadcastEvent pages; for other page types the notification may be
        ignored. Daily quota: 200 URLs.
        """
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured", "success": False}
        if type_ not in ("URL_UPDATED", "URL_DELETED"):
            return {
                "success": False,
                "url": url,
                "error": "type must be URL_UPDATED or URL_DELETED",
            }

        await self._rate_limiter.acquire()
        try:
            service = self._get_indexing_service()
            response = self._execute_with_retry(
                service.urlNotifications().publish(body={"url": url, "type": type_})
            )
            latest = response.get("urlNotificationMetadata", {}).get("latestUpdate", {})
            return {
                "success": True,
                "url": url,
                "type": type_,
                "notify_time": latest.get("notifyTime"),
            }
        except Exception as e:
            return {"success": False, "url": url, "type": type_, "error": str(e)}

    async def get_index_notification_status(self, url: str) -> dict[str, Any]:
        """Return the latest update/remove notification Google recorded for a URL."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        try:
            service = self._get_indexing_service()
            response = self._execute_with_retry(service.urlNotifications().getMetadata(url=url))
            return {
                "url": response.get("url", url),
                "latest_update": response.get("latestUpdate"),
                "latest_remove": response.get("latestRemove"),
            }
        except Exception as e:
            return {"error": str(e), "url": url}

    async def inspect_url(self, site_url: str, page_url: str) -> dict[str, Any]:
        """Inspect a URL for indexing status and rich results."""
        if not self.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        await self._inspection_limiter.acquire()
        service = self._get_service()
        try:
            request = {
                "inspectionUrl": page_url,
                "siteUrl": site_url,
            }
            response = service.urlInspection().index().inspect(body=request).execute()
            inspection = response.get("inspectionResult", {})
            index_status = inspection.get("indexStatusResult", {})

            result = {
                "url": page_url,
                "verdict": index_status.get("verdict"),
                "coverage_state": index_status.get("coverageState"),
                "last_crawl": index_status.get("lastCrawlTime"),
                "page_fetch": index_status.get("pageFetchState"),
                "robots_txt": index_status.get("robotsTxtState"),
                "indexing_state": index_status.get("indexingState"),
                "google_canonical": index_status.get("googleCanonical"),
                "user_canonical": index_status.get("userCanonical"),
            }

            rich = inspection.get("richResultsResult", {})
            if rich.get("detectedItems"):
                result["rich_results"] = [
                    {"type": item.get("richResultType"), "count": len(item.get("items", []))}
                    for item in rich["detectedItems"]
                ]

            return result
        except Exception as e:
            return {"error": str(e)}

    async def batch_url_inspection(self, site_url: str, urls: list[str]) -> list[dict[str, Any]]:
        """Inspect multiple URLs in batch."""
        if not self.is_credentials_available:
            return [{"error": "Google Search Console not configured"}]

        service = self._get_service()
        results = []

        for page_url in urls[:10]:
            try:
                await self._inspection_limiter.acquire()
                request = {"inspectionUrl": page_url, "siteUrl": site_url}
                response = service.urlInspection().index().inspect(body=request).execute()
                inspection = response.get("inspectionResult", {})
                index_status = inspection.get("indexStatusResult", {})

                results.append(
                    {
                        "url": page_url,
                        "verdict": index_status.get("verdict"),
                        "coverage": index_status.get("coverageState"),
                        "last_crawl": index_status.get("lastCrawlTime"),
                    }
                )
            except Exception as e:
                results.append({"url": page_url, "error": str(e)})

        return results

    async def compare_periods(
        self,
        site_url: str,
        period1_start: str,
        period1_end: str,
        period2_start: str,
        period2_end: str,
        dimensions: Optional[list[str]] = None,
        limit: int = 20,
        row_limit: int = 1000,
    ) -> dict[str, Any]:
        """Compare search performance between two periods."""
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured or site_url missing"}

        dimensions = dimensions or ["query"]
        await self._rate_limiter.acquire()
        service = self._get_service()

        def fetch_period(start: str, end: str):
            request_body = {
                "startDate": start,
                "endDate": end,
                "dimensions": dimensions,
                "rowLimit": min(row_limit, 25000),
            }
            response = (
                service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
            )
            return {tuple(row.get("keys", [])): row for row in response.get("rows", [])}

        p1_data = fetch_period(period1_start, period1_end)
        await self._rate_limiter.acquire()
        p2_data = fetch_period(period2_start, period2_end)

        all_keys = set(p1_data.keys()) | set(p2_data.keys())
        comparisons = []

        for keys in all_keys:
            p1 = p1_data.get(keys, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0})
            p2 = p2_data.get(keys, {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0})

            p1_clicks = p1.get("clicks", 0)
            p2_clicks = p2.get("clicks", 0)
            p1_imp = p1.get("impressions", 0)
            p2_imp = p2.get("impressions", 0)
            p1_ctr = round(p1.get("ctr", 0) * 100, 2)
            p2_ctr = round(p2.get("ctr", 0) * 100, 2)
            p1_pos = round(p1.get("position", 0), 1)
            p2_pos = round(p2.get("position", 0), 1)

            click_diff = p2_clicks - p1_clicks
            imp_diff = p2_imp - p1_imp

            comparisons.append(
                {
                    "keys": list(keys),
                    "p1_clicks": p1_clicks,
                    "p2_clicks": p2_clicks,
                    "click_diff": click_diff,
                    "click_pct": round(click_diff / p1_clicks * 100, 1) if p1_clicks > 0 else None,
                    "p1_impressions": p1_imp,
                    "p2_impressions": p2_imp,
                    "imp_diff": imp_diff,
                    "imp_pct": round(imp_diff / p1_imp * 100, 1) if p1_imp > 0 else None,
                    "p1_ctr": p1_ctr,
                    "p2_ctr": p2_ctr,
                    "ctr_diff": round(p2_ctr - p1_ctr, 2),
                    "p1_position": p1_pos,
                    "p2_position": p2_pos,
                    "position_diff": round(p1_pos - p2_pos, 1),
                }
            )

        comparisons.sort(key=lambda x: abs(x["click_diff"]), reverse=True)
        return {
            "site_url": site_url,
            "period1": {"start": period1_start, "end": period1_end},
            "period2": {"start": period2_start, "end": period2_end},
            "dimensions": dimensions,
            "total_items": len(comparisons),
            "showing": min(limit, len(comparisons)),
            "comparisons": comparisons[:limit],
        }

    async def list_sitemaps_enhanced(
        self, site_url: str, sitemap_index: Optional[str] = None
    ) -> dict[str, Any]:
        """List all sitemaps with detailed information."""
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        service = self._get_service()
        try:
            if sitemap_index:
                response = (
                    service.sitemaps().list(siteUrl=site_url, sitemapIndex=sitemap_index).execute()
                )
            else:
                response = service.sitemaps().list(siteUrl=site_url).execute()

            sitemaps = response.get("sitemap", [])
            if not sitemaps:
                return {"sitemaps": [], "count": 0}

            results = []
            for sm in sitemaps:
                results.append(
                    {
                        "path": sm.get("path"),
                        "type": sm.get("type"),
                        "is_sitemaps_index": sm.get("isSitemapsIndex", False),
                        "errors": sm.get("errors", 0),
                        "warnings": sm.get("warnings", 0),
                        "last_submitted": sm.get("lastSubmitted"),
                        "last_downloaded": sm.get("lastDownloaded"),
                        "is_pending": sm.get("isPending", False),
                        "urls_submitted": sm.get("contents", [{}])[0].get("submitted", 0)
                        if sm.get("contents")
                        else 0,
                    }
                )

            return {"sitemaps": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    async def get_search_by_page_query(
        self,
        site_url: str,
        page_url: str,
        days: int = 28,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get search queries driving traffic to a specific page."""
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured"}

        await self._rate_limiter.acquire()
        service = self._get_service()
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        try:
            request_body = {
                "startDate": start_date.isoformat(),
                "endDate": end_date.isoformat(),
                "dimensions": ["query"],
                "dimensionFilterGroups": [
                    {
                        "filters": [
                            {
                                "dimension": "page",
                                "operator": "equals",
                                "expression": page_url,
                            }
                        ]
                    }
                ],
                "rowLimit": limit,
                "orderBy": [{"metric": "CLICK_COUNT", "direction": "descending"}],
            }

            response = (
                service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
            )
            rows = response.get("rows", [])

            queries = []
            for row in rows:
                queries.append(
                    {
                        "query": row["keys"][0],
                        "clicks": row.get("clicks", 0),
                        "impressions": row.get("impressions", 0),
                        "ctr": round(row.get("ctr", 0) * 100, 2),
                        "position": round(row.get("position", 0), 1),
                    }
                )

            total_clicks = sum(q["clicks"] for q in queries)
            total_impressions = sum(q["impressions"] for q in queries)
            avg_ctr = (
                round(total_clicks / total_impressions * 100, 2) if total_impressions > 0 else 0
            )

            return {
                "page_url": page_url,
                "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
                "queries": queries,
                "count": len(queries),
                "total_clicks": total_clicks,
                "total_impressions": total_impressions,
                "average_ctr": avg_ctr,
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_advanced_search_analytics(
        self,
        site_url: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        dimensions: Optional[list[str]] = None,
        search_type: str = "WEB",
        row_limit: int = 1000,
        start_row: int = 0,
        sort_by: str = "clicks",
        sort_direction: str = "descending",
        filter_dimension: Optional[str] = None,
        filter_operator: Optional[str] = None,
        filter_expression: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get advanced search analytics with filtering, sorting, and pagination."""
        if not self.is_credentials_available or not site_url:
            return {"error": "Google Search Console not configured"}

        dimensions = dimensions or ["query"]
        await self._rate_limiter.acquire()
        service = self._get_service()

        if not end_date:
            end_date = datetime.now().date().isoformat()
        if not start_date:
            start_date = (datetime.now().date() - timedelta(days=28)).isoformat()

        metric_map = {
            "clicks": "CLICK_COUNT",
            "impressions": "IMPRESSION_COUNT",
            "ctr": "CTR",
            "position": "POSITION",
        }

        request_body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": min(row_limit, 25000),
            "startRow": start_row,
            "searchType": search_type.upper(),
        }

        if sort_by in metric_map:
            request_body["orderBy"] = [
                {
                    "metric": metric_map[sort_by],
                    "direction": sort_direction.lower(),
                }
            ]

        if filter_dimension and filter_expression:
            request_body["dimensionFilterGroups"] = [
                {
                    "filters": [
                        {
                            "dimension": filter_dimension,
                            "operator": filter_operator or "contains",
                            "expression": filter_expression,
                        }
                    ]
                }
            ]

        try:
            response = (
                service.searchanalytics().query(siteUrl=site_url, body=request_body).execute()
            )
            rows = response.get("rows", [])
            effective_limit = min(row_limit, 25000)

            results = []
            for row in rows:
                entry = {"keys": row.get("keys", [])}
                entry.update(
                    {
                        "clicks": row.get("clicks", 0),
                        "impressions": row.get("impressions", 0),
                        "ctr": round(row.get("ctr", 0) * 100, 2),
                        "position": round(row.get("position", 0), 1),
                    }
                )
                results.append(entry)

            has_more = len(rows) == effective_limit
            result = {
                "site_url": site_url,
                "period": {"start": start_date, "end": end_date},
                "search_type": search_type,
                "dimensions": dimensions,
                "rows": results,
                "count": len(results),
                "response_aggregation_type": response.get("responseAggregationType"),
                "pagination": {
                    "start_row": start_row,
                    "row_count": len(results),
                    "has_more": has_more,
                },
            }
            if has_more:
                result["pagination"]["next_start_row"] = start_row + len(results)
            return result
        except Exception as e:
            return {"error": str(e)}

    async def inspect_url_cached(self, site_url: str, page_url: str, repo) -> dict:
        """Cache-aware URL inspection. Checks cache first, calls API on miss."""
        cached = await repo.get_cached_inspection(site_url, page_url)
        if cached:
            cached["_from_cache"] = True
            return cached

        result = await self.inspect_url(site_url, page_url)
        await repo.cache_inspection(site_url, page_url, result)
        await repo.increment_quota(site_url)
        result["_from_cache"] = False
        return result

    async def batch_inspect_cached(
        self,
        site_url: str,
        urls: list[str],
        repo,
        max_api_calls: int | None = None,
    ) -> dict:
        """Batch inspection with cache. Respects quota."""
        cached = await repo.get_cached_inspections_batch(site_url, urls)
        uncached_urls = [u for u in urls if u not in cached]

        results = {url: {**data, "_from_cache": True} for url, data in cached.items()}

        if uncached_urls:
            quota_used = await repo.get_quota_usage(site_url)
            remaining_quota = 2000 - quota_used

            if max_api_calls is not None:
                limit = min(len(uncached_urls), max_api_calls, remaining_quota)
            else:
                limit = min(len(uncached_urls), remaining_quota)

            to_inspect = uncached_urls[:limit]
            skipped = uncached_urls[limit:]

            for url in to_inspect:
                try:
                    result = await self.inspect_url(site_url, url)
                    await repo.cache_inspection(site_url, url, result)
                    await repo.increment_quota(site_url)
                    result["_from_cache"] = False
                    results[url] = result
                except Exception as e:
                    results[url] = {"error": str(e), "_from_cache": False}

            if skipped:
                for url in skipped:
                    results[url] = {"_skipped": True, "reason": "quota_limit"}

        quota_used = await repo.get_quota_usage(site_url)
        return {
            "results": results,
            "stats": {
                "total": len(urls),
                "from_cache": sum(1 for r in results.values() if r.get("_from_cache")),
                "from_api": sum(
                    1
                    for r in results.values()
                    if not r.get("_from_cache") and not r.get("_skipped")
                ),
                "skipped": sum(1 for r in results.values() if r.get("_skipped")),
                "errors": sum(1 for r in results.values() if "error" in r),
            },
            "quota": {
                "used": quota_used,
                "limit": 2000,
                "remaining": 2000 - quota_used,
            },
        }

    def _parse_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime from GSC response."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
