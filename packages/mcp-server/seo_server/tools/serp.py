"""SERP tool — seo_serp (SERP prediction, live scraping, position tracking, 5 actions).

``live`` and the persistence actions below all go through the same
``serp_analyzer.analyze`` call; ``track`` is ``live`` plus a write to the crawl
repository, which is why the former ``seo_rank`` tool was folded in here.
"""

import logging
from urllib.parse import urlparse

from seo_server import service_context as svc
from seo_server.schemas.serp import SeoSerpInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_serp",
    description="""Analyze SERPs (Search Engine Results Pages) and track ranking positions over time.
Actions:
- predict: Heuristic SERP feature prediction (featured snippets, PAA, knowledge panels, local pack). No API key needed. Requires keywords.
- live: Live SERP scraping for ranking positions and competitor presence. Requires keywords. Requires agent-browser.
- track: Same as live, but persists the positions for historical tracking. Requires keywords + site_url.
- history: Position history for keywords over time. Requires keywords + site_url. Optional days (default 90).
- dashboard: Overview of all tracked keywords with position distribution. Requires site_url. Optional days (default 90).""",
)
@tool_handler
async def seo_serp(input: SeoSerpInput) -> dict:
    action = input.action

    if action == "predict":
        if not input.keywords:
            return {"error": "keywords required for predict action"}
        logger.info("MCP: seo_serp/predict for %d keywords", len(input.keywords))
        return await svc.ctx.serp_landscape_service.analyze(input.keywords, input.site_domain)
    elif action == "live":
        if not input.keywords:
            return {"error": "keywords required for live action"}
        logger.info("MCP: seo_serp/live for %d keywords", len(input.keywords))
        result = await svc.ctx.serp_analyzer.analyze(
            input.keywords, input.engine, input.site_domain
        )
        # Enrich with DataForSEO SERP data if configured
        return await _enrich_live_serp(result, input.keywords)
    elif action == "track":
        return await _serp_track(input)
    elif action == "history":
        return await _serp_history(input)
    elif action == "dashboard":
        return await _serp_dashboard(input)
    else:
        return {"error": f"Unknown action: {action}. Use: predict, live, track, history, dashboard"}


# ─── Position tracking (absorbs the former seo_rank tool) ──


async def _serp_track(input: SeoSerpInput) -> dict:
    """Scrape current positions and persist them — absorbs seo_rank track."""
    if not input.keywords:
        return {"error": "keywords required for track action"}
    if not input.site_url:
        return {"error": "site_url required for track action"}

    site_domain = input.site_domain or urlparse(input.site_url).netloc
    result = await svc.ctx.serp_analyzer.analyze(input.keywords, input.engine, site_domain)
    if result.get("error"):
        return result

    repo = svc.ctx.crawl_repository
    saved = 0
    for kw_result in result.get("results", []):
        keyword = kw_result.get("keyword", "")
        if kw_result.get("error") or not keyword:
            continue

        positions = kw_result.get("site_positions", [])
        if positions:
            for pos in positions:
                await repo.save_position(
                    site_url=input.site_url,
                    keyword=keyword,
                    position=pos.get("position"),
                    url=pos.get("url"),
                    title=pos.get("title"),
                )
                saved += 1
        else:
            # Not found — save as None position
            await repo.save_position(site_url=input.site_url, keyword=keyword, position=None)
            saved += 1

    result["tracking"] = {"persisted": True, "positions_saved": saved}
    return result


async def _serp_history(input: SeoSerpInput) -> dict:
    """Position history from the crawl repository — absorbs seo_rank history."""
    if not input.keywords:
        return {"error": "At least one keyword required for history action"}
    if not input.site_url:
        return {"error": "site_url required for history action"}

    repo = svc.ctx.crawl_repository
    history = {
        keyword: await repo.get_position_history(input.site_url, keyword, input.days)
        for keyword in input.keywords
    }
    return {"site_url": input.site_url, "period_days": input.days, "keywords": history}


async def _serp_dashboard(input: SeoSerpInput) -> dict:
    """Tracked-position dashboard — absorbs seo_rank dashboard."""
    if not input.site_url:
        return {"error": "site_url required for dashboard action"}
    return await svc.ctx.crawl_repository.get_position_dashboard(input.site_url, input.days)


# ─── DataForSEO enrichment helpers ──────────────────


async def _enrich_live_serp(result: dict, keywords: list[str]) -> dict:
    """Add DataForSEO SERP results if configured."""
    try:
        dfs = svc.ctx.dataforseo_client
        if not dfs.is_configured:
            return result

        dataforseo_serp = {}
        for kw in keywords[:5]:  # Cap to avoid excessive API calls
            serp_data = await dfs.get_serp_results(kw)
            if "error" not in serp_data:
                dataforseo_serp[kw] = serp_data

        if dataforseo_serp:
            result["dataforseo_data"] = dataforseo_serp
    except Exception as exc:
        logger.warning("DataForSEO enrichment failed (serp/live): %s", exc)
    return result
