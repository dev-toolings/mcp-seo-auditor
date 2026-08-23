"""Fix tool — seo_fix (generate applyable SEO/GEO fixes as artifacts + unified diffs).

The WRITE/FIX half of the audit→fix→re-audit loop. Every reviewed SEO MCP is read-only;
this one *generates* the fix (JSON-LD, meta tags, robots.txt, llms.txt) and returns it as
a ready-to-apply artifact plus a unified diff against the current state. The server never
writes to remote sites — apply happens client-side (hence dry_run defaults to true).
"""

import difflib
import logging
from urllib.parse import urljoin, urlparse

import httpx

from app.core.safe_http import safe_get
from seo_server import service_context as svc
from seo_server.schemas.fix import SeoFixInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


def _unified_diff(before: str, after: str, path: str) -> str:
    """Build a unified diff between two text blobs."""
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


async def _fetch_text(url: str) -> str:
    """Fetch a URL as text; return '' on any failure."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await safe_get(client, url, headers={"User-Agent": "SEOAuditor/2.0"})
            if resp.status_code == 200:
                return resp.text
    except httpx.RequestError as e:
        logger.warning("Failed to fetch %s: %s", url, e)
    return ""


@mcp.tool(
    name="seo_fix",
    description="""Generate applyable SEO/GEO fixes as artifacts + unified diffs (audit→fix→re-audit loop).
Actions:
- schema: Generate JSON-LD for a page and return an injectable <script> snippet. Requires url.
- meta: Generate optimized title + meta description and a diff vs the current tags. Requires url (+ optional target_keyword).
- robots_txt: Audit AI crawlers in the live robots.txt and return a 2026 robots.txt + unified diff. Requires url or sitemap_url.
- llms_txt: Generate an llms.txt index of top pages from the sitemap. Requires sitemap_url.
dry_run defaults to true — the server returns artifacts/diffs only; apply them client-side.""",
)
@tool_handler
async def seo_fix(input: SeoFixInput) -> dict:
    action = input.action
    if action == "schema":
        return await _fix_schema(input)
    if action == "meta":
        return await _fix_meta(input)
    if action == "robots_txt":
        return await _fix_robots(input)
    if action == "llms_txt":
        return await _fix_llms(input)
    return {"error": f"Unknown action: {action}. Use: schema, meta, robots_txt, llms_txt"}


async def _fix_schema(input: SeoFixInput) -> dict:
    if not input.url:
        return {"error": "url is required for schema action"}
    result = await svc.ctx.schema_generator.generate(
        url=input.url, page_type=input.page_type, language=input.language
    )
    if "error" in result:
        return result
    return {
        "action": "schema",
        "url": input.url,
        "detected_page_type": result.get("detected_page_type"),
        "json_ld": result.get("json_ld"),
        "injection_snippet": result.get("html_snippet"),
        "apply_hint": "Insert the injection_snippet inside the page <head>.",
        "dry_run": input.dry_run,
    }


async def _fix_meta(input: SeoFixInput) -> dict:
    if not input.url:
        return {"error": "url is required for meta action"}

    pages = await svc.ctx.crawler.crawl_pages([input.url])
    if not pages:
        return {"error": f"Could not crawl {input.url}"}
    page = pages[0]
    keyword = input.target_keyword or (page.title or "").strip() or input.url

    generated = await svc.ctx.meta_generator.generate_meta(
        target_keyword=keyword, target_url=input.url
    )
    best = generated.get("best_combination") or {}
    new_title = best.get("title") or (generated.get("titles") or [{}])[0].get("title", "")
    new_desc = best.get("description") or (generated.get("descriptions") or [{}])[0].get(
        "description", ""
    )

    current = (
        f"<title>{page.title or ''}</title>\n"
        f'<meta name="description" content="{page.meta_description or ""}">\n'
    )
    proposed = f'<title>{new_title}</title>\n<meta name="description" content="{new_desc}">\n'

    return {
        "action": "meta",
        "url": input.url,
        "target_keyword": keyword,
        "new_title": new_title,
        "new_description": new_desc,
        "diff": _unified_diff(current, proposed, "head-meta.html"),
        "ai_enhanced": generated.get("ai_enhanced", False),
        "dry_run": input.dry_run,
    }


async def _fix_robots(input: SeoFixInput) -> dict:
    base = input.url or input.sitemap_url
    if not base:
        return {"error": "url or sitemap_url is required for robots_txt action"}
    parsed = urlparse(base)
    root = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urljoin(root, "/robots.txt")
    sitemap_url = input.sitemap_url or urljoin(root, "/sitemap.xml")

    current = await _fetch_text(robots_url)
    llms = await _fetch_text(urljoin(root, "/llms.txt"))
    audit = svc.ctx.llms_txt_checker.analyze(current, llms_txt=llms, sitemap_url=sitemap_url)
    recommended = audit["recommended_robots_txt"]

    return {
        "action": "robots_txt",
        "robots_url": robots_url,
        "score": audit["score"],
        "blocked_citation_bots": audit["blocked_citation_bots"],
        "classification": audit["classification"],
        "llms_txt_present": audit["llms_txt_present"],
        "recommended_robots_txt": recommended,
        "diff": _unified_diff(current, recommended, "robots.txt"),
        "issues": audit["issues"],
        "apply_hint": "Replace /robots.txt with recommended_robots_txt (review training-bot policy first).",
        "dry_run": input.dry_run,
    }


async def _fix_llms(input: SeoFixInput) -> dict:
    if not input.sitemap_url:
        return {"error": "sitemap_url is required for llms_txt action"}

    sitemap_urls = await svc.ctx.sitemap_parser.fetch_all_urls(input.sitemap_url)
    urls = [u.loc for u in sitemap_urls][: input.max_urls]
    if not urls:
        return {"error": f"No URLs found in sitemap {input.sitemap_url}"}

    host = urlparse(input.sitemap_url).netloc
    lines = [
        f"# {host}",
        "",
        "> Curated index of the most citable pages for AI answer engines.",
        "",
        "## Pages",
        "",
    ]
    lines += [f"- [{u}]({u})" for u in urls]
    content = "\n".join(lines) + "\n"

    return {
        "action": "llms_txt",
        "sitemap_url": input.sitemap_url,
        "url_count": len(urls),
        "llms_txt": content,
        "diff": _unified_diff("", content, "llms.txt"),
        "apply_hint": "Publish this as /llms.txt at the site root.",
        "dry_run": input.dry_run,
    }
