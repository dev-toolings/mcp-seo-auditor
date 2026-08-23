"""Full AI-powered audit service."""

import asyncio
import dataclasses
import logging
import random
from collections import defaultdict
from urllib.parse import urlparse

from app.core.scoring import BROKEN_LINK_PENALTY, ORPHAN_PAGE_PENALTY, AuditScorer
from app.services.ai.ai_analyzer import AIAnalyzer
from app.services.geo.geo_analyzer import GEOAnalyzer

logger = logging.getLogger(__name__)

# Circuit breaker thresholds
CIRCUIT_BREAKER_MIN_PAGES = 20
CIRCUIT_BREAKER_ERROR_RATIO = 0.8


class FullAuditService:
    """Orchestrates a complete AI-enhanced SEO audit."""

    def __init__(self, orchestrator, geo_analyzer: GEOAnalyzer, ai_analyzer: AIAnalyzer):
        self.orchestrator = orchestrator
        self.geo = geo_analyzer
        self.ai = ai_analyzer

    async def run(
        self,
        sitemap_url: str,
        max_pages: int = 500,
        include_cwv: bool = False,
        language: str = "en",
    ) -> dict:
        """Run full audit pipeline.

        1. Parse sitemap + stratified sample
        2. Probe-first — fail fast if site is unreachable
        3. Single crawl with circuit breaker
        4. Pass pre-crawled pages to all analyzers (no re-crawl)
        5. GEO analysis on same pages
        6. Calculate dimension scores + AI enrichment
        """
        # 1. Parse sitemap
        sitemap_result = await self.orchestrator.audit_sitemap(sitemap_url)
        sitemap_data = await self.orchestrator.sitemap_parser.fetch_and_parse(sitemap_url)
        all_sitemap_urls = [u.loc for u in sitemap_data.urls]
        sample_urls = _stratified_sample(all_sitemap_urls, max_pages)

        if not sample_urls:
            return {"error": "No URLs found in sitemap", "sitemap_url": sitemap_url}

        # 2. Probe-first — test reachability before committing to full crawl
        probe_error = await self._probe_site(sample_urls)
        if probe_error:
            return {**probe_error, "sitemap_url": sitemap_url, "sitemap": sitemap_result}

        # 3. Single crawl with circuit breaker
        pages = await self._crawl_with_early_abort(sample_urls)
        ok_pages = [p for p in pages if p.status_code == 200]
        logger.info("Crawl complete: %d/%d pages OK (single crawl)", len(ok_pages), len(pages))

        # 4. Run parallel analyses — pass pre-crawled pages, no re-crawl
        content_cap = min(len(pages), 200)
        schema_cap = min(len(pages), 200)
        technical_cap = min(len(pages), 200)
        cwv_cap = min(len(sample_urls), 10)

        tasks = [
            self.orchestrator.audit_content(
                [p.url for p in pages[:content_cap]],
                pages=pages[:content_cap],
                language=language,
            ),
            self.orchestrator.structured_data(
                [p.url for p in pages[:schema_cap]],
                pages=pages[:schema_cap],
            ),
            self.orchestrator.internal_links(
                sitemap_url,
                max_pages=max_pages,
                pages=pages,
                sitemap_urls=all_sitemap_urls,
            ),
            self.orchestrator.technical_check(
                [p.url for p in pages[:technical_cap]],
                pages=pages[:technical_cap],
                sitemap_urls=all_sitemap_urls,
            ),
            self._fetch_gsc_summary(sitemap_url),
        ]

        if include_cwv:
            tasks.append(self.orchestrator.core_web_vitals(sample_urls[:cwv_cap]))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results (handle exceptions from gather)
        content_result = (
            results[0] if not isinstance(results[0], Exception) else {"error": str(results[0])}
        )
        structured_data_result = (
            results[1] if not isinstance(results[1], Exception) else {"error": str(results[1])}
        )
        links_result = (
            results[2] if not isinstance(results[2], Exception) else {"error": str(results[2])}
        )
        technical_result = (
            results[3] if not isinstance(results[3], Exception) else {"error": str(results[3])}
        )
        gsc_result = results[4] if not isinstance(results[4], Exception) else None
        cwv_result = None
        if include_cwv and len(results) > 5 and not isinstance(results[5], Exception):
            cwv_result = results[5]

        # 5. GEO analysis — reuse already-crawled pages
        geo_result = None
        try:
            geo_pages = [
                {
                    "url": p.url,
                    "html_content": p.raw_html or p.content or "",
                    "structured_data": p.structured_data or [],
                }
                for p in ok_pages[:50]
            ]
            if geo_pages:
                geo_result = await self.geo.analyze_pages(geo_pages)
        except Exception as e:
            logger.warning("GEO analysis failed: %s", e)

        # 6. Aggregate all results
        audit_data = {
            "sitemap_url": sitemap_url,
            "total_urls": len(sitemap_data.urls),
            "urls_analyzed": len(sample_urls),
            "sitemap": sitemap_result,
            "content": content_result,
            "structured_data": structured_data_result,
            "internal_links": links_result,
            "technical": technical_result,
            "cwv": cwv_result,
            "geo": geo_result.model_dump() if geo_result else None,
            "gsc_performance": gsc_result,
        }

        # 7. Calculate dimension scores
        audit_data["dimension_scores"] = self._calculate_dimension_scores(audit_data)
        audit_data["overall_score"] = self._calculate_overall_score(audit_data["dimension_scores"])

        # 8. AI enrichment
        # Preserve dimension_scores and overall_score calculated above — the
        # deterministic fallback in AIAnalyzer uses a different (legacy) formula
        # that doesn't have access to the same data keys, so its scores are
        # unreliable.  Only let the AI enrichment *add* new keys (recommendations,
        # quick_wins, executive_summary, etc.) without overwriting our scores.
        preserved_keys = {"dimension_scores", "overall_score"}
        try:
            ai_analysis = await self.ai.analyze_audit(audit_data)
            for k, v in ai_analysis.items():
                if k not in preserved_keys:
                    audit_data[k] = v
        except Exception as e:
            logger.warning("AI enrichment failed: %s", e)
            audit_data["ai_enhanced"] = False
            audit_data["ai_error"] = str(e)

        return audit_data

    async def _probe_site(self, urls: list[str]) -> dict | None:
        """Quick reachability test — HEAD requests on homepage + 2 random URLs.

        Returns an error dict if all probes fail, None otherwise.
        """
        probe_urls = [urls[0]]
        if len(urls) > 3:
            probe_urls.extend(random.sample(urls[1:], min(2, len(urls) - 1)))

        results = await asyncio.gather(
            *[self.orchestrator.crawler.check_url_status(url) for url in probe_urls]
        )
        probe_details = [
            {"url": url, "status": status, "error": error}
            for url, (status, error) in zip(probe_urls, results)
        ]
        failures = sum(1 for status, _ in results if status == 0 or status >= 500)

        if failures >= len(probe_urls):
            return {
                "error": "Site unreachable — all probe requests failed",
                "probe_results": probe_details,
                "recommendation": (
                    "The site appears to be blocking automated requests or is down. "
                    "Check if the site requires JavaScript rendering, uses anti-bot protection, "
                    "or is temporarily unavailable."
                ),
            }
        return None

    async def _crawl_with_early_abort(self, urls: list[str]):
        """Crawl with circuit breaker — abort if error rate exceeds threshold."""
        error_count = 0
        total_checked = 0
        abort_signal = [False]

        async def on_page(page, current, total):
            nonlocal error_count, total_checked
            total_checked += 1
            if page.status_code == 0 or page.status_code >= 500:
                error_count += 1
            if (
                total_checked >= CIRCUIT_BREAKER_MIN_PAGES
                and error_count / total_checked > CIRCUIT_BREAKER_ERROR_RATIO
            ):
                logger.warning(
                    "Circuit breaker triggered: %d/%d pages failed (%.0f%%), aborting crawl",
                    error_count,
                    total_checked,
                    error_count / total_checked * 100,
                )
                abort_signal[0] = True

        return await self.orchestrator.crawler.crawl_pages(
            urls, on_page_crawled=on_page, abort_signal=abort_signal
        )

    async def _fetch_gsc_summary(self, sitemap_url: str) -> dict | None:
        """Fetch GSC performance summary in parallel with the crawl.

        Returns a compact dict with site_totals, top_pages, top_queries,
        and low_ctr_opportunities. Returns None if GSC is not configured
        or any error occurs.
        """
        gsc = self.orchestrator._ctx.gsc
        if not gsc.is_credentials_available:
            return None

        # Derive site origin from sitemap URL
        parsed = urlparse(sitemap_url)
        site_origin = f"{parsed.scheme}://{parsed.hostname}"

        try:
            from seo_server.gsc_resolve import resolve_site_url

            site_url = await resolve_site_url(site_origin)
        except Exception as e:
            logger.warning("GSC resolve failed: %s", e)
            return None

        try:
            top_pages_raw, top_queries_raw = await asyncio.gather(
                gsc.get_top_pages(days=28, limit=50, site_url=site_url),
                gsc.get_top_queries(days=28, limit=20, site_url=site_url),
            )
        except Exception as e:
            logger.warning("GSC fetch failed: %s", e)
            return None

        if not top_pages_raw and not top_queries_raw:
            return None

        # Build compact summary
        top_pages = [dataclasses.asdict(p) for p in top_pages_raw]
        top_queries = [dataclasses.asdict(q) for q in top_queries_raw]

        total_clicks = sum(p["clicks"] for p in top_pages)
        total_impressions = sum(p["impressions"] for p in top_pages)

        low_ctr = [p for p in top_pages if p["impressions"] > 100 and p["ctr"] < 0.02]

        return {
            "site_totals": {
                "clicks_28d": total_clicks,
                "impressions_28d": total_impressions,
                "avg_ctr": total_clicks / total_impressions if total_impressions > 0 else 0,
            },
            "top_pages": sorted(top_pages, key=lambda p: p["clicks"], reverse=True)[:20],
            "top_queries": top_queries,
            "low_ctr_opportunities": sorted(low_ctr, key=lambda p: p["impressions"], reverse=True)[
                :10
            ],
        }

    def _calculate_dimension_scores(self, data: dict) -> dict:
        """Calculate scores for each audit dimension."""
        scores = {}

        # Technical: from technical check + sitemap score
        scores["technical"] = self._safe_score(data.get("sitemap", {}), data.get("technical", {}))

        # Content: from content audit
        scores["content"] = data.get("content", {}).get("score", 50)

        # Links: from internal links
        links = data.get("internal_links", {})
        orphan_penalty = len(links.get("orphan_pages", [])) * ORPHAN_PAGE_PENALTY
        broken_penalty = len(links.get("broken_internal_links", [])) * BROKEN_LINK_PENALTY
        scores["links"] = min(100, max(0, 100 - orphan_penalty - broken_penalty))

        # Schema: from structured data
        sd = data.get("structured_data", {})
        sd_summary = sd.get("summary", {})
        pages_with = sd_summary.get("pages_with_schemas", 0)
        pages_without = sd_summary.get("pages_without_schemas", 0)
        sd_total = pages_with + pages_without
        if sd_total > 0:
            scores["schema"] = int(pages_with / sd_total * 100)
        else:
            # Fallback: try per-page results array
            sd_results = sd.get("results", [])
            if sd_results:
                valid = sum(1 for r in sd_results if r.get("valid_schemas", 0) > 0)
                scores["schema"] = int(valid / max(len(sd_results), 1) * 100)
            else:
                scores["schema"] = 0

        # Performance: from CWV
        if data.get("cwv"):
            cwv_results = data["cwv"].get("results", [])
            if cwv_results:
                perf_scores = [
                    r.get("performance_score", 50) for r in cwv_results if isinstance(r, dict)
                ]
                scores["performance"] = int(sum(perf_scores) / max(len(perf_scores), 1))

        # GEO: from GEO analysis
        geo_data = data.get("geo")
        if geo_data:
            scores["geo"] = geo_data.get("geo_score", 0)

        return scores

    def _safe_score(self, sitemap: dict, technical: dict) -> int:
        """Compute technical score from sitemap + technical check results."""
        sitemap_score = sitemap.get("score", 50)
        canonical_issues = len(technical.get("canonical_issues", []))
        meta_issues = len(technical.get("meta_robots_issues", []))
        tech_penalty = canonical_issues * 5 + meta_issues * 5
        return int(max(0, min(100, (sitemap_score + max(0, 100 - tech_penalty)) / 2)))

    def _calculate_overall_score(self, dimension_scores: dict) -> int:
        """Weighted average of dimension scores."""
        return AuditScorer.calculate_overall_score(dimension_scores)


def _stratified_sample(urls: list[str], max_count: int) -> list[str]:
    """Sample URLs proportionally by first path segment.

    Ensures each URL pattern (e.g. /blog/, /products/, /) is represented
    proportionally in the sample, unlike head-slice which over-represents
    whatever comes first alphabetically in the sitemap.
    """
    if len(urls) <= max_count:
        return urls

    groups: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        parts = urlparse(url).path.strip("/").split("/")
        key = f"/{parts[0]}/" if parts and parts[0] else "/"
        groups[key].append(url)

    selected = []
    for group in groups.values():
        allocation = max(1, round(len(group) / len(urls) * max_count))
        selected.extend(random.sample(group, min(allocation, len(group))))

    if len(selected) > max_count:
        selected = random.sample(selected, max_count)
    return selected
