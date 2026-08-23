"""Rapid URL Indexer — pay-per-success bulk indexer for regular pages.

The Google Indexing API officially honours only JobPosting / BroadcastEvent
pages; for ordinary content (articles, landing pages) Google ignores it. The
reliable programmatic option at scale is a third-party indexer. Rapid URL
Indexer (https://rapidurlindexer.com) exposes a REST API, charges per
successfully indexed URL, and auto-refunds URLs not indexed within 14 days.

API key via RAPID_URL_INDEXER_API_KEY. The service degrades gracefully when
the key is absent (every method returns a structured error, never raises).
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_URLS_PER_PROJECT = 9999

_ERROR_MESSAGES = {
    400: "Malformed request (invalid project name or URLs).",
    401: "Invalid or missing API key (RAPID_URL_INDEXER_API_KEY).",
    403: "Insufficient credits on the Rapid URL Indexer account.",
    404: "Resource not found (check project_id).",
    425: "Report not ready yet — available 96h after project creation.",
    429: "Rate limit exceeded (100 requests/minute).",
}


class RapidUrlIndexerService:
    """Thin async client over the Rapid URL Indexer REST API."""

    def __init__(self):
        self._api_key = settings.RAPID_URL_INDEXER_API_KEY.get_secret_value()
        self._base_url = settings.RAPID_URL_INDEXER_BASE_URL.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _call(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        accept: str | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured:
            return {
                "success": False,
                "error": "RAPID_URL_INDEXER_API_KEY not configured.",
            }
        headers = {"X-API-Key": self._api_key, "Content-Type": "application/json"}
        if accept:
            headers["Accept"] = accept
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method, f"{self._base_url}{path}", headers=headers, json=json
                )
        except httpx.HTTPError as e:
            return {"success": False, "error": f"Request failed: {e}"}

        if resp.status_code >= 400:
            msg = _ERROR_MESSAGES.get(resp.status_code, f"HTTP {resp.status_code}")
            return {"success": False, "status_code": resp.status_code, "error": msg}
        try:
            return resp.json()
        except ValueError:
            return {"success": False, "error": "Invalid JSON response from indexer."}

    async def submit(
        self,
        urls: list[str],
        project_name: str | None = None,
        apex_mode: bool = False,
        notify: bool = False,
    ) -> dict[str, Any]:
        """Create an indexing project for a batch of URLs (max 9,999)."""
        clean = [u for u in urls if u.startswith(("http://", "https://"))][:MAX_URLS_PER_PROJECT]
        if not clean:
            return {"success": False, "error": "No valid http(s) URLs to submit."}

        result = await self._call(
            "POST",
            "/api/v1/projects",
            json={
                "project_name": project_name or "mcp-seo-auditor",
                "urls": clean,
                "notify_on_status_change": notify,
                "apex_mode_enabled": apex_mode,
            },
        )
        if "project_id" in result:
            result["success"] = True
            result["submitted"] = len(clean)
        return result

    async def get_status(self, project_id: int) -> dict[str, Any]:
        """Return project-level status (indexed_links / submitted_links)."""
        return await self._call("GET", f"/api/v1/projects/{project_id}")

    async def get_report(self, project_id: int) -> dict[str, Any]:
        """Return the per-URL indexed/not_indexed report (ready 96h after submit)."""
        return await self._call(
            "GET", f"/api/v1/projects/{project_id}/report", accept="application/json"
        )

    async def get_credits(self) -> dict[str, Any]:
        """Return the remaining credit balance."""
        return await self._call("GET", "/api/v1/credits/balance")
