"""Sitemap XML parser service."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx
from lxml import etree

from app.core.config import settings
from app.core.exceptions import SitemapFetchError, SitemapParseError
from app.core.safe_http import safe_get
from app.core.security import validate_url

logger = logging.getLogger(__name__)

# XML namespaces for sitemap parsing
SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "xhtml": "http://www.w3.org/1999/xhtml",
}

# How many levels of nested sitemap indexes we follow below the root sitemap.
MAX_SITEMAP_DEPTH = 3


@dataclass
class SitemapUrl:
    """A single URL entry from sitemap."""

    loc: str
    lastmod: Optional[datetime] = None
    changefreq: Optional[str] = None
    priority: Optional[float] = None
    alternates: dict[str, str] = field(default_factory=dict)  # lang -> url


@dataclass
class SitemapData:
    """Parsed sitemap data."""

    urls: list[SitemapUrl] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)  # For sitemap index
    is_index: bool = False
    # Non-fatal problems met while resolving a sitemap index (depth limit hit,
    # circular reference, unreachable child). Non-empty means the URL list is
    # INCOMPLETE — callers must not report the crawl as exhaustive.
    warnings: list[str] = field(default_factory=list)


class SitemapParserService:
    """Service to fetch and parse XML sitemaps."""

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or settings.CRAWLER_TIMEOUT
        self.user_agent = settings.CRAWLER_USER_AGENT

    async def fetch_and_parse(
        self,
        url: str,
        fetch_children: bool = True,
        max_depth: int = MAX_SITEMAP_DEPTH,
    ) -> SitemapData:
        """Fetch sitemap from URL and parse it.

        Args:
            url: The sitemap URL to fetch.
            fetch_children: If True, automatically fetch child sitemaps for sitemap index.
                           Set to False to get just the index structure.
            max_depth: How many levels of nested indexes to follow below the root.

        Returns:
            SitemapData with all URLs (recursively fetched if it's an index and fetch_children=True).
            ``warnings`` is non-empty when the URL list is incomplete (depth limit,
            circular reference or unreachable child sitemap).
        """
        logger.info(f"Fetching sitemap: {url}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                data = self.parse_xml(await self._fetch(client, url))

                # If this is a sitemap index and fetch_children is True, resolve it recursively
                if data.is_index and fetch_children:
                    logger.info(
                        f"Sitemap index detected with {len(data.sitemaps)} child sitemaps, fetching all..."
                    )
                    all_urls, warnings = await self._resolve_index(
                        client,
                        data.sitemaps,
                        seen={url},
                        depth=1,
                        max_depth=max_depth,
                    )

                    # Replace the sitemap list with the actual URLs
                    data.urls = all_urls
                    data.warnings.extend(warnings)
                    data.is_index = False  # Mark as resolved
                    logger.info(
                        f"Total URLs from all sitemaps: {len(all_urls)} "
                        f"({len(warnings)} warning(s))"
                    )

                return data

        except httpx.HTTPStatusError as e:
            raise SitemapFetchError(url, f"HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            raise SitemapFetchError(url, str(e))

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> bytes:
        """GET a sitemap URL and return its raw body."""
        response = await safe_get(
            client,
            url,
            headers={"User-Agent": self.user_agent},
        )
        response.raise_for_status()
        return response.content

    async def _resolve_index(
        self,
        client: httpx.AsyncClient,
        sitemap_urls: list[str],
        seen: set[str],
        depth: int,
        max_depth: int,
    ) -> tuple[list[SitemapUrl], list[str]]:
        """Recursively resolve a sitemap index into its URLs.

        A child that is itself an index is followed until ``max_depth``. Anything
        skipped (loop, depth limit, fetch failure) is reported as a warning instead
        of being silently dropped — a partial crawl must never look complete.
        """
        urls: list[SitemapUrl] = []
        warnings: list[str] = []

        for sitemap_url in sitemap_urls:
            try:
                sitemap_url = validate_url(sitemap_url)
            except Exception as e:
                warnings.append(f"Blocked unsafe child sitemap {sitemap_url}: {e}")
                continue
            if sitemap_url in seen:
                msg = f"Circular or duplicate sitemap reference, already visited: {sitemap_url}"
                logger.warning(msg)
                warnings.append(msg)
                continue
            seen.add(sitemap_url)

            try:
                logger.info(f"Fetching child sitemap (depth {depth}): {sitemap_url}")
                child_data = self.parse_xml(await self._fetch(client, sitemap_url))
            except Exception as e:
                msg = f"Failed to fetch child sitemap {sitemap_url}: {e}"
                logger.warning(msg)
                warnings.append(msg)
                continue

            if not child_data.is_index:
                urls.extend(child_data.urls)
                continue

            if depth >= max_depth:
                msg = (
                    f"Sitemap nesting depth limit ({max_depth}) reached at {sitemap_url}: "
                    f"{len(child_data.sitemaps)} nested sitemap(s) were NOT fetched — "
                    "the URL list is incomplete"
                )
                logger.warning(msg)
                warnings.append(msg)
                continue

            child_urls, child_warnings = await self._resolve_index(
                client,
                child_data.sitemaps,
                seen=seen,
                depth=depth + 1,
                max_depth=max_depth,
            )
            urls.extend(child_urls)
            warnings.extend(child_warnings)

        return urls, warnings

    def parse_xml(self, xml_content: bytes) -> SitemapData:
        """Parse sitemap XML content."""
        try:
            root = etree.fromstring(xml_content)
        except etree.XMLSyntaxError as e:
            raise SitemapParseError(str(e))

        # Detect if this is a sitemap index or regular sitemap
        root_tag = etree.QName(root.tag).localname

        if root_tag == "sitemapindex":
            return self._parse_sitemap_index(root)
        elif root_tag == "urlset":
            return self._parse_urlset(root)
        else:
            raise SitemapParseError(f"Unknown root element: {root_tag}")

    def _parse_sitemap_index(self, root: etree._Element) -> SitemapData:
        """Parse a sitemap index file."""
        data = SitemapData(is_index=True)

        for sitemap in root.findall("sm:sitemap", SITEMAP_NS):
            loc = sitemap.find("sm:loc", SITEMAP_NS)
            if loc is not None and loc.text:
                data.sitemaps.append(loc.text.strip())

        logger.info(f"Parsed sitemap index with {len(data.sitemaps)} sitemaps")
        return data

    def _parse_urlset(self, root: etree._Element) -> SitemapData:
        """Parse a regular sitemap with URLs."""
        data = SitemapData()

        for url_elem in root.findall("sm:url", SITEMAP_NS):
            sitemap_url = self._parse_url_element(url_elem)
            if sitemap_url:
                data.urls.append(sitemap_url)

        logger.info(f"Parsed sitemap with {len(data.urls)} URLs")
        return data

    def _parse_url_element(self, url_elem: etree._Element) -> Optional[SitemapUrl]:
        """Parse a single <url> element."""
        loc_elem = url_elem.find("sm:loc", SITEMAP_NS)
        if loc_elem is None or not loc_elem.text:
            return None

        url = SitemapUrl(loc=loc_elem.text.strip())

        # Parse lastmod
        lastmod_elem = url_elem.find("sm:lastmod", SITEMAP_NS)
        if lastmod_elem is not None and lastmod_elem.text:
            url.lastmod = self._parse_datetime(lastmod_elem.text.strip())

        # Parse changefreq
        changefreq_elem = url_elem.find("sm:changefreq", SITEMAP_NS)
        if changefreq_elem is not None and changefreq_elem.text:
            url.changefreq = changefreq_elem.text.strip()

        # Parse priority
        priority_elem = url_elem.find("sm:priority", SITEMAP_NS)
        if priority_elem is not None and priority_elem.text:
            try:
                url.priority = float(priority_elem.text.strip())
            except ValueError:
                pass

        # Parse alternates (hreflang)
        for link in url_elem.findall("xhtml:link", SITEMAP_NS):
            rel = link.get("rel")
            hreflang = link.get("hreflang")
            href = link.get("href")
            if rel == "alternate" and hreflang and href:
                url.alternates[hreflang] = href

        return url

    def _parse_datetime(self, date_str: str) -> Optional[datetime]:
        """Parse W3C datetime format."""
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None

    async def fetch_all_urls(self, url: str) -> list[SitemapUrl]:
        """Fetch sitemap and recursively get all URLs (handles nested sitemap indexes).

        Warnings about an incomplete resolution are logged only; use
        ``fetch_and_parse`` when the caller needs to surface them.
        """
        data = await self.fetch_and_parse(url)
        return data.urls
