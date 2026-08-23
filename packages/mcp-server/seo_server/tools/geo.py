"""GEO tool — seo_geo (Generative Engine Optimization readiness)."""

import logging

from seo_server import service_context as svc
from seo_server.schemas.geo import SeoGeoInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_geo",
    description=(
        "GEO (Generative Engine Optimization) readiness assessment: measures how well "
        "pages are optimized for AI-powered search engines. Returns: GEO score (0-100), "
        "grade, per-dimension scores, recommendations."
    ),
)
@tool_handler
async def seo_geo(input: SeoGeoInput) -> dict:
    urls = input.urls[: input.max_urls]
    logger.info("MCP: seo_geo for %d URLs (engine=%s)", len(urls), input.target_engine)

    pages = await svc.ctx.crawler.crawl_pages(urls)
    geo_pages = [
        {
            "url": p.url,
            "html_content": p.raw_html or p.content or "",
            "structured_data": p.structured_data or [],
        }
        for p in pages
        if p.status_code == 200
    ]
    if not geo_pages:
        return {"error": "No pages could be crawled successfully"}
    report = await svc.ctx.geo_analyzer.analyze_pages(geo_pages, target_engine=input.target_engine)
    result = report.model_dump()
    if not input.include_ai_recommendations:
        result.pop("ai_recommendations", None)
    result["ai_enhanced"] = input.include_ai_recommendations
    result["target_engine"] = input.target_engine
    result["language"] = input.language
    result["urls_analyzed"] = len(geo_pages)
    return result
