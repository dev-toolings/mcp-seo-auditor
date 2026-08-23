"""GSC analytics tool — gsc_analytics (performance data, 6 actions)."""

import logging
import random
import re
from collections import defaultdict
from urllib.parse import urlparse

from seo_server import service_context as svc
from seo_server.gsc_resolve import resolve_site_url
from seo_server.schemas.gsc_analytics import GscAnalyticsInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler
from seo_server.tools._gsc_helpers import gsc_credentials_error

logger = logging.getLogger(__name__)


@mcp.tool(
    name="gsc_analytics",
    description="""Google Search Console performance analytics.
Actions:
- query: Universal search analytics endpoint. Use dimensions (query/page/device/country/date) and filters. Presets: omit dimensions for overview, dimensions=['page'] for top pages, dimensions=['query'] for top queries.
- compare: Compare performance between two date periods.
- cannibalization: Detect keyword cannibalization from real GSC impression data.
- sitemap_health: Cross-reference sitemap URLs with GSC indexation status.
- ai_queries: AI query detection, classification, and opportunity analysis.
- ai_traffic: AI traffic trend analysis across multiple periods.""",
)
@tool_handler
async def gsc_analytics(input: GscAnalyticsInput) -> dict:
    if not svc.ctx.gsc.is_credentials_available:
        return gsc_credentials_error()

    site_url = await resolve_site_url(input.site_url)

    action = input.action
    if action == "query":
        return await _analytics_query(input, site_url)
    elif action == "compare":
        return await _analytics_compare(input, site_url)
    elif action == "cannibalization":
        return await _analytics_cannibalization(input, site_url)
    elif action == "sitemap_health":
        return await _analytics_sitemap_health(input, site_url)
    elif action == "ai_queries":
        return await _analytics_ai_queries(input, site_url)
    elif action == "ai_traffic":
        return await _analytics_ai_traffic(input, site_url)
    else:
        return {
            "error": f"Unknown action: {action}. Use: query, compare, cannibalization, sitemap_health, ai_queries, ai_traffic"
        }


async def _analytics_query(input: GscAnalyticsInput, site_url: str) -> dict:
    """Universal query endpoint — absorbs gsc_performance, gsc_top_pages, gsc_top_queries, gsc_page_queries, gsc_advanced_analytics."""
    dimensions = input.dimensions
    page_url = input.page_url

    # If page_url is specified, filter by page
    if page_url:
        return await svc.ctx.gsc.get_search_by_page_query(
            site_url,
            page_url,
            input.days,
            input.limit,
        )

    # If advanced params are set, use advanced analytics
    if input.start_date or input.filter_dimension:
        return await svc.ctx.gsc.get_advanced_search_analytics(
            site_url,
            input.start_date,
            input.end_date,
            dimensions,
            input.search_type,
            input.row_limit,
            input.start_row,
            input.sort_by,
            input.sort_direction,
            input.filter_dimension,
            input.filter_operator,
            input.filter_expression,
        )

    # Dimension-based presets
    if not dimensions:
        # Overview: aggregate performance
        return await svc.ctx.gsc.get_performance(days=input.days, site_url=site_url)

    if dimensions == ["page"]:
        pages = await svc.ctx.gsc.get_top_pages(
            days=input.days,
            limit=input.limit,
            site_url=site_url,
        )
        return {
            "count": len(pages),
            "pages": [
                {
                    "url": p.url,
                    "clicks": p.clicks,
                    "impressions": p.impressions,
                    "ctr": p.ctr,
                    "position": p.position,
                }
                for p in pages
            ],
        }

    if dimensions == ["query"]:
        queries = await svc.ctx.gsc.get_top_queries(
            days=input.days,
            limit=input.limit,
            site_url=site_url,
        )
        return {
            "count": len(queries),
            "queries": [
                {
                    "query": q.query,
                    "clicks": q.clicks,
                    "impressions": q.impressions,
                    "ctr": q.ctr,
                    "position": q.position,
                }
                for q in queries
            ],
        }

    # Fallback: use advanced analytics with specified dimensions
    return await svc.ctx.gsc.get_advanced_search_analytics(
        site_url,
        input.start_date,
        input.end_date,
        dimensions,
        input.search_type,
        input.row_limit,
        input.start_row,
        input.sort_by,
        input.sort_direction,
        input.filter_dimension,
        input.filter_operator,
        input.filter_expression,
    )


async def _analytics_compare(input: GscAnalyticsInput, site_url: str) -> dict:
    """Compare periods — absorbs gsc_compare_periods."""
    required = ["period1_start", "period1_end", "period2_start", "period2_end"]
    for field in required:
        if not getattr(input, field):
            return {"error": f"{field} is required for compare action"}
    return await svc.ctx.gsc.compare_periods(
        site_url,
        input.period1_start,
        input.period1_end,
        input.period2_start,
        input.period2_end,
        input.dimensions,
        input.limit,
        input.row_limit,
    )


async def _analytics_cannibalization(input: GscAnalyticsInput, site_url: str) -> dict:
    """GSC cannibalization — absorbs gsc_cannibalization."""
    results = await svc.ctx.gsc.find_cannibalization_from_gsc(
        min_impressions=input.min_impressions,
        site_url=site_url,
    )
    return {"cannibalization_groups": len(results), "groups": results[:20]}


def _classify_url_pattern(url: str) -> str:
    """Classify a URL into a pattern group."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return "/"
    segments = path.split("/")
    pattern_parts = []
    for seg in segments:
        if not seg:
            continue
        if re.match(r"^[0-9a-f]{8}-", seg) or re.match(r"^\d+$", seg):
            pattern_parts.append("{id}")
        elif re.match(r"^[a-z0-9]+-[a-z0-9]+-", seg) and len(seg) > 20:
            pattern_parts.append("{slug}")
        else:
            pattern_parts.append(seg)
    return "/" + "/".join(pattern_parts)


async def _analytics_sitemap_health(input: GscAnalyticsInput, site_url: str) -> dict:
    """Sitemap health — absorbs seo_sitemap_health."""
    sitemap_url = input.sitemap_url
    if not sitemap_url:
        return {"error": "sitemap_url is required for sitemap_health action"}
    sample_size = input.sample_size
    use_cache = input.use_cache

    logger.info("MCP: gsc_analytics/sitemap_health for %s (sample=%d)", sitemap_url, sample_size)

    sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
    all_urls = [u.loc for u in sitemap_data.urls]
    total_urls = len(all_urls)

    if total_urls == 0:
        return {"error": "Sitemap is empty or could not be parsed", "sitemap_url": sitemap_url}

    pattern_groups: dict[str, list[str]] = defaultdict(list)
    for url in all_urls:
        pattern = _classify_url_pattern(url)
        pattern_groups[pattern].append(url)

    sampled_urls: list[str] = []
    for pattern, group_urls in pattern_groups.items():
        proportion = len(group_urls) / total_urls
        group_sample = max(1, int(proportion * sample_size))
        group_sample = min(group_sample, len(group_urls))
        sampled_urls.extend(random.sample(group_urls, group_sample))

    if len(sampled_urls) > sample_size:
        sampled_urls = random.sample(sampled_urls, sample_size)

    inspection_results = {}
    quota_info = None

    if svc.ctx.gsc.is_credentials_available:
        repo = svc.ctx.crawl_repository
        await repo.initialize()

        if use_cache:
            batch_result = await svc.ctx.gsc.batch_inspect_cached(site_url, sampled_urls, repo)
            inspection_results = batch_result.get("results", {})
            quota_info = batch_result.get("quota")
        else:
            for url in sampled_urls:
                try:
                    result = await svc.ctx.gsc.inspect_url(site_url, url)
                    await repo.cache_inspection(site_url, url, result)
                    await repo.increment_quota(site_url)
                    result["_from_cache"] = False
                    inspection_results[url] = result
                except Exception as e:
                    inspection_results[url] = {"error": str(e)}
            quota_used = await repo.get_quota_usage(site_url)
            quota_info = {"used": quota_used, "limit": 2000, "remaining": 2000 - quota_used}

    coverage_breakdown: dict[str, int] = defaultdict(int)
    indexed_count = 0
    issues: list[dict] = []

    for url, result in inspection_results.items():
        if "error" in result or result.get("_skipped"):
            coverage_breakdown["unknown"] += 1
            continue

        verdict = result.get("verdict", "UNKNOWN")
        coverage_state = result.get("coverage_state", "UNKNOWN")
        coverage_breakdown[coverage_state] += 1

        if verdict == "PASS":
            indexed_count += 1
        else:
            issues.append(
                {
                    "url": url,
                    "verdict": verdict,
                    "coverage_state": coverage_state,
                    "page_fetch": result.get("page_fetch"),
                    "robots_txt_state": result.get("robots_txt_state", result.get("robots_txt")),
                }
            )

    inspected_count = len(inspection_results)
    indexed_pct = round(indexed_count / inspected_count * 100, 1) if inspected_count > 0 else 0

    crawl_cross_ref = None
    try:
        sessions = await svc.ctx.crawl_repository.list_sessions(site_url=site_url, limit=1)
        if sessions:
            latest = sessions[0]
            crawl_cross_ref = {
                "session_id": latest.get("id"),
                "crawled_at": latest.get("started_at"),
                "crawled_urls": latest.get("crawled_urls", 0),
                "score": latest.get("score"),
            }
    except Exception:
        pass

    return {
        "sitemap_url": sitemap_url,
        "site_url": site_url,
        "total_urls": total_urls,
        "sampled": len(sampled_urls),
        "urls_by_pattern": {pattern: len(urls) for pattern, urls in sorted(pattern_groups.items())},
        "indexed_pct": indexed_pct,
        "coverage_breakdown": dict(coverage_breakdown),
        "issues_count": len(issues),
        "issues": issues[:50],
        "crawl_cross_ref": crawl_cross_ref,
        "quota": quota_info,
    }


async def _analytics_ai_queries(input: GscAnalyticsInput, site_url: str) -> dict:
    """AI query intelligence — absorbs gsc_ai_query_intelligence."""
    return await svc.ctx.ai_query_intelligence.analyze(
        site_url,
        input.days,
        input.language,
    )


async def _analytics_ai_traffic(input: GscAnalyticsInput, site_url: str) -> dict:
    """AI traffic growth — absorbs gsc_ai_traffic_growth."""
    return await svc.ctx.ai_query_intelligence.track_ai_traffic_growth(
        site_url,
        input.periods,
        input.period_days,
        input.language,
    )
