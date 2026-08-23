"""Crawl tool — seo_crawl (crawl session data access, 5 actions)."""

import logging

from seo_server import service_context as svc
from seo_server.schemas.crawl import SeoCrawlInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_crawl",
    description="""Access and analyze crawl session data.
Actions:
- list: List past crawl sessions with scores and dates. Optional site_url filter.
- get: Get detailed session info (pages, issues). Requires crawl_id. Also retrieves reports by audit_id.
- compare: Compare two crawl sessions (score delta, pages added/removed). Requires crawl_id_1 + crawl_id_2.
- trends: SEO score evolution over time. Requires site_url.
- alerts: Detect regressions (score drops, error increases). Requires site_url.""",
)
@tool_handler
async def seo_crawl(input: SeoCrawlInput) -> dict:
    action = input.action
    if action == "list":
        return await _crawl_list(input)
    elif action == "get":
        return await _crawl_get(input)
    elif action == "compare":
        return await _crawl_compare(input)
    elif action == "trends":
        return await _crawl_trends(input)
    elif action == "alerts":
        return await _crawl_alerts(input)
    else:
        return {"error": f"Unknown action: {action}. Use: list, get, compare, trends, alerts"}


async def _crawl_list(input: SeoCrawlInput) -> dict:
    """List crawl sessions — absorbs crawl_data list action."""
    sessions = await svc.ctx.crawl_repository.list_sessions(
        site_url=input.site_url, limit=input.limit
    )
    return {"total": len(sessions), "sessions": sessions}


async def _crawl_get(input: SeoCrawlInput) -> dict:
    """Get session or report — absorbs crawl_data get + seo_get_report."""
    audit_id = input.audit_id
    if audit_id:
        report = await svc.ctx.report_repository.get(audit_id)
        if report is None:
            return {
                "error": f"Report not found: {audit_id}",
                "error_type": "ReportNotFound",
                "recoverable": True,
            }
        return {
            "audit_id": report.audit_id,
            "audit_type": report.audit_type.value,
            "score": report.score,
            "created_at": report.created_at.isoformat(),
            "total_urls": report.total_urls,
            "issues_critical": report.issues_critical,
            "issues_warning": report.issues_warning,
            "recommendations": report.recommendations,
        }

    crawl_id = input.crawl_id
    if not crawl_id:
        return {"error": "crawl_id or audit_id is required for get action"}
    session = await svc.ctx.crawl_repository.get_session(crawl_id)
    if not session:
        return {"error": f"Crawl session not found: {crawl_id}"}
    issues = await svc.ctx.crawl_repository.get_issues(crawl_id)
    pages_data = await svc.ctx.crawl_repository.get_pages(crawl_id, page=1, per_page=50)
    return {"session": session, "issues": issues, "pages": pages_data}


async def _crawl_compare(input: SeoCrawlInput) -> dict:
    """Compare sessions — absorbs crawl_analysis compare + seo_audit_compare."""
    crawl_id_1 = input.crawl_id_1
    crawl_id_2 = input.crawl_id_2
    if not crawl_id_1 or not crawl_id_2:
        return {"error": "crawl_id_1 and crawl_id_2 are required for compare action"}

    repo = svc.ctx.crawl_repository
    await repo.initialize()

    session1 = await repo.get_session(crawl_id_1)
    session2 = await repo.get_session(crawl_id_2)
    if not session1:
        return {"error": f"Crawl session not found: {crawl_id_1}"}
    if not session2:
        return {"error": f"Crawl session not found: {crawl_id_2}"}

    pages1_data = await repo.get_pages(crawl_id_1, per_page=10000)
    pages2_data = await repo.get_pages(crawl_id_2, per_page=10000)
    urls1 = {p["url"] for p in pages1_data["pages"]}
    urls2 = {p["url"] for p in pages2_data["pages"]}

    issues1 = (await repo.get_issues(crawl_id_1))["issues"]
    issues2 = (await repo.get_issues(crawl_id_2))["issues"]
    issues1_types = {i["issue_type"] for i in issues1}
    issues2_types = {i["issue_type"] for i in issues2}

    score_1 = session1.get("score") or 0
    score_2 = session2.get("score") or 0
    score_delta = score_2 - score_1

    improvements = []
    regressions = []
    if score_delta > 0:
        improvements.append(f"Score improved by {score_delta} points")
    elif score_delta < 0:
        regressions.append(f"Score dropped by {abs(score_delta)} points")

    issues_delta = len(issues2) - len(issues1)
    if issues_delta < 0:
        improvements.append(f"{abs(issues_delta)} fewer issues")
    elif issues_delta > 0:
        regressions.append(f"{issues_delta} more issues")

    pages_delta = len(urls2) - len(urls1)
    if pages_delta > 0:
        improvements.append(f"{pages_delta} more pages")

    return {
        "session1": session1,
        "session2": session2,
        "score_delta": score_delta,
        "pages_added": sorted(urls2 - urls1),
        "pages_removed": sorted(urls1 - urls2),
        "new_issues": [i for i in issues2 if i["issue_type"] not in issues1_types],
        "resolved_issues": [i for i in issues1 if i["issue_type"] not in issues2_types],
        "issues_count_delta": issues_delta,
        "improvements": improvements,
        "regressions": regressions,
        "trend": "improving" if score_delta > 0 else ("declining" if score_delta < 0 else "stable"),
    }


async def _crawl_trends(input: SeoCrawlInput) -> dict:
    """Score trends — absorbs crawl_analysis trends action."""
    site_url = input.site_url
    if not site_url:
        return {"error": "site_url is required for trends action"}
    days = input.days
    trends = await svc.ctx.crawl_repository.get_trends(site_url, days=days)
    return {"site_url": site_url, "days": days, "data_points": len(trends), "trends": trends}


async def _crawl_alerts(input: SeoCrawlInput) -> dict:
    """Regression alerts — absorbs crawl_analysis alerts action."""
    site_url = input.site_url
    if not site_url:
        return {"error": "site_url is required for alerts action"}

    repo = svc.ctx.crawl_repository
    sessions = await repo.list_sessions(site_url=site_url, limit=5)
    completed = [s for s in sessions if s["status"] == "completed" and s.get("score") is not None]

    if len(completed) < 2:
        return {
            "site_url": site_url,
            "alerts": [],
            "message": "Not enough completed crawls to detect regressions (need at least 2)",
        }

    latest, previous = completed[0], completed[1]
    alerts = []

    score_delta = (latest.get("score") or 0) - (previous.get("score") or 0)
    if score_delta <= -10:
        alerts.append(
            {
                "type": "score_drop",
                "severity": "critical",
                "message": f"Score dropped by {abs(score_delta)} points (from {previous.get('score')} to {latest.get('score')})",
                "crawl_id": latest["id"],
            }
        )
    elif score_delta <= -5:
        alerts.append(
            {
                "type": "score_drop",
                "severity": "warning",
                "message": f"Score dropped by {abs(score_delta)} points (from {previous.get('score')} to {latest.get('score')})",
                "crawl_id": latest["id"],
            }
        )

    errors_delta = latest.get("errors_count", 0) - previous.get("errors_count", 0)
    if errors_delta > 0:
        alerts.append(
            {
                "type": "errors_increase",
                "severity": "warning",
                "message": f"{errors_delta} new error(s) detected",
                "crawl_id": latest["id"],
            }
        )

    latest_issues = (await repo.get_issues(latest["id"]))["issues"]
    previous_issues = (await repo.get_issues(previous["id"]))["issues"]
    prev_types = {i["issue_type"] for i in previous_issues}
    new_critical = [
        i
        for i in latest_issues
        if i["severity"] == "critical" and i["issue_type"] not in prev_types
    ]
    if new_critical:
        alerts.append(
            {
                "type": "new_critical_issues",
                "severity": "critical",
                "message": f"{len(new_critical)} new critical issue(s): "
                + ", ".join(i["issue_type"] for i in new_critical),
                "crawl_id": latest["id"],
            }
        )

    return {
        "site_url": site_url,
        "latest_crawl": latest["id"],
        "previous_crawl": previous["id"],
        "alerts": alerts,
        "alert_count": len(alerts),
    }
