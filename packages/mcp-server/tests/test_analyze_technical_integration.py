"""seo_analyze/technical must surface the same honesty signals as the audit path.

Lane 1 wired hreflang + raw-vs-rendered diff into the seo_audit path only; these
tests pin the equivalent wiring on the per-page tool, plus the sitemap warning
propagation that stops a partially-resolved sitemap from looking complete.

No network, no browser: everything goes through mocks.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.crawler_service import CrawledPage, CrawlerService
from seo_server.schemas.analyze import SeoAnalyzeInput
from seo_server.tools.analyze import seo_analyze


def _page(url: str = "https://x.com/", status: int = 200) -> CrawledPage:
    return CrawledPage(url=url, status_code=status)


class _Ctx:
    """Minimal ServiceContext stand-in for the technical action."""

    def __init__(self, sitemap_warnings=None):
        self.crawler = SimpleNamespace(
            crawl_pages=AsyncMock(return_value=[_page()]),
            diff_raw_vs_rendered_batch=AsyncMock(
                return_value=[{"url": "https://x.com/", "status": "unavailable"}]
            ),
        )
        self.technical_seo_checker = SimpleNamespace(
            validate_canonicals=lambda pages: [],
            check_meta_robots=lambda pages, sitemap_urls=None: [],
            validate_hreflang=lambda pages=None: [{"type": "missing_x_default"}],
            check_redirect_chain=AsyncMock(return_value={"has_redirect_chain": False}),
        )
        self.sitemap_parser = SimpleNamespace(
            fetch_and_parse=AsyncMock(
                return_value=SimpleNamespace(
                    urls=[SimpleNamespace(loc="https://x.com/")],
                    warnings=sitemap_warnings or [],
                )
            )
        )


async def _run(**kwargs):
    ctx = kwargs.pop("ctx", None) or _Ctx()
    payload = {"action": "technical", "urls": ["https://x.com/"], **kwargs}
    with patch("seo_server.tools.analyze.svc") as mock_svc:
        mock_svc.ctx = ctx
        return await seo_analyze(SeoAnalyzeInput(**payload))


class TestHreflang:
    async def test_hreflang_reported_by_default(self):
        result = await _run()
        assert result["hreflang_issues"] == [{"type": "missing_x_default"}]

    async def test_hreflang_can_be_disabled(self):
        result = await _run(check_hreflang=False)
        assert "hreflang_issues" not in result


class TestRenderDiff:
    async def test_render_diff_is_off_by_default(self):
        """It needs the optional browser crawler — must not fire unasked."""
        ctx = _Ctx()
        result = await _run(ctx=ctx)
        assert "render_diff" not in result
        ctx.crawler.diff_raw_vs_rendered_batch.assert_not_called()

    async def test_render_diff_when_requested(self):
        result = await _run(check_render_diff=True)
        assert result["render_diff"][0]["status"] == "unavailable"


class TestSitemapWarnings:
    async def test_warnings_propagated(self):
        """A truncated sitemap index must never be silent on this path either."""
        ctx = _Ctx(sitemap_warnings=["max depth reached at https://x.com/s2.xml"])
        result = await _run(ctx=ctx, sitemap_url="https://x.com/sitemap.xml")
        assert result["sitemap_warnings"] == ["max depth reached at https://x.com/s2.xml"]

    async def test_no_warnings_key_when_sitemap_is_complete(self):
        ctx = _Ctx(sitemap_warnings=[])
        result = await _run(ctx=ctx, sitemap_url="https://x.com/sitemap.xml")
        assert "sitemap_warnings" not in result

    async def test_meta_robots_still_computed(self):
        """Regression guard: the warning branch must not swallow the robots check."""
        ctx = _Ctx(sitemap_warnings=["truncated"])
        result = await _run(ctx=ctx, sitemap_url="https://x.com/sitemap.xml")
        assert "meta_robots_issues" in result


class TestCrawlerBatchDiff:
    """The sampling logic now lives on the crawler — the orchestrator delegates."""

    async def test_skips_non_200_pages(self):
        crawler = CrawlerService()
        with patch.object(crawler, "diff_raw_vs_rendered", new=AsyncMock()) as diff:
            out = await crawler.diff_raw_vs_rendered_batch([_page(status=404)], sample=2)
        assert out == []
        diff.assert_not_called()

    async def test_honours_sample_size(self):
        crawler = CrawlerService()
        pages = [_page(f"https://x.com/{i}") for i in range(5)]
        with patch.object(
            crawler, "diff_raw_vs_rendered", new=AsyncMock(return_value={"status": "ok"})
        ) as diff:
            out = await crawler.diff_raw_vs_rendered_batch(pages, sample=2)
        assert len(out) == 2
        assert diff.await_count == 2

    async def test_per_page_failure_does_not_raise(self):
        crawler = CrawlerService()
        with patch.object(
            crawler, "diff_raw_vs_rendered", new=AsyncMock(side_effect=RuntimeError("no browser"))
        ):
            out = await crawler.diff_raw_vs_rendered_batch([_page()], sample=1)
        assert out[0]["status"] == "error"
        assert "no browser" in out[0]["reason"]


class TestCorrelationId:
    """Every tool response carries the id that ties its log lines together."""

    async def test_meta_carries_correlation_id(self):
        result = await _run()
        assert result["_meta"]["correlation_id"]

    async def test_error_shape_carries_correlation_id(self):
        ctx = _Ctx()
        ctx.crawler.crawl_pages = AsyncMock(side_effect=RuntimeError("boom"))
        result = await _run(ctx=ctx)
        assert result["error_type"] == "RuntimeError"
        assert result["correlation_id"]


@pytest.mark.parametrize("flag", ["check_hreflang", "check_render_diff"])
def test_new_flags_exposed_in_schema(flag):
    """The MCP schema must advertise the new switches, or no client can use them."""
    assert flag in SeoAnalyzeInput.model_json_schema()["properties"]
