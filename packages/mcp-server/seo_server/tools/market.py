"""Market intelligence tool — seo_market (keyword research, trends, competitors, niches, volumes)."""

import asyncio
import logging

from seo_server import service_context as svc
from seo_server.schemas.market import SeoMarketInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_market",
    description=(
        "Market intelligence and keyword research. No API key needed"
        " — uses Google Trends + NLP.\n"
        "Actions:\n"
        "- research: Keyword research from seeds with pytrends suggestions"
        " + KeyBERT clustering.\n"
        "- trends: Trend analysis over 12 months — interest, seasonality,"
        " growth rate.\n"
        "- competitors: Competitor discovery via Google Trends related"
        " topics/queries.\n"
        "- niches: Find niche opportunities from rising queries + TF-IDF"
        " relevance scoring.\n"
        "- volumes: Volume estimation via GSC impressions calibrated with"
        " pytrends. Requires site_url + GSC credentials.\n"
        "- insights: AI-powered keyword impact analysis — aggregates research"
        " + trends + niches, then uses LLM to prioritize keywords by impact,"
        " classify intent, identify quick wins, and suggest content strategy.\n"
        "- viability: SaaS viability assessment — orchestrates all market"
        " intelligence tools to score a concept on demand, growth, competition,"
        " and open-source risk. Requires concept. Optional: market_type (B2B/B2C)."
    ),
)
@tool_handler
async def seo_market(input: SeoMarketInput) -> dict:
    action = input.action
    keywords = input.keywords

    if action == "research":
        logger.info("MCP: seo_market/research for %d keywords", len(keywords))
        result = await asyncio.to_thread(
            svc.ctx.keyword_research.research,
            keywords,
            input.geo,
            input.language,
        )
        # Enrich with DataForSEO keyword suggestions if configured
        result = await _enrich_research(result, keywords)
        return result

    elif action == "trends":
        logger.info("MCP: seo_market/trends for %d keywords", len(keywords))
        return await asyncio.to_thread(
            svc.ctx.trend_analysis.analyze,
            keywords,
            geo=input.geo.upper(),
        )

    elif action == "competitors":
        logger.info("MCP: seo_market/competitors for %d keywords", len(keywords))
        return await asyncio.to_thread(
            svc.ctx.competitor_analyzer.analyze,
            keywords,
            input.max_results,
            input.geo.upper(),
        )

    elif action == "niches":
        logger.info("MCP: seo_market/niches for %d keywords", len(keywords))
        return await asyncio.to_thread(
            svc.ctx.niche_finder.find_niches,
            keywords,
            input.max_results,
            input.geo.upper(),
        )

    elif action == "volumes":
        if not input.site_url:
            return {"error": "site_url is required for volume calibration."}
        logger.info("MCP: seo_market/volumes for %d keywords", len(keywords))
        result = await svc.ctx.volume_calibrator.calibrate(
            input.site_url,
            keywords,
            input.days,
            input.geo.upper(),
        )
        # Enrich with DataForSEO search volumes if configured
        result = await _enrich_volumes(result, keywords, input.language)
        return result

    elif action == "insights":
        logger.info("MCP: seo_market/insights for %d keywords", len(keywords))
        # Aggregate research + trends + niches
        research_data = await asyncio.to_thread(
            svc.ctx.keyword_research.research,
            keywords,
            input.geo,
            input.language,
        )
        trends_data = await asyncio.to_thread(
            svc.ctx.trend_analysis.analyze,
            keywords,
            geo=input.geo.upper(),
        )
        niches_data = await asyncio.to_thread(
            svc.ctx.niche_finder.find_niches,
            keywords,
            input.max_results,
            input.geo.upper(),
        )

        market_data = {
            "research": research_data,
            "trends": trends_data,
            "niches": niches_data,
        }

        # AI enrichment
        ai_insights = await svc.ctx.ai_analyzer.analyze_keyword_insights(market_data)

        return {
            **market_data,
            "ai_insights": ai_insights,
        }

    elif action == "viability":
        if not input.concept:
            return {"error": "concept is required for viability action."}
        logger.info("MCP: seo_market/viability for concept=%s", input.concept)
        return await svc.ctx.saas_viability.assess(
            input.concept, keywords, input.market_type, input.geo
        )

    else:
        return {
            "error": f"Unknown action: {action}. "
            "Use: research, trends, competitors, niches, volumes, insights, viability"
        }


# ─── DataForSEO enrichment helpers ──────────────────


async def _enrich_research(result: dict, keywords: list[str]) -> dict:
    """Add DataForSEO keyword suggestions if configured."""
    try:
        dfs = svc.ctx.dataforseo_client
        if not dfs.is_configured:
            return result
        # Use first keyword as seed for suggestions
        seed = keywords[0] if keywords else None
        if not seed:
            return result
        suggestions = await dfs.get_keyword_suggestions(seed)
        if "error" not in suggestions:
            result["dataforseo_data"] = suggestions
    except Exception as exc:
        logger.warning("DataForSEO enrichment failed (research): %s", exc)
    return result


async def _enrich_volumes(result: dict, keywords: list[str], language: str = "fr") -> dict:
    """Add DataForSEO search volume data if configured."""
    try:
        dfs = svc.ctx.dataforseo_client
        if not dfs.is_configured:
            return result
        volumes = await dfs.get_search_volume(keywords, language_code=language)
        if "error" not in volumes:
            result["dataforseo_data"] = volumes
    except Exception as exc:
        logger.warning("DataForSEO enrichment failed (volumes): %s", exc)
    return result
