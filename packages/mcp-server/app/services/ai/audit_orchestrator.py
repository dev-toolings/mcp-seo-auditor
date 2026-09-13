"""Audit orchestrator — replaces ServiceContext facade methods to break circular dependency."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class AuditOrchestrator:
    """Provides SEO analysis operations by calling services directly.

    Replaces the facade pattern where AI services called ToolRegistry.dispatch()
    through ServiceContext, which created a circular dependency.
    """

    def __init__(self, ctx):
        """Accept the ServiceContext to access lazy-loaded services."""
        self._ctx = ctx

    # ─── Direct access to services (used by FullAuditService) ───

    @property
    def sitemap_parser(self):
        return self._ctx.sitemap_parser

    @property
    def crawler(self):
        return self._ctx.crawler

    # ─── Orchestrated operations ───

    async def audit_sitemap(self, sitemap_url: str) -> dict:
        """Audit a sitemap — equivalent to seo_site/sitemap action."""
        sitemap_data = await self._ctx.sitemap_parser.fetch_and_parse(sitemap_url)
        issues = self._ctx.sitemap_analyzer.analyze(sitemap_data)

        total_urls = len(sitemap_data.urls)
        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        score = max(0, 100 - (critical_count * 10) - (warning_count * 2))

        return {
            "score": score,
            "total_urls": total_urls,
            # Non-empty when the sitemap index was only partially resolved (depth
            # limit, loop, unreachable child) — the URL list is NOT exhaustive.
            "warnings": sitemap_data.warnings,
            "complete": not sitemap_data.warnings,
            "issues_critical": critical_count,
            "issues_warning": warning_count,
            "issues": [
                {
                    "type": i.issue_type,
                    "severity": i.severity,
                    "description": i.description,
                    "urls": i.urls[:3],
                    "recommendation": i.recommendation,
                }
                for i in issues
            ],
            "recommendations": self._ctx.sitemap_analyzer.generate_recommendations(issues),
        }

    async def audit_content(self, urls: list[str], pages=None, **kwargs) -> dict:
        """Content quality audit — equivalent to seo_analyze/content action."""
        from app.services.content_validator import ContentValidatorService, content_score

        if pages is None:
            pages = await self._ctx.crawler.crawl_pages(urls)
        validator = ContentValidatorService()
        all_issues = []
        issues_by_page = []
        page_results = []

        for page in pages:
            issues = validator.validate(page)
            all_issues.extend(issues)
            issues_by_page.append(issues)
            page_results.append(
                {
                    "url": page.url,
                    "status": page.status_code,
                    "title": page.title,
                    "word_count": page.word_count,
                    "item_count": page.item_count,
                    "js_rendered": page.js_rendered,
                    "issues": [i.description for i in issues],
                }
            )

        return {
            "score": content_score(issues_by_page),
            "pages_analyzed": len(pages),
            "pages_with_issues": sum(1 for p in page_results if p["issues"]),
            "pages": page_results,
            "recommendations": validator.generate_recommendations(all_issues, len(pages)),
        }

    async def structured_data(self, urls: list[str], pages=None) -> dict:
        """Structured data validation — equivalent to seo_analyze/structured_data action."""
        if pages is None:
            pages = await self._ctx.crawler.crawl_pages(urls)
        results = []
        for page in pages:
            if page.status_code == 200:
                report = self._ctx.structured_data_validator.validate_page(
                    page.url, page.structured_data
                )
                results.append(self._ctx.structured_data_validator.to_dict(report))
            else:
                results.append({"url": page.url, "error": f"HTTP {page.status_code}"})
        return {"pages_analyzed": len(results), "results": results}

    async def internal_links(
        self, sitemap_url: str, max_pages: int = 500, pages=None, sitemap_urls=None
    ) -> dict:
        """Internal links analysis — equivalent to seo_site/links action."""
        if pages is None:
            sitemap_data = await self._ctx.sitemap_parser.fetch_and_parse(sitemap_url)
            urls = [u.loc for u in sitemap_data.urls[:max_pages]]
            pages = await self._ctx.crawler.crawl_pages(urls)
            sitemap_urls = sitemap_urls or [u.loc for u in sitemap_data.urls]
        elif sitemap_urls is None:
            sitemap_data = await self._ctx.sitemap_parser.fetch_and_parse(sitemap_url)
            sitemap_urls = [u.loc for u in sitemap_data.urls]
        analyzer = self._ctx.internal_links_analyzer
        target_statuses = await self._ctx.crawler.check_link_statuses(
            analyzer.uncrawled_targets(pages)
        )
        return analyzer.analyze(pages, sitemap_urls=sitemap_urls, target_statuses=target_statuses)

    async def technical_check(
        self,
        urls: list[str],
        pages=None,
        sitemap_urls=None,
        render_diff_sample: int = 2,
        **kwargs,
    ) -> dict:
        """Technical SEO check — equivalent to seo_analyze/technical action."""
        if pages is None:
            pages = await self._ctx.crawler.crawl_pages(urls)
        result: dict[str, Any] = {"pages_analyzed": len(pages)}
        result["canonical_issues"] = self._ctx.technical_seo_checker.validate_canonicals(pages)
        result["meta_robots_issues"] = self._ctx.technical_seo_checker.check_meta_robots(
            pages, sitemap_urls=sitemap_urls
        )
        result["hreflang_issues"] = self._ctx.technical_seo_checker.validate_hreflang(pages=pages)
        result["render_diff"] = await self._render_diff(pages, render_diff_sample)
        return result

    async def _render_diff(self, pages, sample: int) -> list[dict]:
        """Raw HTML vs browser-rendered diff — delegates to the crawler service.

        Kept as a thin wrapper so a stubbed crawler without the batch helper (older
        test doubles) degrades to ``status: unavailable`` instead of raising.
        """
        try:
            return await self._ctx.crawler.diff_raw_vs_rendered_batch(pages, sample=sample)
        except AttributeError as e:
            logger.warning("Render diff unavailable: %s", e)
            targets = [p for p in pages if p.status_code == 200][:sample]
            return [{"url": p.url, "status": "unavailable", "reason": str(e)} for p in targets]

    async def core_web_vitals(self, urls: list[str], strategy: str = "mobile") -> dict:
        """CWV analysis — equivalent to seo_analyze/cwv action."""
        results = await self._ctx.cwv_service.analyze_multiple(urls, strategy=strategy)
        return {"strategy": strategy, "pages_analyzed": len(results), "results": results}

    async def gsc_performance(self, days: int = 28, site_url: str | None = None) -> dict:
        """GSC performance overview — equivalent to gsc_analytics/query action."""
        try:
            return await self._ctx.gsc.get_performance(days=days, site_url=site_url)
        except Exception as e:
            logger.warning("GSC performance failed: %s", e)
            return {"error": str(e)}
