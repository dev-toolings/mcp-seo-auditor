"""Tests for the Indexing API integration (gsc_manage action='index')."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import google_search_console as gsc_mod
from seo_server.tools.gsc_manage import _manage_index


def _patched_svc(gsc):
    """Patch the gsc_manage module-level service container to use `gsc`."""
    mock_svc = MagicMock()
    mock_svc.ctx.gsc = gsc
    return patch("seo_server.tools.gsc_manage.svc", mock_svc)


class TestManageIndexHandler:
    @pytest.mark.asyncio
    async def test_notify_single_url(self):
        gsc = AsyncMock()
        gsc.notify_index_update = AsyncMock(
            return_value={"success": True, "url": "https://x.fr/a", "type": "URL_UPDATED"}
        )
        with _patched_svc(gsc):
            result = await _manage_index("notify", "https://x.fr/a", None, "URL_UPDATED")
        gsc.notify_index_update.assert_awaited_once_with("https://x.fr/a", "URL_UPDATED")
        assert result["success"] is True
        assert "note" in result

    @pytest.mark.asyncio
    async def test_notify_batch_counts(self):
        gsc = AsyncMock()
        gsc.notify_index_update = AsyncMock(
            side_effect=lambda url, t: {"success": url.endswith("ok"), "url": url}
        )
        with _patched_svc(gsc):
            result = await _manage_index(
                "notify", None, ["https://x.fr/ok", "https://x.fr/bad"], "URL_DELETED"
            )
        assert result["type"] == "URL_DELETED"
        assert result["stats"] == {"total": 2, "succeeded": 1, "failed": 1}

    @pytest.mark.asyncio
    async def test_status_requires_page_url(self):
        with _patched_svc(AsyncMock()):
            result = await _manage_index("status", None, None, "URL_UPDATED")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_sub_action(self):
        with _patched_svc(AsyncMock()):
            result = await _manage_index("bogus", "https://x.fr/a", None, "URL_UPDATED")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_notify_without_url_errors(self):
        with _patched_svc(AsyncMock()):
            result = await _manage_index("notify", None, None, "URL_UPDATED")
        assert "error" in result


class TestNotifyIndexUpdateService:
    @pytest.mark.asyncio
    async def test_rejects_invalid_type(self):
        service = gsc_mod.GoogleSearchConsoleService(credentials_path="/fake.json")
        with patch.object(type(service), "is_credentials_available", property(lambda self: True)):
            out = await service.notify_index_update("https://x.fr/a", "BOGUS")
        assert out["success"] is False
        assert "URL_UPDATED" in out["error"]

    @pytest.mark.asyncio
    async def test_publishes_expected_body(self):
        service = gsc_mod.GoogleSearchConsoleService(credentials_path="/fake.json")
        fake_service = MagicMock()
        publish = fake_service.urlNotifications.return_value.publish

        with (
            patch.object(type(service), "is_credentials_available", property(lambda self: True)),
            patch.object(service, "_get_indexing_service", return_value=fake_service),
            patch.object(
                type(service),
                "_execute_with_retry",
                staticmethod(
                    lambda req: {
                        "urlNotificationMetadata": {
                            "latestUpdate": {"notifyTime": "2026-06-22T10:00:00Z"}
                        }
                    }
                ),
            ),
        ):
            out = await service.notify_index_update("https://x.fr/a", "URL_UPDATED")

        publish.assert_called_once_with(body={"url": "https://x.fr/a", "type": "URL_UPDATED"})
        assert out == {
            "success": True,
            "url": "https://x.fr/a",
            "type": "URL_UPDATED",
            "notify_time": "2026-06-22T10:00:00Z",
        }

