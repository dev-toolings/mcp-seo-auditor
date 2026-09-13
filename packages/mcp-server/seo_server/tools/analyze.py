"""Analyze tool — seo_analyze (per-page SEO analysis, 5 actions)."""

import logging
from typing import Any

from seo_server import service_context as svc
from seo_server.schemas.analyze import SeoAnalyzeInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_analyze",
    description="""Analyze specific pages for SEO quality.
Actions:
- content: Content quality audit (thin content, meta tags, readability, headings). Use depth='deep' for readability + image alt + heading hierarchy.
- technical: Canonical tags, meta robots, hreflang (reciprocity, BCP47, x-default) and redirect chains. Set check_render_diff=true to also report content that only appears after JS rendering (needs the optional browser crawler).
- structured_data: JSON-LD / Schema.org validation. To generate the missing schemas, use seo_fix(action="schema") — it returns an injectable snippet.
- eeat: E-E-A-T signals audit (author, citations, trust, credentials).
- cwv: Core Web Vitals via PageSpeed Insights API (LCP, INP, CLS).""",
)
@tool_handler
async def seo_analyze(input: SeoAnalyzeInput) -> dict:
    action = input.action
    if action == "content":
        return await _analyze_content(input)
    elif action == "technical":
        return await _analyze_technical(input)
    elif action == "structured_data":
        return await _analyze_structured_data(input)
    elif action == "eeat":
        return await _analyze_eeat(input)
    elif action == "cwv":
        return await _analyze_cwv(input)
    else:
        return {
            "error": f"Unknown action: {action}. Use: content, technical, structured_data, eeat, cwv"
        }


async def _analyze_content(input: SeoAnalyzeInput) -> dict:
    """Content quality audit — absorbs seo_content_audit + seo_page_score."""
    urls = input.urls
    depth = input.depth
    language = input.language
    check_thin_content = input.check_thin_content
    check_empty_listings = input.check_empty_listings
    logger.info("MCP: seo_analyze/content (%s) for %d URLs", depth, len(urls))

    from app.services.content_validator import ContentValidatorService, content_score
    from app.services.crawler_service import CrawlerService

    if input.listing_config:
        from app.services.crawler_service import ListingConfig as CrawlerListingConfig

        lc = CrawlerListingConfig(
            css_selectors=input.listing_config.css_selectors,
            count_css_selector=input.listing_config.count_css_selector,
            text_patterns=input.listing_config.text_patterns,
        )
        crawler = CrawlerService(listing_config=lc)
    else:
        crawler = svc.ctx.crawler

    pages = await crawler.crawl_pages(urls)

    listing_url_patterns = input.listing_config.url_patterns if input.listing_config else []
    validator = ContentValidatorService(listing_url_patterns=listing_url_patterns)
    all_issues = []
    issues_by_page = []
    page_results = []

    for page in pages:
        issues = validator.validate(
            page,
            check_thin_content=check_thin_content,
            check_empty_listings=check_empty_listings,
        )
        all_issues.extend(issues)
        issues_by_page.append(issues)
        page_result = {
            "url": page.url,
            "status": page.status_code,
            "title": page.title,
            "word_count": page.word_count,
            "item_count": page.item_count,
            "js_rendered": page.js_rendered,
            "issues": [i.description for i in issues],
        }

        if depth == "deep" and page.status_code == 200:
            _enrich_deep_analysis(page, page_result, language)

        page_results.append(page_result)

    return {
        "score": content_score(issues_by_page),
        "depth": depth,
        "pages_analyzed": len(pages),
        "pages_with_issues": sum(1 for p in page_results if p["issues"]),
        "pages": page_results,
        "recommendations": validator.generate_recommendations(all_issues, len(pages)),
    }


def _enrich_deep_analysis(page, page_result: dict, language: str) -> None:
    """Add readability, image alt, and heading hierarchy analysis."""
    from bs4 import BeautifulSoup

    from app.services.content_readability import analyze as analyze_readability

    if page.content:
        page_result["readability"] = analyze_readability(page.content, language=language)

    if page.title:
        title_len = len(page.title)
        page_result["title_analysis"] = {
            "length": title_len,
            "status": "ok" if 30 <= title_len <= 60 else "warning",
            "recommendation": (
                None
                if 30 <= title_len <= 60
                else ("Too short (< 30 chars)" if title_len < 30 else "Too long (> 60 chars)")
            ),
        }

    if page.meta_description:
        desc_len = len(page.meta_description)
        page_result["meta_description_analysis"] = {
            "length": desc_len,
            "status": "ok" if 120 <= desc_len <= 160 else "warning",
            "recommendation": (
                None
                if 120 <= desc_len <= 160
                else ("Too short (< 120 chars)" if desc_len < 120 else "Too long (> 160 chars)")
            ),
        }
    else:
        page_result["meta_description_analysis"] = {
            "length": 0,
            "status": "missing",
            "recommendation": "Add a meta description (120-160 characters)",
        }

    html_to_parse = page.raw_html
    if html_to_parse:
        try:
            soup = BeautifulSoup(html_to_parse, "lxml")
            images = soup.find_all("img")
            if images:
                missing_alt = sum(1 for img in images if not img.get("alt"))
                page_result["images"] = {
                    "total": len(images),
                    "missing_alt": missing_alt,
                    "alt_coverage": round((len(images) - missing_alt) / len(images) * 100, 1),
                }
            headings = []
            for level in range(1, 7):
                for tag in soup.find_all(f"h{level}"):
                    headings.append({"level": level, "text": tag.get_text(strip=True)[:100]})
            h1_count = sum(1 for h in headings if h["level"] == 1)
            page_result["headings"] = {
                "h1_count": h1_count,
                "h1_unique": h1_count == 1,
                "total_headings": len(headings),
                "outline": headings[:20],
            }
        except Exception as e:
            logger.warning("Failed to parse HTML for %s: %s", page.url, e)


async def _analyze_technical(input: SeoAnalyzeInput) -> dict:
    """Technical SEO checks — absorbs seo_technical_check."""
    urls = input.urls
    check_canonicals = input.check_canonicals
    check_meta_robots = input.check_meta_robots
    check_redirects = input.check_redirects
    sitemap_url = input.sitemap_url
    logger.info("MCP: seo_analyze/technical for %d URLs", len(urls))

    pages = await svc.ctx.crawler.crawl_pages(urls)
    result: dict[str, Any] = {"pages_analyzed": len(pages)}

    if check_canonicals:
        result["canonical_issues"] = svc.ctx.technical_seo_checker.validate_canonicals(pages)

    if check_meta_robots:
        sitemap_urls_list = []
        if sitemap_url:
            sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
            sitemap_urls_list = [u.loc for u in sitemap_data.urls]
            # Never let a partially-resolved sitemap look like a complete one.
            if sitemap_data.warnings:
                result["sitemap_warnings"] = sitemap_data.warnings
        result["meta_robots_issues"] = svc.ctx.technical_seo_checker.check_meta_robots(
            pages, sitemap_urls=sitemap_urls_list
        )

    if input.check_hreflang:
        result["hreflang_issues"] = svc.ctx.technical_seo_checker.validate_hreflang(pages=pages)

    if input.check_render_diff:
        result["render_diff"] = await svc.ctx.crawler.diff_raw_vs_rendered_batch(pages, sample=2)

    if check_redirects:
        redirect_results = []
        for url in urls[:10]:
            chain = await svc.ctx.technical_seo_checker.check_redirect_chain(url)
            if chain.get("has_redirect_chain"):
                redirect_results.append(chain)
        result["redirect_chains"] = redirect_results

    return result


async def _analyze_structured_data(input: SeoAnalyzeInput) -> dict:
    """Structured data validation — absorbs seo_structured_data.

    Read-only on purpose: generating the missing JSON-LD is seo_fix(action="schema"),
    which returns the artifact ready to inject instead of a nested report blob.
    """
    urls = input.urls
    logger.info("MCP: seo_analyze/structured_data for %d URLs", len(urls))

    pages = await svc.ctx.crawler.crawl_pages(urls)
    results = []
    for page in pages:
        if page.status_code == 200:
            report = svc.ctx.structured_data_validator.validate_page(page.url, page.structured_data)
            results.append(svc.ctx.structured_data_validator.to_dict(report))
        else:
            results.append({"url": page.url, "error": f"HTTP {page.status_code}"})

    return {"pages_analyzed": len(results), "results": results}


async def _analyze_eeat(input: SeoAnalyzeInput) -> dict:
    """E-E-A-T signals audit — absorbs seo_eeat_audit."""
    urls = input.urls
    sitemap_url = input.sitemap_url
    logger.info("MCP: seo_analyze/eeat for %d URLs", len(urls))

    pages = await svc.ctx.crawler.crawl_pages(urls)
    page_data = [
        {
            "url": p.url,
            "html_content": p.raw_html or p.content or "",
            "structured_data": p.structured_data or [],
        }
        for p in pages
        if p.status_code == 200
    ]
    if not page_data:
        return {
            "error": "No pages could be crawled successfully",
            "error_type": "ToolError",
            "recoverable": True,
        }

    sitemap_urls = []
    if sitemap_url:
        sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
        sitemap_urls = [u.loc for u in sitemap_data.urls]

    report = await svc.ctx.eeat_service.audit(page_data, sitemap_urls)
    return report.model_dump()


async def _analyze_cwv(input: SeoAnalyzeInput) -> dict:
    """Core Web Vitals — absorbs seo_core_web_vitals."""
    urls = input.urls
    strategy = input.strategy
    logger.info("MCP: seo_analyze/cwv for %d URLs (%s)", len(urls), strategy)

    results = await svc.ctx.cwv_service.analyze_multiple(urls, strategy=strategy)
    return {"strategy": strategy, "pages_analyzed": len(results), "results": results}
