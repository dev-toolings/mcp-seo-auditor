"""Site tool — seo_site (site-wide analysis from sitemap, 7 actions)."""

import logging
from urllib.parse import urlparse

from seo_server import service_context as svc
from seo_server.schemas.site import SeoSiteInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_site",
    description="""Analyze site-wide SEO from sitemap. Start here for any new site.
Actions:
- sitemap: Audit sitemap.xml (duplicates, stale timestamps, depth). Set quick=true for fast overview.
- links: Internal link structure analysis (PageRank, orphans, broken links).
- cannibalization: NLP-based keyword cannibalization detection between pages.
- indexation_leaks: Detect internal links leaking crawl budget to noindex/blocked pages.
- topical_authority: Map topical authority clusters across site content.
- robots: Parse and analyze robots.txt rules.
- migration: Plan site migration with redirect mapping (requires old_sitemap_url + new_sitemap_url).""",
)
@tool_handler
async def seo_site(input: SeoSiteInput) -> dict:
    action = input.action
    if action == "sitemap":
        return await _site_sitemap(input)
    elif action == "links":
        return await _site_links(input)
    elif action == "cannibalization":
        return await _site_cannibalization(input)
    elif action == "indexation_leaks":
        return await _site_indexation_leaks(input)
    elif action == "topical_authority":
        return await _site_topical_authority(input)
    elif action == "robots":
        return await _site_robots(input)
    elif action == "migration":
        return await _site_migration(input)
    else:
        return {
            "error": f"Unknown action: {action}. Use: sitemap, links, cannibalization, indexation_leaks, topical_authority, robots, migration"
        }


async def _site_sitemap(input: SeoSiteInput) -> dict:
    """Audit sitemap.xml — absorbs seo_audit_sitemap."""
    sitemap_url = input.sitemap_url
    if not sitemap_url:
        return {"error": "sitemap_url is required for sitemap action"}
    quick = input.quick
    logger.info("MCP: seo_site/sitemap %s (quick=%s)", sitemap_url, quick)

    sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
    issues = svc.ctx.sitemap_analyzer.analyze(sitemap_data)

    total_urls = len(sitemap_data.urls)
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    score = max(0, 100 - (critical_count * 10) - (warning_count * 2))

    if quick:
        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 70:
            grade = "C"
        elif score >= 60:
            grade = "D"
        else:
            grade = "F"

        return {
            "score": score,
            "grade": grade,
            "total_urls": total_urls,
            "critical_issues": critical_count,
            "warnings": warning_count,
            "top_issues": [
                {"type": i.issue_type, "severity": i.severity, "description": i.description}
                for i in sorted(
                    issues, key=lambda x: (x.severity != "critical", x.severity != "warning")
                )[:5]
            ],
            "quick_wins": list(svc.ctx.sitemap_analyzer.generate_recommendations(issues)[:3]),
        }

    from app.models.report import AuditReport, AuditType

    report = AuditReport(
        audit_type=AuditType.SITEMAP,
        score=score,
        total_urls=total_urls,
        issues_critical=critical_count,
        issues_warning=warning_count,
        issues=issues,
        recommendations=svc.ctx.sitemap_analyzer.generate_recommendations(issues),
        metadata={"sitemap_url": sitemap_url},
    )
    await svc.ctx.report_repository.save(report)

    return {
        "audit_id": report.audit_id,
        "score": score,
        "total_urls": total_urls,
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
        "recommendations": report.recommendations,
    }


async def _site_links(input: SeoSiteInput) -> dict:
    """Internal link structure — absorbs seo_internal_links."""
    sitemap_url = input.sitemap_url
    if not sitemap_url:
        return {"error": "sitemap_url is required for links action"}
    max_pages = input.max_pages
    logger.info("MCP: seo_site/links from %s", sitemap_url)

    sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
    urls = [u.loc for u in sitemap_data.urls[:max_pages]]
    pages = await svc.ctx.crawler.crawl_pages(urls)
    sitemap_urls = [u.loc for u in sitemap_data.urls]
    return svc.ctx.internal_links_analyzer.analyze(pages, sitemap_urls=sitemap_urls)


async def _site_cannibalization(input: SeoSiteInput) -> dict:
    """NLP cannibalization detection — absorbs seo_cannibalization_nlp."""
    sitemap_url = input.sitemap_url
    if not sitemap_url:
        return {"error": "sitemap_url is required for cannibalization action"}
    max_urls = input.max_urls
    language = input.language
    logger.info("MCP: seo_site/cannibalization from %s", sitemap_url)

    sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
    urls_to_analyze = sitemap_data.urls[:max_urls]
    pages = await svc.ctx.crawler.crawl_pages([u.loc for u in urls_to_analyze])

    keyword_extractor = svc.ctx.keyword_extractor
    page_keywords = {}
    for page in pages:
        if page.status_code == 200:
            keywords = keyword_extractor.extract_keywords(
                page.content, page.title, language=language
            )
            page_keywords[page.url] = keywords

    detector = svc.ctx.cannibalization_detector
    keyword_groups = detector.detect(page_keywords)
    url_groups = detector.detect_url_cannibalization([u.loc for u in sitemap_data.urls])
    all_groups = keyword_groups + url_groups

    critical_count = sum(1 for g in all_groups if len(g.urls) > 3)
    warning_count = len(all_groups) - critical_count
    score = max(0, 100 - (critical_count * 15) - (warning_count * 5))

    return {
        "score": score,
        "urls_analyzed": len(page_keywords),
        "cannibalization_groups": len(all_groups),
        "groups": [
            {
                "urls": g.urls,
                "shared_keywords": g.shared_keywords[:5],
                "similarity": g.similarity_score,
                "recommendation": g.recommendation,
            }
            for g in all_groups[:10]
        ],
        "recommendations": detector.generate_recommendations(all_groups),
    }


async def _site_indexation_leaks(input: SeoSiteInput) -> dict:
    """Detect indexation leaks — absorbs seo_indexation_leaks."""
    urls = list(input.urls) if input.urls else []
    sitemap_url = input.sitemap_url
    max_pages = input.max_pages
    check_targets = input.check_targets

    if sitemap_url:
        logger.info("MCP: seo_site/indexation_leaks from sitemap %s", sitemap_url)
        sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
        urls = [u.loc for u in sitemap_data.urls[:max_pages]]
    elif urls:
        urls = urls[:max_pages]
    else:
        return {"error": "Provide either 'urls' or 'sitemap_url'"}

    logger.info("MCP: seo_site/indexation_leaks — crawling %d source pages", len(urls))

    source_pages = await svc.ctx.crawler.crawl_pages(urls)

    disallow_patterns = []
    if urls:
        parsed = urlparse(urls[0])
        root_url = f"{parsed.scheme}://{parsed.netloc}"
        try:
            robots_data = await svc.ctx.technical_seo_checker.parse_robots_txt(root_url)
            for rule in robots_data.get("rules", []):
                if (
                    rule.get("user_agent") == "*"
                    and rule.get("directive") == "disallow"
                    and rule.get("path")
                ):
                    disallow_patterns.append(rule["path"])
            disallow_patterns = list(set(disallow_patterns))
        except Exception as e:
            logger.warning("Failed to fetch robots.txt: %s", e)

    target_urls = set()
    for page in source_pages:
        for link in page.link_details:
            if link.is_internal and not link.nofollow:
                target_urls.add(link.href)

    source_url_set = {p.url for p in source_pages}
    target_urls -= source_url_set
    target_urls_list = list(target_urls)[:200]

    target_pages = {}
    redirect_results = {}

    if check_targets and target_urls_list:
        logger.info(
            "MCP: seo_site/indexation_leaks — checking %d target URLs",
            len(target_urls_list),
        )
        crawled_targets = await svc.ctx.crawler.crawl_pages(target_urls_list)
        for tp in crawled_targets:
            target_pages[tp.url] = tp
            if tp.final_url and tp.final_url != tp.url:
                redirect_results[tp.url] = tp.final_url

    report = svc.ctx.indexation_leak_detector.detect_leaks(
        source_pages=source_pages,
        disallow_patterns=disallow_patterns,
        target_pages=target_pages,
        redirect_results=redirect_results,
    )

    return report


async def _site_topical_authority(input: SeoSiteInput) -> dict:
    """Topical authority mapping — absorbs seo_topical_authority."""
    sitemap_url = input.sitemap_url
    if not sitemap_url:
        return {"error": "sitemap_url is required for topical_authority action"}
    max_pages = input.max_pages
    logger.info("MCP: seo_site/topical_authority from %s (max %d)", sitemap_url, max_pages)

    sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
    urls = [u.loc for u in sitemap_data.urls[:max_pages]]
    crawled = await svc.ctx.crawler.crawl_pages(urls)

    pages = [
        {
            "url": p.url,
            "title": p.title or "",
            "content": p.content or "",
            "word_count": p.word_count,
            "h1": p.h1 or "",
        }
        for p in crawled
        if p.status_code == 200
    ]

    if not pages:
        return {"error": "No pages could be crawled successfully"}

    return await svc.ctx.topical_authority.analyze(pages)


async def _site_robots(input: SeoSiteInput) -> dict:
    """Parse robots.txt — absorbs seo_robots_txt."""
    url = input.url or input.sitemap_url
    if not url:
        return {"error": "url or sitemap_url is required for robots action"}
    logger.info("MCP: seo_site/robots for %s", url)
    return await svc.ctx.technical_seo_checker.parse_robots_txt(url)


async def _site_migration(input: SeoSiteInput) -> dict:
    """Migration planning — absorbs seo_migration_plan."""
    old_sitemap_url = input.old_sitemap_url
    new_sitemap_url = input.new_sitemap_url
    if not old_sitemap_url or not new_sitemap_url:
        return {"error": "old_sitemap_url and new_sitemap_url are required for migration action"}
    site_url = input.site_url
    logger.info("MCP: seo_site/migration %s → %s", old_sitemap_url, new_sitemap_url)
    return await svc.ctx.migration_planner.plan(old_sitemap_url, new_sitemap_url, site_url)
