"""Strategy tool — seo_strategy (AI-powered SEO strategy, 7 actions)."""

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any

from seo_server import service_context as svc
from seo_server.schemas.strategy import SeoStrategyInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_strategy",
    description="""AI-powered SEO strategy generation. Requires: LLM API key.
Actions:
- action_plan: Prioritized action plan with impact/effort scoring from sitemap audit. Requires sitemap_url.
- roadmap: Strategic 30/60/90 day SEO roadmap from aggregated data. Requires aggregated_data.
- competitor_gap: Competitive gap analysis to find SEO opportunities. Requires sitemap_url.
- content_plan: AI editorial content plan with per-article generation prompts. Crawls site, pulls GSC data, identifies gaps, and generates ready-to-use LLM prompts for each article. Requires site_url (GSC property) + sitemap_url.
- quick_wins: Identify low-hanging SEO opportunities from GSC data (striking distance keywords, low CTR, declining content). Requires site_url. Optional: days (default 28).
- priorities: Build effort/impact priority matrix for SEO actions from GSC data. Requires site_url. Optional: days (default 28).""",
)
@tool_handler
async def seo_strategy(input: SeoStrategyInput) -> dict:
    action = input.action
    if action == "action_plan":
        return await _strategy_action_plan(
            input.sitemap_url, input.business_context, input.max_actions
        )
    elif action == "roadmap":
        return await _strategy_roadmap(
            input.aggregated_data, input.business_context, input.site_type
        )
    elif action == "competitor_gap":
        return await _strategy_competitor_gap(
            input.sitemap_url, input.competitor_urls, input.keywords
        )
    elif action == "content_plan":
        return await _strategy_content_plan(input)
    elif action == "quick_wins":
        return await _strategy_quick_wins(input.site_url, input.days)
    elif action == "priorities":
        return await _strategy_priorities(input.site_url, input.days)
    else:
        return {
            "error": f"Unknown action: {action}. "
            "Use: action_plan, roadmap, competitor_gap, content_plan, quick_wins, priorities"
        }


async def _strategy_action_plan(
    sitemap_url: str | None, business_context: str, max_actions: int
) -> dict:
    """Prioritized action plan — absorbs seo_ai_strategy action_plan mode."""
    if not sitemap_url:
        return {"error": "sitemap_url is required for action_plan"}
    try:
        audit_data = await svc.ctx.full_audit.run(sitemap_url, max_pages=30, include_cwv=False)
        if audit_data.get("error"):
            return audit_data
        return await svc.ctx.action_plan.generate(audit_data, business_context, max_actions)
    except Exception as e:
        logger.exception("Strategy action_plan failed")
        return {"error": str(e)}


async def _strategy_roadmap(
    aggregated_data: dict[str, Any] | None, business_context: str, site_type: str | None
) -> dict:
    """Strategic roadmap — absorbs seo_ai_strategy roadmap mode."""
    if not aggregated_data:
        return {"error": "aggregated_data is required for roadmap"}
    try:
        return await svc.ctx.strategic_plan.generate(aggregated_data, business_context, site_type)
    except Exception as e:
        logger.exception("Strategy roadmap failed")
        return {"error": str(e)}


async def _strategy_competitor_gap(
    sitemap_url: str | None, competitor_urls: list[str], keywords: list[str]
) -> dict:
    """Competitor gap analysis — absorbs seo_ai_competitor_gap."""
    if not sitemap_url:
        return {"error": "sitemap_url is required for competitor_gap"}
    try:
        return await svc.ctx.competitor_gap.analyze(sitemap_url, competitor_urls, keywords)
    except Exception as e:
        logger.exception("Strategy competitor_gap failed")
        return {"error": str(e)}


async def _strategy_quick_wins(site_url: str | None, days: int) -> dict:
    """Quick-win SEO opportunities from GSC data."""
    if not site_url:
        return {"error": "site_url is required for quick_wins (GSC property identifier)"}
    try:
        return await svc.ctx.priorities_service.quick_wins(site_url, days)
    except Exception as e:
        logger.exception("Strategy quick_wins failed")
        return {"error": str(e)}


async def _strategy_priorities(site_url: str | None, days: int) -> dict:
    """Effort/impact priority matrix from GSC data."""
    if not site_url:
        return {"error": "site_url is required for priorities (GSC property identifier)"}
    try:
        return await svc.ctx.priorities_service.priority_matrix(site_url, days)
    except Exception as e:
        logger.exception("Strategy priorities failed")
        return {"error": str(e)}


async def _strategy_content_plan(input) -> dict:
    """Generate editorial content plan with per-article LLM generation prompts."""
    site_url = input.site_url
    sitemap_url = input.sitemap_url
    if not site_url:
        return {"error": "site_url is required for content_plan (GSC property identifier)"}
    if not sitemap_url:
        return {"error": "sitemap_url is required for content_plan"}

    try:
        # 1. Crawl existing pages (light crawl for content inventory)
        logger.info("content_plan: crawling %s", sitemap_url)
        sitemap_data = await svc.ctx.sitemap_parser.fetch_and_parse(sitemap_url)
        urls = [u.loc for u in sitemap_data.urls[:50]]
        crawled = await svc.ctx.crawler.crawl_pages(urls[:30])
        existing_pages = [
            {
                "url": p.url,
                "title": p.title,
                "word_count": p.word_count,
                "h1": p.h1,
                "status_code": p.status_code,
            }
            for p in crawled
            if p.status_code == 200
        ]

        # 2. Pull GSC top queries (28 days)
        gsc_queries = []
        if svc.ctx.gsc.is_credentials_available:
            from seo_server.gsc_resolve import resolve_site_url

            resolved_url = await resolve_site_url(site_url)
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=28)
            raw = await svc.ctx.gsc.get_advanced_search_analytics(
                site_url=resolved_url,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                dimensions=["query", "page"],
                row_limit=500,
                sort_by="impressions",
                sort_direction="descending",
            )
            for row in raw.get("rows", []):
                keys = row.get("keys", [])
                if len(keys) >= 2:
                    gsc_queries.append(
                        {
                            "query": keys[0],
                            "page": keys[1],
                            "clicks": row.get("clicks", 0),
                            "impressions": row.get("impressions", 0),
                            "ctr": round(row.get("ctr", 0) * 100, 2),
                            "position": round(row.get("position", 0), 1),
                        }
                    )

        # 3. Identify gaps: queries with high impressions but no dedicated page
        # or queries ranking poorly (position > 10)
        quick_wins = [q for q in gsc_queries if q["position"] > 5 and q["impressions"] >= 20]
        quick_wins.sort(key=lambda q: q["impressions"], reverse=True)

        # 4. Build site data for LLM
        site_data = {
            "existing_pages": existing_pages,
            "total_sitemap_urls": len(sitemap_data.urls),
            "gsc_top_queries": gsc_queries[:100],
            "quick_win_queries": quick_wins[:30],
            "language": input.language,
        }

        if input.keywords:
            site_data["seed_keywords"] = input.keywords

        # 5. AI generates the content plan
        result = await svc.ctx.ai_analyzer.generate_content_plan(site_data)
        result["data_sources"] = {
            "pages_crawled": len(existing_pages),
            "gsc_queries_analyzed": len(gsc_queries),
            "quick_wins_found": len(quick_wins),
        }

        # 6. Save full plan to file, return lightweight summary
        articles = result.get("articles", [])
        if articles:
            plan_dir = os.path.join(tempfile.gettempdir(), "seo-auditor-plans")
            os.makedirs(plan_dir, exist_ok=True)
            domain = site_url.replace("sc-domain:", "").replace("https://", "").split("/")[0]
            plan_path = os.path.join(plan_dir, f"content-plan-{domain}.json")
            with open(plan_path, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)

            # Return summary without generation_prompts (they're huge)
            summary_articles = []
            for a in articles:
                summary = {k: v for k, v in a.items() if k != "generation_prompt"}
                summary["has_prompt"] = "generation_prompt" in a
                summary_articles.append(summary)

            return {
                "site_summary": result.get("site_summary", ""),
                "articles_count": len(articles),
                "articles": summary_articles,
                "plan_file": plan_path,
                "usage": f"Read {plan_path} to access full generation prompts per article.",
                "data_sources": result["data_sources"],
                "ai_enhanced": result.get("ai_enhanced", False),
            }

        return result

    except Exception as e:
        logger.exception("Strategy content_plan failed")
        return {"error": str(e)}
