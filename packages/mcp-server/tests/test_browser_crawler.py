"""Tests for BrowserCrawler — ghostchrome CLI based crawling (fastfetch + Chrome)."""

import json
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# GHOSTCHROME_AVAILABLE flag
# ---------------------------------------------------------------------------


class TestGhostchromeAvailability:
    """Test graceful degradation when ghostchrome is not installed."""

    def test_flag_exists(self):
        """GHOSTCHROME_AVAILABLE must exist and be a bool."""
        from app.services.browser_crawler import GHOSTCHROME_AVAILABLE

        assert isinstance(GHOSTCHROME_AVAILABLE, bool)

    async def test_raises_without_ghostchrome(self):
        """RuntimeError is raised when ghostchrome and agent-browser are both absent."""
        from app.services.crawler_service import CrawlerService

        crawler = CrawlerService()

        with (
            patch("app.services.browser_crawler.GHOSTCHROME_AVAILABLE", False),
            patch("app.services.agent_browser_crawler.AGENT_BROWSER_AVAILABLE", False),
        ):
            with pytest.raises(RuntimeError, match="none was found"):
                await crawler._get_browser_crawler()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestBrowserCrawlerInit:
    """Test BrowserCrawler initialization and default configuration."""

    def test_default_config(self):
        """All defaults match documented values."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()
        assert crawler.headless is True
        assert crawler.timeout == 30
        assert crawler.max_concurrent == 3
        assert crawler.cdp_url == ""

    def test_custom_config(self):
        """Constructor arguments override defaults."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler(
            headless=False,
            timeout=60,
            max_concurrent=5,
            cdp_url="ws://localhost:9222",
        )
        assert crawler.headless is False
        assert crawler.timeout == 60
        assert crawler.max_concurrent == 5
        assert crawler.cdp_url == "ws://localhost:9222"

    def test_semaphore_sized_to_max_concurrent(self):
        """The concurrency semaphore is initialised to max_concurrent."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler(max_concurrent=4)
        assert crawler._semaphore._value == 4


# ---------------------------------------------------------------------------
# _fastfetch — JSON envelope parsing and raw HTML fallback
# ---------------------------------------------------------------------------


class TestFastfetch:
    """Test the HTTP-only fast path."""

    async def test_parses_json_envelope(self):
        """A JSON envelope yields html, status and final url."""
        from app.services.browser_crawler import BrowserCrawler

        payload = json.dumps(
            {"status": 200, "url": "https://example.com/", "html": "<html>ok</html>"}
        )
        crawler = BrowserCrawler()
        crawler._run_cmd = AsyncMock(return_value=payload.encode())

        html, status, final_url = await crawler._fastfetch("https://example.com/")

        assert html == "<html>ok</html>"
        assert status == 200
        assert final_url == "https://example.com/"

    async def test_raw_html_when_not_json(self):
        """Non-JSON stdout is treated as raw HTML with status 200."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()
        crawler._run_cmd = AsyncMock(return_value=b"<html>raw</html>")

        html, status, final_url = await crawler._fastfetch("https://example.com/")

        assert html == "<html>raw</html>"
        assert status == 200
        assert final_url == "https://example.com/"


# ---------------------------------------------------------------------------
# crawl_page — two-pass strategy (fastfetch fast path, Chrome fallback)
# ---------------------------------------------------------------------------


class TestBrowserCrawlerCrawlPage:
    """Test single-page crawl behaviour."""

    async def test_fastfetch_success_returns_directly(self):
        """A rich fastfetch result (>500 bytes, status 200) skips Chrome."""
        from app.services.browser_crawler import BrowserCrawler

        html = "<html>" + "x" * 600 + "</html>"
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(return_value=(html, 200, "https://example.com/"))
        crawler._chrome_fetch = AsyncMock()

        result_html, status, final_url = await crawler.crawl_page("https://example.com/")

        assert status == 200
        assert result_html == html
        assert final_url == "https://example.com/"
        crawler._chrome_fetch.assert_not_called()

    async def test_next_streaming_with_visible_dom_returns_directly(self):
        """A Next streaming page is accepted when the visible DOM is rich enough."""
        from app.services.browser_crawler import BrowserCrawler

        visible = " ".join(["word"] * 350)
        html = (
            "<html><body><h1>Visible page</h1><main>"
            + visible
            + "</main><script>self.__next_f.push([1])</script></body></html>"
        )
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(return_value=(html, 200, "https://example.com/"))
        crawler._chrome_fetch = AsyncMock()

        result_html, status, final_url = await crawler.crawl_page("https://example.com/")

        assert status == 200
        assert result_html == html
        assert final_url == "https://example.com/"
        crawler._chrome_fetch.assert_not_called()

    async def test_next_streaming_thin_dom_falls_back_to_chrome(self):
        """A large React Flight payload with thin visible DOM triggers Chrome."""
        from app.services.browser_crawler import BrowserCrawler

        thin_dom_large_payload = (
            "<html><body><p>Se connecter</p>"
            "<script>self.__next_f.push([1, '"
            + ("Voiture occasion Paris " * 80)
            + "'])</script></body></html>"
        )
        rich = (
            "<html><body><h1>Voiture occasion Paris</h1>"
            + (" ".join(["visible"] * 350))
            + "</body></html>"
        )
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(
            return_value=(thin_dom_large_payload, 200, "https://example.com/")
        )
        crawler._chrome_fetch = AsyncMock(return_value=(rich, 200, "https://example.com/"))

        result_html, status, _ = await crawler.crawl_page("https://example.com/")

        crawler._chrome_fetch.assert_called_once()
        assert result_html == rich
        assert status == 200

    async def test_next_streaming_without_h1_falls_back_to_chrome(self):
        """A rich Next streaming payload without visible H1 still needs Chrome."""
        from app.services.browser_crawler import BrowserCrawler

        no_h1_payload = (
            "<html><body><section>"
            + " ".join(["visible"] * 350)
            + "</section><script>self.__next_f.push([1])</script></body></html>"
        )
        rich = "<html><body><h1>Rendered H1</h1>" + (" ".join(["visible"] * 350)) + "</body></html>"
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(return_value=(no_h1_payload, 200, "https://example.com/"))
        crawler._chrome_fetch = AsyncMock(return_value=(rich, 200, "https://example.com/"))

        result_html, status, _ = await crawler.crawl_page("https://example.com/")

        crawler._chrome_fetch.assert_called_once()
        assert result_html == rich
        assert status == 200

    async def test_thin_fastfetch_falls_back_to_chrome(self):
        """A thin fastfetch result triggers the Chrome fallback."""
        from app.services.browser_crawler import BrowserCrawler

        rich = "<html>" + "y" * 600 + "</html>"
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(return_value=("<p>thin</p>", 200, "https://example.com/"))
        crawler._chrome_fetch = AsyncMock(return_value=(rich, 200, "https://example.com/"))

        result_html, status, _ = await crawler.crawl_page("https://example.com/")

        crawler._chrome_fetch.assert_called_once()
        assert result_html == rich
        assert status == 200

    async def test_fastfetch_error_falls_back_to_chrome(self):
        """A fastfetch exception triggers the Chrome fallback."""
        from app.services.browser_crawler import BrowserCrawler

        rich = "<html>" + "z" * 600 + "</html>"
        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(side_effect=RuntimeError("ghostchrome exited 1"))
        crawler._chrome_fetch = AsyncMock(return_value=(rich, 200, "https://example.com/"))

        result_html, status, _ = await crawler.crawl_page("https://example.com/")

        crawler._chrome_fetch.assert_called_once()
        assert result_html == rich

    async def test_timeout_returns_status_zero(self):
        """crawl_page returns ("", 0, url) when the Chrome fallback times out."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(side_effect=RuntimeError("thin"))
        crawler._chrome_fetch = AsyncMock(side_effect=TimeoutError("timed out"))

        html, status, final_url = await crawler.crawl_page("https://slow.com/")

        assert html == ""
        assert status == 0
        assert final_url == "https://slow.com/"

    async def test_error_returns_status_zero(self):
        """crawl_page returns ("", 0, url) when the Chrome fallback raises."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()
        crawler._fastfetch = AsyncMock(side_effect=RuntimeError("thin"))
        crawler._chrome_fetch = AsyncMock(side_effect=RuntimeError("navigation failed"))

        html, status, final_url = await crawler.crawl_page("https://example.com/")

        assert html == ""
        assert status == 0
        assert final_url == "https://example.com/"


# ---------------------------------------------------------------------------
# crawl_pages (batch)
# ---------------------------------------------------------------------------


class TestBrowserCrawlerCrawlPages:
    """Test concurrent batch crawl behaviour."""

    async def test_returns_dict_keyed_by_url(self):
        """crawl_pages returns a dict mapping original URL to (html, status, final_url)."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler(max_concurrent=2)

        async def _fake_crawl(url: str):
            return ("<html></html>", 200, url)

        crawler.crawl_page = _fake_crawl

        urls = ["https://example.com/1", "https://example.com/2"]
        results = await crawler.crawl_pages(urls)

        assert len(results) == 2
        for url in urls:
            assert url in results
            _, status, _ = results[url]
            assert status == 200

    async def test_failed_url_excluded(self):
        """URLs that return status 0 are excluded from the result dict."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()

        async def _fake_crawl(url: str):
            return ("", 0, url)

        crawler.crawl_page = _fake_crawl

        results = await crawler.crawl_pages(["https://fail.com/"])
        assert len(results) == 0

    async def test_partial_failure_keeps_successful_pages(self):
        """Only failed URLs are excluded; successful ones remain in the dict."""
        from app.services.browser_crawler import BrowserCrawler

        crawler = BrowserCrawler()
        responses = {
            "https://ok.com/": ("<html></html>", 200, "https://ok.com/"),
            "https://fail.com/": ("", 0, "https://fail.com/"),
        }

        async def _fake_crawl(url: str):
            return responses[url]

        crawler.crawl_page = _fake_crawl

        results = await crawler.crawl_pages(["https://ok.com/", "https://fail.com/"])

        assert "https://ok.com/" in results
        assert "https://fail.com/" not in results


# ---------------------------------------------------------------------------
# Chrome fallback — driven by the ghostchrome SDK (navigate + eval)
# ---------------------------------------------------------------------------


class _FakeNav:
    def __init__(self, status: int, url: str, title: str = "t"):
        self.status = status
        self.url = url
        self.title = title


class _FakeEval:
    def __init__(self, value: str):
        self.value = value


def _fake_ghostchrome(
    captured: dict, *, html: str | list[str] = "<html></html>", status: int = 200
):
    """Build a fake Ghostchrome class that records constructor kwargs and ops."""
    html_values = html if isinstance(html, list) else [html]

    class FakeGhostchrome:
        def __init__(self, *, command, extra_flags, timeout):
            captured["command"] = command
            captured["extra_flags"] = extra_flags
            captured["timeout"] = timeout
            captured["eval_count"] = 0

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def navigate(self, url, wait=None):
            captured["navigate_url"] = url
            captured["navigate_wait"] = wait
            return _FakeNav(status, url), None

        def eval_(self, expr, ref=None):
            captured["eval_expr"] = expr
            index = min(captured["eval_count"], len(html_values) - 1)
            captured["eval_count"] += 1
            return _FakeEval(html_values[index]), None

    return FakeGhostchrome


class TestChromeFetch:
    """Test the SDK-backed Chrome fallback (_chrome_fetch / _chrome_fetch_sync)."""

    def test_returns_html_status_and_url(self):
        """_chrome_fetch_sync returns the SDK's html, status and final url."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        captured: dict = {}
        fake = _fake_ghostchrome(captured, html="<html>rendered</html>", status=200)
        with patch.object(browser_crawler, "Ghostchrome", fake):
            crawler = BrowserCrawler()
            html, status, final_url = crawler._chrome_fetch_sync("https://example.com/")

        assert html == "<html>rendered</html>"
        assert status == 200
        assert final_url == "https://example.com/"
        assert captured["eval_expr"] == "document.documentElement.outerHTML"
        assert captured["navigate_wait"] == "stable"

    def test_retries_when_rendered_next_dom_is_still_empty(self):
        """_chrome_fetch_sync re-reads a thin Next snapshot before returning it."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        thin_next_shell = (
            "<html><body><p>Chargement</p><script>self.__next_f.push([1])</script></body></html>"
        )
        rendered = (
            "<html><body><h1>Voiture occasion Nord</h1>"
            + " ".join(["visible"] * 120)
            + "<script>self.__next_f.push([1])</script></body></html>"
        )

        captured: dict = {}
        fake = _fake_ghostchrome(captured, html=[thin_next_shell, rendered], status=200)
        with (
            patch.object(browser_crawler, "Ghostchrome", fake),
            patch.object(browser_crawler.time, "sleep") as sleep,
        ):
            crawler = BrowserCrawler()
            html, status, final_url = crawler._chrome_fetch_sync("https://example.com/")

        assert html == rendered
        assert status == 200
        assert final_url == "https://example.com/"
        assert captured["eval_count"] == 2
        sleep.assert_called_once()

    def test_cdp_url_forwarded_as_connect_flag(self):
        """When cdp_url is set, --connect=<url> is passed to the SDK as an extra flag."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        captured: dict = {}
        with patch.object(browser_crawler, "Ghostchrome", _fake_ghostchrome(captured)):
            crawler = BrowserCrawler(cdp_url="ws://localhost:9222")
            crawler._chrome_fetch_sync("https://example.com/")

        assert "--connect=ws://localhost:9222" in captured["extra_flags"]

    def test_no_cdp_url_omits_connect_flag(self):
        """When cdp_url is empty, no --connect flag is passed."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        captured: dict = {}
        with patch.object(browser_crawler, "Ghostchrome", _fake_ghostchrome(captured)):
            crawler = BrowserCrawler()
            crawler._chrome_fetch_sync("https://example.com/")

        assert not any(f.startswith("--connect") for f in captured["extra_flags"])

    def test_headless_false_adds_flag(self):
        """headless=False forwards --headless=false to the SDK."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        captured: dict = {}
        with patch.object(browser_crawler, "Ghostchrome", _fake_ghostchrome(captured)):
            crawler = BrowserCrawler(headless=False)
            crawler._chrome_fetch_sync("https://example.com/")

        assert "--headless=false" in captured["extra_flags"]

    def test_raises_when_sdk_missing(self):
        """_chrome_fetch_sync raises a clear error when the SDK is not installed."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        with patch.object(browser_crawler, "Ghostchrome", None):
            crawler = BrowserCrawler()
            with pytest.raises(RuntimeError, match="ghostchrome SDK not installed"):
                crawler._chrome_fetch_sync("https://example.com/")

    async def test_chrome_fetch_async_delegates_to_sync(self):
        """The async _chrome_fetch wrapper returns the sync result via a worker thread."""
        from app.services import browser_crawler
        from app.services.browser_crawler import BrowserCrawler

        captured: dict = {}
        fake = _fake_ghostchrome(captured, html="<html>x</html>", status=200)
        with patch.object(browser_crawler, "Ghostchrome", fake):
            crawler = BrowserCrawler()
            html, status, _ = await crawler._chrome_fetch("https://example.com/")

        assert html == "<html>x</html>"
        assert status == 200
        assert captured["navigate_url"] == "https://example.com/"


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestBrowserCrawlerCleanup:
    """Test resource cleanup via close()."""

    async def test_close_is_noop(self):
        """close() returns without spawning a subprocess and without raising."""
        from app.services.browser_crawler import BrowserCrawler

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            crawler = BrowserCrawler(max_concurrent=3)
            await crawler.close()

        mock_exec.assert_not_called()
