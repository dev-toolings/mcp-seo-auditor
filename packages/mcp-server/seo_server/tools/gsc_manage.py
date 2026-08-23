"""GSC management tool — gsc_manage (sites, sitemaps, inspect)."""

import logging
import os

from seo_server import service_context as svc
from seo_server.gsc_resolve import _resolved_cache as gsc_resolve_cache
from seo_server.gsc_resolve import resolve_site_url
from seo_server.schemas.gsc_manage import GscManageInput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler
from seo_server.tools._gsc_helpers import gsc_credentials_error

logger = logging.getLogger(__name__)


@mcp.tool(
    name="gsc_manage",
    description="""Manage Google Search Console properties, sitemaps, and URL inspection.
IMPORTANT: Always call action='sites' first to discover available GSC properties and get the correct site_url (sc-domain: format preferred).
Actions:
- sites: Manage site properties (sub_action: list/add/delete/details/reauthenticate). Call with sub_action='list' first to get available properties. Use sub_action='reauthenticate' to reset OAuth token without restarting.
- sitemaps: Manage sitemaps (sub_action: list/submit/details). Requires site_url.
- inspect: Inspect URL indexing status. Pass page_url (single) or urls (batch, max 200). Use sub_action='quota' to check daily quota.
- index: Get URLs (re)indexed (sub_action varies by provider). provider='google' (default) = Google Indexing API (notify/status, index_type URL_UPDATED/URL_DELETED) — only honoured for JobPosting/BroadcastEvent pages, requires the service account to be an Owner. provider='rapid' = Rapid URL Indexer, a pay-per-success third-party indexer that works for REGULAR pages (sub_action notify/submit to create a project from page_url/urls, status/report with project_id, credits for balance).""",
)
@tool_handler
async def gsc_manage(input: GscManageInput) -> dict:
    if not svc.ctx.gsc.is_credentials_available:
        return gsc_credentials_error()

    # Auto-resolve site_url to sc-domain: format — skip for sites/delete and sites/add
    # to allow targeting a specific property format (e.g. URL property vs domain property)
    site_url = input.site_url
    skip_resolve = input.action == "sites" and input.sub_action in ("delete", "add")
    if site_url and not skip_resolve:
        site_url = await resolve_site_url(site_url)

    action = input.action
    if action == "sites":
        return await _manage_sites(input.sub_action, site_url)
    elif action == "sitemaps":
        return await _manage_sitemaps(
            site_url, input.sub_action, input.sitemap_url, input.sitemap_index
        )
    elif action == "inspect":
        return await _manage_inspect(
            site_url, input.sub_action, input.page_url, input.urls, input.force_refresh
        )
    elif action == "index":
        return await _manage_index(
            input.sub_action,
            input.page_url,
            input.urls,
            input.index_type,
            input.provider,
            input.project_id,
        )
    else:
        return {"error": f"Unknown action: {action}. Use: sites, sitemaps, inspect, index"}


async def _manage_sites(sub_action: str | None, site_url: str | None) -> dict:
    """Manage GSC site properties — absorbs gsc_sites."""
    sub_action = sub_action or "list"

    if sub_action == "list":
        sites = await svc.ctx.gsc.list_sites()
        return {"sites": sites, "count": len(sites)}

    if sub_action == "reauthenticate":
        return await _reauthenticate()

    if not site_url:
        return {"error": "site_url is required for add/delete/details"}

    if sub_action == "add":
        return await svc.ctx.gsc.add_site(site_url)
    elif sub_action == "delete":
        return await svc.ctx.gsc.delete_site(site_url)
    elif sub_action == "details":
        return await svc.ctx.gsc.get_site_details(site_url)
    else:
        return {
            "error": f"Unknown sub_action: {sub_action}. Use: list, add, delete, details, reauthenticate"
        }


async def _reauthenticate() -> dict:
    """Reset OAuth token and re-authenticate."""
    gsc = svc.ctx.gsc
    token_deleted = False

    token_path = os.path.join(os.getcwd(), gsc.oauth_token_file)
    if os.path.exists(token_path):
        os.remove(token_path)
        token_deleted = True

    gsc._service = None
    gsc_resolve_cache.clear()

    if not gsc.oauth_client_secrets or not os.path.exists(gsc.oauth_client_secrets):
        return {
            "success": False,
            "error": "OAuth client secrets file not found. Set GSC_OAUTH_CLIENT_SECRETS_FILE.",
        }

    try:
        gsc._get_service()
        msg = "Successfully re-authenticated with GSC."
        if token_deleted:
            msg = "Previous token deleted. " + msg
        return {"success": True, "message": msg}
    except Exception as e:
        return {"success": False, "error": f"Re-authentication failed: {e}"}


async def _manage_sitemaps(
    site_url: str | None,
    sub_action: str | None,
    sitemap_url: str | None,
    sitemap_index: str | None,
) -> dict:
    """Manage GSC sitemaps — absorbs gsc_sitemaps."""
    if not site_url:
        return {"error": "site_url is required for sitemaps action"}
    sub_action = sub_action or "list"

    if sub_action == "list":
        return await svc.ctx.gsc.list_sitemaps_enhanced(site_url, sitemap_index)
    elif sub_action == "submit":
        if not sitemap_url:
            return {"error": "sitemap_url is required for submit"}
        return await svc.ctx.gsc.submit_sitemap(site_url, sitemap_url)
    elif sub_action == "details":
        if not sitemap_url:
            return {"error": "sitemap_url is required for details"}
        return await svc.ctx.gsc.get_sitemap_details(site_url, sitemap_url)
    else:
        return {"error": f"Unknown sub_action: {sub_action}. Use: list, submit, details"}


async def _manage_inspect(
    site_url: str | None,
    sub_action: str | None,
    page_url: str | None,
    urls: list[str] | None,
    force_refresh: bool,
) -> dict:
    """URL inspection — absorbs gsc_inspect."""
    if not site_url:
        return {"error": "site_url is required for inspect action"}

    sub_action = sub_action or "inspect"
    repo = svc.ctx.crawl_repository

    if sub_action == "quota":
        quota_used = await repo.get_quota_usage(site_url)
        return {
            "site_url": site_url,
            "quota": {"used": quota_used, "limit": 2000, "remaining": 2000 - quota_used},
        }

    if page_url:
        if force_refresh:
            result = await svc.ctx.gsc.inspect_url(site_url, page_url)
            await repo.cache_inspection(site_url, page_url, result)
            await repo.increment_quota(site_url)
            result["_from_cache"] = False
            return result
        return await svc.ctx.gsc.inspect_url_cached(site_url, page_url, repo)
    elif urls:
        if force_refresh:
            results = {}
            batch_urls = urls[:200]
            for url in batch_urls:
                try:
                    result = await svc.ctx.gsc.inspect_url(site_url, url)
                    await repo.cache_inspection(site_url, url, result)
                    await repo.increment_quota(site_url)
                    result["_from_cache"] = False
                    results[url] = result
                except Exception as e:
                    results[url] = {"error": str(e), "_from_cache": False}
            quota_used = await repo.get_quota_usage(site_url)
            return {
                "results": results,
                "stats": {
                    "total": len(batch_urls),
                    "from_cache": 0,
                    "from_api": sum(1 for r in results.values() if "error" not in r),
                    "skipped": 0,
                    "errors": sum(1 for r in results.values() if "error" in r),
                },
                "quota": {"used": quota_used, "limit": 2000, "remaining": 2000 - quota_used},
            }
        return await svc.ctx.gsc.batch_inspect_cached(site_url, urls[:200], repo)
    else:
        return {"error": "Provide page_url (single) or urls (batch), or use sub_action='quota'"}


async def _manage_index(
    sub_action: str | None,
    page_url: str | None,
    urls: list[str] | None,
    index_type: str,
    provider: str = "google",
    project_id: int | None = None,
) -> dict:
    """Get URLs (re)indexed via the Google Indexing API or Rapid URL Indexer.

    provider='google' (default) uses urlNotifications:publish — officially
    honoured only for JobPosting/BroadcastEvent pages, requires the service
    account to be an Owner, daily quota 200 URLs. provider='rapid' uses the
    Rapid URL Indexer pay-per-success API, which works for regular pages.
    """
    if provider == "rapid":
        return await _manage_index_rapid(sub_action, page_url, urls, project_id)

    sub_action = sub_action or "notify"
    gsc = svc.ctx.gsc

    if sub_action == "status":
        if not page_url:
            return {"error": "page_url is required for index status"}
        return await gsc.get_index_notification_status(page_url)

    if sub_action != "notify":
        return {"error": f"Unknown sub_action: {sub_action}. Use: notify, status"}

    note = (
        "Indexing API officially supports only JobPosting/BroadcastEvent pages; "
        "other pages may be ignored. Daily quota: 200 URLs."
    )

    if page_url:
        result = await gsc.notify_index_update(page_url, index_type)
        result["note"] = note
        return result
    elif urls:
        batch = urls[:200]
        results = {url: await gsc.notify_index_update(url, index_type) for url in batch}
        succeeded = sum(1 for r in results.values() if r.get("success"))
        return {
            "results": results,
            "type": index_type,
            "stats": {
                "total": len(batch),
                "succeeded": succeeded,
                "failed": len(batch) - succeeded,
            },
            "note": note,
        }
    else:
        return {"error": "Provide page_url (single) or urls (batch) for notify"}


async def _manage_index_rapid(
    sub_action: str | None,
    page_url: str | None,
    urls: list[str] | None,
    project_id: int | None,
) -> dict:
    """Rapid URL Indexer — pay-per-success bulk indexer for regular pages.

    sub_action: notify/submit (create a project from page_url/urls), status
    (project state via project_id), report (per-URL, project_id), credits.
    """
    sub_action = sub_action or "notify"
    indexer = svc.ctx.rapid_indexer

    if not indexer.is_configured:
        return {
            "error": "RAPID_URL_INDEXER_API_KEY not configured. "
            "See docs/INDEXING_API_SETUP.md (Rapid URL Indexer section)."
        }

    if sub_action == "credits":
        return await indexer.get_credits()

    if sub_action == "status":
        if project_id is None:
            return {"error": "project_id is required for status"}
        return await indexer.get_status(project_id)

    if sub_action == "report":
        if project_id is None:
            return {"error": "project_id is required for report"}
        return await indexer.get_report(project_id)

    if sub_action in ("notify", "submit"):
        batch = list(urls or [])
        if page_url:
            batch.append(page_url)
        if not batch:
            return {"error": "Provide page_url (single) or urls (batch) to submit"}
        return await indexer.submit(batch)

    return {"error": f"Unknown sub_action: {sub_action}. Use: notify, status, report, credits"}
