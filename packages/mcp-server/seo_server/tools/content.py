"""Content tool — seo_content (AI-powered content generation, 6 actions)."""

import logging

from seo_server import service_context as svc
from seo_server.schemas.content import SeoContentInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_content",
    description="""AI-powered SEO content generation and optimization. Requires: LLM API key.
Actions:
- write: Generate a full SEO-optimized article from a target keyword. Requires target_keyword.
- optimize: Optimize existing content for SEO. Requires content + target_keyword.
- meta: Generate meta titles and descriptions with CTR scoring. Requires target_url or target_keyword.
- headlines: Generate headline variations with conversion scoring. Requires target_keyword.
- humanize: Remove AI writing patterns and naturalize content. Requires content.
- research: Generate a comprehensive content brief for a keyword. Requires target_keyword (+ optional target_url).""",
)
@tool_handler
async def seo_content(input: SeoContentInput) -> dict:
    action = input.action
    if action == "write":
        return await _content_write(input)
    elif action == "optimize":
        return await _content_optimize(input)
    elif action == "meta":
        return await _content_meta(input)
    elif action == "headlines":
        return await _content_headlines(input)
    elif action == "humanize":
        return await _content_humanize(input)
    elif action == "research":
        return await _content_research(input)
    else:
        return {
            "error": f"Unknown action: {action}. "
            "Use: write, optimize, meta, headlines, humanize, research"
        }


async def _content_write(input: SeoContentInput) -> dict:
    """Generate a full SEO-optimized article from a target keyword."""
    if not input.target_keyword:
        return {"error": "target_keyword is required for write"}
    try:
        return await svc.ctx.content_writer.write(
            target_keyword=input.target_keyword,
            target_url=input.target_url or "",
            language=input.language,
            tone=input.tone,
            word_count=input.word_count,
        )
    except Exception as e:
        logger.exception("Content write failed")
        return {"error": str(e)}


async def _content_optimize(input: SeoContentInput) -> dict:
    """Optimize existing content for SEO."""
    if not input.content:
        return {"error": "content is required for optimize"}
    try:
        keywords = [input.target_keyword] if input.target_keyword else []
        return await svc.ctx.content_optimizer.optimize(
            content=input.content,
            keywords=keywords,
        )
    except Exception as e:
        logger.exception("Content optimize failed")
        return {"error": str(e)}


async def _content_meta(input: SeoContentInput) -> dict:
    """Generate meta titles and descriptions with CTR scoring."""
    if not input.target_keyword and not input.target_url:
        return {"error": "target_keyword or target_url is required for meta"}
    try:
        page_data = {}
        if input.target_url:
            try:
                pages = await svc.ctx.crawler.crawl_pages([input.target_url])
                if pages and pages[0].status_code == 200:
                    crawled = pages[0]
                    page_data = {
                        "title": crawled.title or "",
                        "meta_description": crawled.meta_description or "",
                        "h1": crawled.h1 or "",
                        "url": input.target_url,
                    }
            except Exception as e:
                logger.warning("Failed to crawl %s for meta: %s", input.target_url, e)

        return await svc.ctx.meta_generator.generate_meta(
            target_keyword=input.target_keyword,
            target_url=input.target_url or "",
            page_data=page_data,
        )
    except Exception as e:
        logger.exception("Content meta failed")
        return {"error": str(e)}


async def _content_headlines(input: SeoContentInput) -> dict:
    """Generate headline variations with conversion scoring."""
    if not input.target_keyword:
        return {"error": "target_keyword is required for headlines"}
    try:
        return await svc.ctx.meta_generator.generate_headlines(
            topic=input.target_keyword,
            keywords=[input.target_keyword],
        )
    except Exception as e:
        logger.exception("Content headlines failed")
        return {"error": str(e)}


async def _content_humanize(input: SeoContentInput) -> dict:
    """Remove AI writing patterns and naturalize content."""
    if not input.content:
        return {"error": "content is required for humanize"}
    try:
        return await svc.ctx.content_writer.humanize(content=input.content)
    except Exception as e:
        logger.exception("Content humanize failed")
        return {"error": str(e)}


async def _content_research(input: SeoContentInput) -> dict:
    """Generate a comprehensive content brief for a keyword."""
    if not input.target_keyword:
        return {"error": "target_keyword is required for research"}
    try:
        return await svc.ctx.content_brief.generate(
            target_url=input.target_url or "",
            target_keyword=input.target_keyword,
            language=input.language,
        )
    except Exception as e:
        logger.exception("Content research failed")
        return {"error": str(e)}
