"""Audit tool — seo_audit (AI-enhanced full site audit)."""

import json
import logging
from collections import Counter

from seo_server import service_context as svc
from seo_server.schemas.audit import SeoAuditInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)

_MAX_RESULT_CHARS = 95_000


@mcp.tool(
    name="seo_audit",
    description=(
        "Complete AI-enhanced SEO audit: crawls sitemap, analyzes content quality, "
        "technical SEO, structured data, internal links, and GEO readiness. Returns "
        "overall score (0-100), dimension scores, prioritized recommendations. "
        "Requires: LLM API key."
    ),
)
@tool_handler
async def seo_audit(input: SeoAuditInput) -> dict:
    try:
        result = await svc.ctx.full_audit.run(
            input.sitemap_url,
            input.max_pages,
            input.include_cwv,
            input.language,
        )
        if result.get("error"):
            return result
        try:
            session_id = await _persist_audit(input.sitemap_url, result)
            result["crawl_session_id"] = session_id
        except Exception as e:
            logger.warning("Failed to persist audit to SQLite: %s", e)
        return _compact_audit_result(result)
    except Exception as e:
        logger.exception("AI full audit failed")
        return {"error": str(e)}


def _compact_audit_result(result: dict) -> dict:
    """Compact full audit result to fit within MCP payload limits."""
    size = len(json.dumps(result, default=str))
    if size <= _MAX_RESULT_CHARS:
        return result

    out = dict(result)

    geo = out.get("geo")
    if geo and isinstance(geo, dict):
        page_results = geo.pop("page_results", [])
        if page_results:
            all_issues: list[str] = []
            for pr in page_results:
                all_issues.extend(pr.get("issues", []))
            issue_counts = Counter(all_issues)
            geo["top_issues"] = [
                {"issue": issue, "count": count} for issue, count in issue_counts.most_common(10)
            ]
            sorted_pages = sorted(page_results, key=lambda p: p.get("geo_score", 100))
            geo["worst_pages"] = [
                {k: v for k, v in p.items() if k != "recommendations"} for p in sorted_pages[:5]
            ]
            geo["pages_analyzed"] = len(page_results)
            geo["avg_geo_score"] = round(
                sum(p.get("geo_score", 0) for p in page_results) / len(page_results),
                1,
            )
        out["geo"] = geo

    sd = out.get("structured_data")
    if sd and isinstance(sd, dict):
        sd_results = sd.pop("results", [])
        if sd_results:
            total = len(sd_results)
            with_valid = sum(1 for r in sd_results if r.get("valid_schemas", 0) > 0)
            all_types: list[str] = []
            for r in sd_results:
                for s in r.get("schemas", []):
                    st = s.get("type", "")
                    if st:
                        all_types.append(st)
            type_counts = Counter(all_types)
            sd["summary"] = {
                "pages_with_schemas": with_valid,
                "pages_without_schemas": total - with_valid,
                "schema_types": dict(type_counts.most_common(15)),
            }
            all_recs: set[str] = set()
            for r in sd_results:
                for rec in r.get("recommendations", []):
                    all_recs.add(rec)
            sd["unique_recommendations"] = sorted(all_recs)[:10]
            sd["pages_without_schema"] = [
                r["url"] for r in sd_results if r.get("valid_schemas", 0) == 0
            ][:10]
        out["structured_data"] = sd

    content = out.get("content")
    if content and isinstance(content, dict):
        pages = content.pop("pages", [])
        if pages:
            pages_with_issues = [p for p in pages if p.get("issues")]
            content["pages_with_issues_detail"] = pages_with_issues[:15]
            content["total_pages_analyzed"] = len(pages)
            content["pages_ok"] = len(pages) - len(pages_with_issues)
        out["content"] = content

    links = out.get("internal_links")
    if links and isinstance(links, dict):
        links["top_pages_by_pagerank"] = links.get("top_pages_by_pagerank", [])[:10]
        out["internal_links"] = links

    logger.info(
        "Compacted audit result: %d → %d chars",
        size,
        len(json.dumps(out, default=str)),
    )
    return out


async def _persist_audit(sitemap_url: str, audit_data: dict) -> str:
    """Persist full audit results to SQLite via CrawlRepository."""
    from urllib.parse import urlparse

    repo = svc.ctx.crawl_repository
    await repo.initialize()

    parsed = urlparse(sitemap_url)
    site_url = f"{parsed.scheme}://{parsed.netloc}"
    total_urls = audit_data.get("urls_analyzed", 0)
    overall_score = audit_data.get("overall_score")

    session_id = await repo.create_session(
        site_url=site_url,
        total_urls=total_urls,
        metadata={
            "audit_type": "ai_full_audit",
            "sitemap_url": sitemap_url,
            "dimension_scores": audit_data.get("dimension_scores", {}),
        },
    )

    pages_saved = 0
    content_data = audit_data.get("content", {})
    content_pages = content_data.get("pages", [])
    for page in content_pages:
        await repo.save_page(
            session_id,
            {
                "url": page.get("url", ""),
                "status_code": page.get("status", 200),
                "title": page.get("title"),
                "meta_description": None,
                "h1": None,
                "word_count": page.get("word_count", 0),
                "canonical_url": None,
                "meta_robots": None,
                "internal_links_count": 0,
                "structured_data_count": 0,
                "item_count": page.get("item_count"),
                "error": None,
            },
        )
        pages_saved += 1

    technical_data = audit_data.get("technical", {})
    tech_results = technical_data.get("results", [])
    tech_by_url = {r.get("url"): r for r in tech_results if isinstance(r, dict)}

    sd_data = audit_data.get("structured_data", {})
    sd_results = sd_data.get("results", [])
    sd_by_url = {r.get("url"): r for r in sd_results if isinstance(r, dict)}

    content_urls = {p.get("url") for p in content_pages}
    for url in set(list(tech_by_url.keys()) + list(sd_by_url.keys())):
        if url and url not in content_urls:
            tech = tech_by_url.get(url, {})
            sd = sd_by_url.get(url, {})
            await repo.save_page(
                session_id,
                {
                    "url": url,
                    "status_code": tech.get("status_code", 200),
                    "title": None,
                    "meta_description": None,
                    "h1": None,
                    "word_count": 0,
                    "canonical_url": tech.get("canonical"),
                    "meta_robots": tech.get("meta_robots"),
                    "internal_links_count": 0,
                    "structured_data_count": sd.get("valid_schemas", 0),
                    "item_count": None,
                    "error": None,
                },
            )
            pages_saved += 1

    issues = []
    for page in content_pages:
        for desc in page.get("issues", []):
            issues.append(
                {
                    "issue_type": "content",
                    "severity": "warning",
                    "description": desc,
                    "recommendation": desc,
                    "urls": [page.get("url", "")],
                }
            )

    for key in ["canonical_issues", "meta_robots_issues"]:
        for item in technical_data.get(key, []):
            if isinstance(item, dict):
                issues.append(
                    {
                        "issue_type": "technical",
                        "severity": "warning",
                        "description": item.get("issue", str(item)),
                        "recommendation": item.get("recommendation", "Fix technical issue"),
                        "urls": [item.get("url", "")],
                    }
                )

    links_data = audit_data.get("internal_links", {})
    for orphan_url in links_data.get("orphan_pages", []):
        issues.append(
            {
                "issue_type": "links",
                "severity": "warning",
                "description": f"Orphan page: {orphan_url}",
                "recommendation": "Add internal links pointing to this page",
                "urls": [orphan_url],
            }
        )
    for broken in links_data.get("broken_internal_links", []):
        if isinstance(broken, dict):
            issues.append(
                {
                    "issue_type": "links",
                    "severity": "critical",
                    "description": f"Broken link: {broken.get('url', broken)}",
                    "recommendation": "Fix or remove this broken link",
                    "urls": [broken.get("url", str(broken))],
                }
            )

    for rec in audit_data.get("recommendations", []):
        if isinstance(rec, dict):
            issues.append(
                {
                    "issue_type": "ai_recommendation",
                    "severity": rec.get("priority", "info"),
                    "description": rec.get("title", rec.get("description", str(rec))),
                    "recommendation": rec.get("description", str(rec)),
                    "urls": rec.get("affected_urls", []),
                }
            )

    if issues:
        await repo.save_issues(session_id, issues)

    await repo.finish_session(
        session_id,
        score=overall_score,
        errors_count=len([i for i in issues if i["severity"] == "critical"]),
    )
    await repo.update_progress(session_id, crawled_urls=pages_saved)
    logger.info(
        "Persisted audit: session=%s, pages=%d, issues=%d",
        session_id,
        pages_saved,
        len(issues),
    )
    return session_id
