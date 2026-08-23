"""Tests for GSC enrichment in full audit pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ai.full_audit import FullAuditService
from app.services.google_search_console import PagePerformance, QueryPerformance


def _make_service(gsc_available=True, top_pages=None, top_queries=None):
    """Create a FullAuditService with mocked dependencies."""
    orchestrator = MagicMock()
    gsc = AsyncMock()
    gsc.is_credentials_available = gsc_available
    gsc.get_top_pages = AsyncMock(return_value=top_pages or [])
    gsc.get_top_queries = AsyncMock(return_value=top_queries or [])
    orchestrator._ctx = MagicMock()
    orchestrator._ctx.gsc = gsc

    geo = MagicMock()
    ai = MagicMock()
    return FullAuditService(orchestrator, geo, ai)


class TestFetchGscSummary:
    @pytest.mark.asyncio
    async def test_returns_none_when_credentials_unavailable(self):
        service = _make_service(gsc_available=False)
        result = await service._fetch_gsc_summary("https://example.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data(self):
        service = _make_service(gsc_available=True, top_pages=[], top_queries=[])
        with patch(
            "seo_server.gsc_resolve.resolve_site_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = "sc-domain:example.com"
            result = await service._fetch_gsc_summary("https://example.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_summary_with_data(self):
        pages = [
            PagePerformance(
                url="https://example.com/a", clicks=100, impressions=5000, ctr=0.02, position=3.0
            ),
            PagePerformance(
                url="https://example.com/b", clicks=5, impressions=500, ctr=0.01, position=8.0
            ),
            PagePerformance(
                url="https://example.com/c", clicks=0, impressions=200, ctr=0.0, position=15.0
            ),
        ]
        queries = [
            QueryPerformance(
                query="example query", clicks=50, impressions=2000, ctr=0.025, position=4.0
            ),
        ]
        service = _make_service(gsc_available=True, top_pages=pages, top_queries=queries)

        with patch(
            "seo_server.gsc_resolve.resolve_site_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = "sc-domain:example.com"
            result = await service._fetch_gsc_summary("https://example.com/sitemap.xml")

        assert result is not None
        assert result["site_totals"]["clicks_28d"] == 105
        assert result["site_totals"]["impressions_28d"] == 5700
        assert len(result["top_pages"]) == 3
        assert len(result["top_queries"]) == 1
        # Pages b and c have impressions > 100 and CTR < 2%
        assert len(result["low_ctr_opportunities"]) == 2

    @pytest.mark.asyncio
    async def test_returns_none_on_resolve_error(self):
        service = _make_service(gsc_available=True)
        with patch(
            "seo_server.gsc_resolve.resolve_site_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.side_effect = Exception("resolve failed")
            result = await service._fetch_gsc_summary("https://example.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_gsc_fetch_error(self):
        service = _make_service(gsc_available=True)
        service.orchestrator._ctx.gsc.get_top_pages.side_effect = Exception("API error")
        with patch(
            "seo_server.gsc_resolve.resolve_site_url", new_callable=AsyncMock
        ) as mock_resolve:
            mock_resolve.return_value = "sc-domain:example.com"
            result = await service._fetch_gsc_summary("https://example.com/sitemap.xml")
        assert result is None
