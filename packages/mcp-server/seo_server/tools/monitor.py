"""Monitor tool — seo_monitor (anomaly detection + fix verification, 3 actions)."""

import logging

from seo_server import service_context as svc
from seo_server.gsc_resolve import resolve_site_url
from seo_server.schemas.monitor import SeoMonitorInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler

logger = logging.getLogger(__name__)


@mcp.tool(
    name="seo_monitor",
    description="""SEO monitoring: anomaly detection and fix verification.
Actions:
- anomalies: AI-powered anomaly detection on keyword performance over time. Requires keywords.
- detect: Detect SEO issues on a URL (e.g. indexation leaks). Requires url.
- verify: Verify that previously detected issues are fixed. Requires url.""",
)
@tool_handler
async def seo_monitor(input: SeoMonitorInput) -> dict:
    site_url = input.site_url
    if site_url:
        site_url = await resolve_site_url(site_url)

    action = input.action
    if action == "anomalies":
        return await _monitor_anomalies(input.keywords, input.days_back, site_url)
    elif action == "detect":
        return await _monitor_detect(input.url, site_url, input.issue_type)
    elif action == "verify":
        return await _monitor_verify(input.url, site_url, input.issue_type)
    else:
        return {"error": f"Unknown action: {action}. Use: anomalies, detect, verify"}


async def _monitor_anomalies(
    keywords: list[str] | None, days_back: int, site_url: str | None
) -> dict:
    """AI anomaly detection — absorbs seo_ai_monitor."""
    if not keywords:
        return {"error": "keywords is required for anomalies action"}
    try:
        return await svc.ctx.anomaly_detector.detect(
            keywords,
            days_back,
            site_url=site_url,
        )
    except Exception as e:
        logger.exception("Monitor anomalies failed")
        return {"error": str(e)}


async def _monitor_detect(url: str | None, site_url: str | None, issue_type: str) -> dict:
    """Detect issues — absorbs seo_fix_and_verify detect mode."""
    if not url:
        return {"error": "url is required for detect action"}
    site_url = site_url or ""

    issues: list[dict] = []

    if issue_type == "indexation_leak":
        from urllib.parse import urlparse

        pages = await svc.ctx.crawler.crawl_pages([url])
        if pages:
            page = pages[0]
            parsed = urlparse(url)
            root_url = f"{parsed.scheme}://{parsed.netloc}"
            disallow_patterns: list[str] = []
            try:
                robots_data = await svc.ctx.technical_seo_checker.parse_robots_txt(root_url)
                for rule in robots_data.get("rules", []):
                    if (
                        rule.get("user_agent") == "*"
                        and rule.get("directive") == "disallow"
                        and rule.get("path")
                    ):
                        disallow_patterns.append(rule["path"])
                disallow_patterns = list(set(disallow_patterns))
            except Exception as e:
                logger.warning("Failed to fetch robots.txt: %s", e)

            report = svc.ctx.indexation_leak_detector.detect_leaks(
                source_pages=[page],
                disallow_patterns=disallow_patterns,
            )
            for leak in report.get("leaks", []):
                issues.append(
                    {
                        "type": "indexation_leak",
                        "severity": leak.get("severity", "medium"),
                        "description": leak.get("description", ""),
                        "recommendation": leak.get("recommendation", ""),
                        "code_hint": leak.get("code_hint", ""),
                    }
                )

    elif issue_type == "canonical":
        pages = await svc.ctx.crawler.crawl_pages([url])
        for problem in svc.ctx.technical_seo_checker.validate_canonicals(pages):
            issues.append(
                {
                    "type": "canonical",
                    "severity": problem.get("severity", "medium"),
                    "description": problem.get(
                        "issue", problem.get("description", "Canonical issue")
                    ),
                    "recommendation": problem.get(
                        "recommendation", "Set a self-referencing canonical to the preferred URL."
                    ),
                    "code_hint": '<link rel="canonical" href="...">',
                }
            )

    elif issue_type == "redirect_chain":
        chain = await svc.ctx.technical_seo_checker.check_redirect_chain(url)
        if chain.get("has_redirect_chain"):
            issues.append(
                {
                    "type": "redirect_chain",
                    "severity": "medium",
                    "description": (
                        f"Redirect chain of {chain.get('redirects', 0)} hops "
                        f"from {chain.get('initial_url')} to {chain.get('final_url')}."
                    ),
                    "recommendation": "Collapse to a single 301 hop to the final URL.",
                    "code_hint": str(chain.get("chain", [])),
                }
            )

    elif issue_type == "thin_content":
        pages = await svc.ctx.crawler.crawl_pages([url])
        for page in pages:
            for problem in svc.ctx.content_validator.validate(page, check_thin_content=True):
                if problem.issue_type in ("empty_page", "thin_content"):
                    issues.append(
                        {
                            "type": "thin_content",
                            "severity": problem.severity,
                            "description": problem.description,
                            "recommendation": problem.recommendation,
                            "code_hint": "",
                        }
                    )

    gsc_data = None
    if site_url and svc.ctx.gsc.is_credentials_available:
        try:
            repo = svc.ctx.crawl_repository
            await repo.initialize()
            gsc_data = await svc.ctx.gsc.inspect_url_cached(site_url, url, repo)
        except Exception:
            pass

    return {
        "url": url,
        "mode": "detect",
        "issue_type": issue_type,
        "issues_found": len(issues),
        "issues": issues,
        "gsc_status": (
            {
                "verdict": gsc_data.get("verdict") if gsc_data else None,
                "coverage_state": gsc_data.get("coverage_state") if gsc_data else None,
                "from_cache": gsc_data.get("_from_cache") if gsc_data else None,
            }
            if gsc_data
            else None
        ),
        "suggestions": [
            {
                "file_pattern": issue.get("code_hint", ""),
                "severity": issue["severity"],
                "fix": issue["recommendation"],
            }
            for issue in issues
        ],
    }


async def _monitor_verify(url: str | None, site_url: str | None, issue_type: str) -> dict:
    """Verify fixes — absorbs seo_fix_and_verify verify mode."""
    if not url:
        return {"error": "url is required for verify action"}
    site_url = site_url or ""

    current = await _monitor_detect(url, site_url, issue_type)

    previous_issues_count = None
    if site_url and svc.ctx.crawl_repository:
        try:
            repo = svc.ctx.crawl_repository
            await repo.initialize()
            cached = await repo.get_cached_inspection(site_url, url)
            if cached:
                previous_issues_count = cached.get("_issues_count")
        except Exception:
            pass

    return {
        "url": url,
        "mode": "verify",
        "issue_type": issue_type,
        "current_issues": current["issues_found"],
        "previous_issues": previous_issues_count,
        "fixed": current["issues_found"] == 0,
        "remaining_issues": current["issues"],
        "improvement": (
            f"Reduced from {previous_issues_count} to {current['issues_found']}"
            if previous_issues_count is not None
            else "No previous baseline available"
        ),
        "gsc_status": current.get("gsc_status"),
    }
