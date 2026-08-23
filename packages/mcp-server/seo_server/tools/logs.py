"""Log analysis tool — seo_logs (server log analysis for crawl budget, 4 actions)."""

import logging

from seo_server import service_context as svc
from seo_server.schemas.logs import SeoLogsInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_logs",
    description=(
        "Analyze server access logs for SEO insights"
        " — crawl budget, bot activity, AI bot detection.\n"
        "Actions:\n"
        "- analyze: Full log analysis — bot activity, crawl budget,"
        " status codes, sitemap cross-reference.\n"
        "- bots: Bot activity breakdown — Googlebot, Bingbot,"
        " GPTBot, ClaudeBot, PerplexityBot.\n"
        "- waste: Crawl budget waste detection — static assets,"
        " admin pages, UTM params, pagination.\n"
        "- ai_bots: AI bot activity focus — GPTBot, ClaudeBot,"
        " PerplexityBot crawl patterns."
    ),
)
@tool_handler
async def seo_logs(input: SeoLogsInput) -> dict:
    action = input.action
    log_content = input.log_content
    sitemap_url = input.sitemap_url

    if not log_content or not log_content.strip():
        return {"error": "No log content provided"}

    # Get sitemap URLs if provided
    sitemap_urls = None
    if sitemap_url:
        try:
            sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
            sitemap_urls = [u.loc for u in sitemap_data.urls]
        except Exception as e:
            logger.warning("Failed to parse sitemap for log cross-reference: %s", e)

    # Run full analysis then filter output based on action
    result = await svc.ctx.log_analyzer.analyze(log_content, sitemap_urls)

    if result.get("error"):
        return result

    if action == "analyze":
        return result
    elif action == "bots":
        return {
            "summary": result.get("summary", {}),
            "bot_activity": result.get("bot_activity", {}),
            "bot_status_codes": result.get("bot_status_codes", {}),
        }
    elif action == "waste":
        return {
            "summary": result.get("summary", {}),
            "crawl_budget": result.get("crawl_budget", {}),
            "recommendations": [
                r
                for r in result.get("recommendations", [])
                if "crawl" in r.lower() or "waste" in r.lower() or "block" in r.lower()
            ]
            or result.get("recommendations", []),
        }
    elif action == "ai_bots":
        return {
            "summary": result.get("summary", {}),
            "ai_bot_activity": result.get("ai_bot_activity", {}),
        }
    else:
        return {"error": (f"Unknown action: {action}. Use: analyze, bots, waste, ai_bots")}
