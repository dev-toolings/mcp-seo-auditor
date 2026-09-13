"""Tests for CrawlerService with ghostchrome as the primary crawler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.crawler_service import CrawledPage, CrawlerService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crawler() -> CrawlerService:
    """Instantiate CrawlerService without touching external settings."""
    return CrawlerService()


SAMPLE_HTML = (
    "<html><head><title>Test Page</title></head>"
    "<body><main>" + " ".join(["content"] * 100) + "</main></body></html>"
)


# ---------------------------------------------------------------------------
# crawl_pages — ghostchrome as primary crawler
# ---------------------------------------------------------------------------


class TestCrawlPagesBrowser:
    """Verify crawl_pages uses BrowserCrawler for every page."""

    async def test_all_pages_are_js_rendered(self):
        """Every crawled page has js_rendered=True."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(return_value=(SAMPLE_HTML, 200, "https://example.com"))
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://example.com"])

        assert len(pages) == 1
        assert pages[0].js_rendered is True

    async def test_parse_html_extracts_title(self):
        """_parse_html is called and extracts the title from ghostchrome HTML."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(return_value=(SAMPLE_HTML, 200, "https://example.com"))
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://example.com"])

        assert pages[0].title == "Test Page"
        assert pages[0].word_count > 0

    async def test_callback_is_invoked(self):
        """on_page_crawled callback receives correct count and total."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(return_value=(SAMPLE_HTML, 200, "https://a.com"))
        crawler._browser_crawler = mock_browser

        callback = AsyncMock()
        await crawler.crawl_pages(["https://a.com"], on_page_crawled=callback)

        callback.assert_called_once()
        args = callback.call_args[0]
        assert isinstance(args[0], CrawledPage)
        assert args[1] == 1  # crawled_count
        assert args[2] == 1  # total

    async def test_multiple_urls_all_crawled(self):
        """Multiple URLs are all crawled via ghostchrome."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(
            side_effect=[
                (SAMPLE_HTML, 200, "https://a.com"),
                (SAMPLE_HTML, 200, "https://b.com"),
            ]
        )
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://a.com", "https://b.com"])

        assert len(pages) == 2
        assert all(p.js_rendered is True for p in pages)
        assert mock_browser.crawl_page.call_count == 2

    async def test_non_200_status_no_parse(self):
        """A non-200 response does not populate content fields."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(return_value=("", 404, "https://example.com/missing"))
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://example.com/missing"])

        assert pages[0].status_code == 404
        assert pages[0].word_count == 0
        assert pages[0].title is None

    async def test_final_url_set_on_redirect(self):
        """final_url is set when the browser lands on a different URL."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(
            return_value=(SAMPLE_HTML, 200, "https://example.com/redirected")
        )
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://example.com/original"])

        assert pages[0].final_url == "https://example.com/redirected"

    async def test_final_url_none_when_no_redirect(self):
        """final_url is None when the URL doesn't change."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(return_value=(SAMPLE_HTML, 200, "https://example.com"))
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://example.com"])

        assert pages[0].final_url is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestCrawlPagesErrorHandling:
    """Verify error handling when crawl_page raises."""

    async def test_exception_returns_error_page(self):
        """A crawl_page exception produces CrawledPage with status=0 and error."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(side_effect=TimeoutError("Page timeout"))
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://slow.com"])

        assert len(pages) == 1
        assert pages[0].status_code == 0
        assert "Page timeout" in pages[0].error

    async def test_mixed_success_and_failure(self):
        """One success and one failure produce correct results."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        mock_browser.crawl_page = AsyncMock(
            side_effect=[
                (SAMPLE_HTML, 200, "https://ok.com"),
                ConnectionError("refused"),
            ]
        )
        crawler._browser_crawler = mock_browser

        pages = await crawler.crawl_pages(["https://ok.com", "https://fail.com"])

        assert pages[0].status_code == 200
        assert pages[0].js_rendered is True
        assert pages[1].status_code == 0
        assert pages[1].error is not None


# ---------------------------------------------------------------------------
# ghostchrome unavailable
# ---------------------------------------------------------------------------


class TestGhostchromeUnavailable:
    """Verify RuntimeError when no browser backend is installed."""

    async def test_raises_runtime_error(self):
        """crawl_pages raises RuntimeError when neither ghostchrome nor agent-browser exists."""
        crawler = _make_crawler()

        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", False),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", False),
        ):
            with pytest.raises(RuntimeError, match="none was found"):
                await crawler.crawl_pages(["https://example.com"])


# ---------------------------------------------------------------------------
# _get_browser_crawler — lazy init and reuse
# ---------------------------------------------------------------------------


class TestGetBrowserCrawler:
    """Test lazy BrowserCrawler initialisation."""

    async def test_creates_instance_on_first_call(self):
        """_get_browser_crawler creates and caches a BrowserCrawler."""
        crawler = _make_crawler()
        assert crawler._browser_crawler is None

        with patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", True):
            result = await crawler._get_browser_crawler()

        assert crawler._browser_crawler is not None
        assert result is crawler._browser_crawler

    async def test_reuses_cached_instance(self):
        """_get_browser_crawler returns the cached instance on subsequent calls."""
        crawler = _make_crawler()
        mock_instance = MagicMock()
        crawler._browser_crawler = mock_instance

        result = await crawler._get_browser_crawler()
        assert result is mock_instance

    async def test_raises_when_agent_browser_absent(self):
        """_get_browser_crawler raises RuntimeError when no browser binary is found."""
        crawler = _make_crawler()

        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", False),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", False),
        ):
            with pytest.raises(RuntimeError, match="none was found"):
                await crawler._get_browser_crawler()


# ---------------------------------------------------------------------------
# close() — resource cleanup
# ---------------------------------------------------------------------------


class TestCrawlerServiceClose:
    """Test CrawlerService.close() tears down the browser crawler."""

    async def test_close_delegates_to_browser_crawler(self):
        """close() calls close() on the BrowserCrawler and nulls the reference."""
        crawler = _make_crawler()
        mock_browser = AsyncMock()
        crawler._browser_crawler = mock_browser

        await crawler.close()

        mock_browser.close.assert_called_once()
        assert crawler._browser_crawler is None

    async def test_close_without_browser_does_not_raise(self):
        """close() is a no-op when no BrowserCrawler was created."""
        crawler = _make_crawler()
        assert crawler._browser_crawler is None
        await crawler.close()

    async def test_close_sets_browser_crawler_to_none(self):
        """After close(), _browser_crawler is always None."""
        crawler = _make_crawler()
        crawler._browser_crawler = AsyncMock()

        await crawler.close()

        assert crawler._browser_crawler is None


# ---------------------------------------------------------------------------
# BROWSER_BACKEND: ghostchrome or agent-browser
# ---------------------------------------------------------------------------


class TestBrowserBackendSelection:
    """BROWSER_BACKEND picks the crawler; auto prefers ghostchrome."""

    async def test_auto_prefers_ghostchrome(self):
        """auto uses ghostchrome when both binaries exist."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = _make_crawler()
        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", True),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", True),
            patch.object(settings, "BROWSER_BACKEND", "auto"),
        ):
            result = await crawler._get_browser_crawler()

        assert isinstance(result, BrowserCrawler)

    async def test_auto_falls_back_to_agent_browser(self):
        """auto uses agent-browser when ghostchrome is missing."""
        from app.services.agent_browser_crawler import AgentBrowserCrawler

        crawler = _make_crawler()
        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", False),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", True),
            patch.object(settings, "BROWSER_BACKEND", "auto"),
        ):
            result = await crawler._get_browser_crawler()

        assert isinstance(result, AgentBrowserCrawler)

    async def test_explicit_backend_missing_raises(self):
        """An explicitly requested backend that is not installed is an error, not a fallback."""
        crawler = _make_crawler()
        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", True),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", False),
            patch.object(settings, "BROWSER_BACKEND", "agent-browser"),
        ):
            with pytest.raises(RuntimeError, match="agent-browser is required"):
                await crawler._get_browser_crawler()

    async def test_unknown_backend_raises(self):
        """A typo in BROWSER_BACKEND is reported with the accepted values."""
        crawler = _make_crawler()
        with patch.object(settings, "BROWSER_BACKEND", "playwright"):
            with pytest.raises(RuntimeError, match="Unknown BROWSER_BACKEND"):
                await crawler._get_browser_crawler()
