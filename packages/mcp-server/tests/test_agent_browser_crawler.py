"""Tests for AgentBrowserCrawler: agent-browser CLI based crawling (read + Chromium)."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent_browser_crawler import AgentBrowserCrawler, _browser_env

URL = "https://example.com/page"
FULL_HTML = (
    "<html><head><title>T</title></head><body><h1>Hello</h1>" + "word " * 400 + "</body></html>"
)
THIN_HTML = "<html><body><div id='root'></div></body></html>"


def _fake_run(responses: dict[tuple[str, ...], object]):
    """Build a _run replacement answering by command; exceptions are raised."""
    calls: list[tuple[tuple[str, ...], object]] = []

    async def run(*args: str, session=None, timeout=None):
        calls.append((args, session))
        for prefix, response in responses.items():
            if args[: len(prefix)] == prefix:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"unexpected command {args}")

    return run, calls


def _render_responses(status: int, final_url: str = URL) -> dict[tuple[str, ...], object]:
    return {
        ("network", "requests", "--clear"): {"cleared": True},
        ("open",): {"url": final_url},
        ("network", "requests"): {
            "requests": [
                # Redirect hop: logged without a status, must not be picked.
                {"resourceType": "Document", "url": "http://example.com/page", "status": None},
                {"resourceType": "Font", "url": "https://example.com/f.woff2", "status": 200},
                {"resourceType": "Document", "url": final_url, "status": status},
            ]
        },
        ("eval",): {"result": FULL_HTML},
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


class TestArgv:
    """Test how agent-browser is invoked."""

    def test_session_flags_precede_json_and_command(self):
        """A local session passes --session, --user-agent and --idle-timeout before --json."""
        crawler = AgentBrowserCrawler(idle_timeout=120, user_agent="UA")

        argv = crawler._argv(("open", URL), "s1")

        assert argv[1:] == [
            "--session",
            "s1",
            "--user-agent",
            "UA",
            "--idle-timeout",
            "120s",
            "--json",
            "open",
            URL,
        ]

    def test_cdp_mode_never_passes_session(self):
        """CDP mode attaches with --cdp only and crawls serially."""
        crawler = AgentBrowserCrawler(cdp_url="ws://localhost:9222", max_concurrent=4)

        argv = crawler._argv(("open", URL), crawler._acquire_session())

        assert "--cdp" in argv and "--session" not in argv
        assert crawler.max_concurrent == 1

    async def test_run_raises_on_unsuccessful_payload(self):
        """A {success: false} envelope becomes a RuntimeError carrying the error."""
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(
            return_value=(json.dumps({"success": False, "error": "boom"}).encode(), b"")
        )
        crawler = AgentBrowserCrawler()

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(RuntimeError, match="open failed: boom"):
                await crawler._run("open", URL, session="s1")


# ---------------------------------------------------------------------------
# crawl_page: two-pass strategy (read fast path, Chromium fallback)
# ---------------------------------------------------------------------------


class TestCrawlPage:
    """Test single-page crawl behaviour."""

    async def test_usable_read_skips_chromium(self):
        """A complete HTML read is returned without launching a browser."""
        crawler = AgentBrowserCrawler()
        run, calls = _fake_run(
            {
                ("read",): {
                    "content": FULL_HTML,
                    "status": 200,
                    "finalUrl": URL,
                    "contentType": "text/html; charset=utf-8",
                }
            }
        )
        crawler._run = run

        assert await crawler.crawl_page(URL) == (FULL_HTML, 200, URL)
        assert [args[0] for args, _ in calls] == ["read"]

    async def test_thin_read_renders_with_document_status(self):
        """A thin read falls back to Chromium; status is the Document that reached final_url."""
        crawler = AgentBrowserCrawler()
        responses = {
            ("read",): {"content": THIN_HTML, "status": 200, "contentType": "text/html"},
            **_render_responses(200),
        }
        crawler._run, calls = _fake_run(responses)

        assert await crawler.crawl_page(URL) == (FULL_HTML, 200, URL)
        assert all(session is not None for args, session in calls if args[0] != "read")

    async def test_markdown_read_is_not_audited(self):
        """A markdown answer to read is not a DOM: the page is rendered instead."""
        crawler = AgentBrowserCrawler()
        responses = {
            ("read",): {"content": FULL_HTML, "status": 200, "contentType": "text/markdown"},
            **_render_responses(200),
        }
        crawler._run, calls = _fake_run(responses)

        await crawler.crawl_page(URL)

        assert any(args[0] == "open" for args, _ in calls)

    async def test_http_error_keeps_real_status(self):
        """A 404 reported by read and by the network log is returned as 404."""
        crawler = AgentBrowserCrawler()
        responses = {
            ("read",): RuntimeError("agent-browser read failed: Read failed with HTTP 404"),
            **_render_responses(404),
        }
        crawler._run, _ = _fake_run(responses)

        _, status, _ = await crawler.crawl_page(URL)

        assert status == 404

    async def test_render_failure_returns_status_zero(self):
        """A browser error degrades to ("", 0, url) instead of raising."""
        crawler = AgentBrowserCrawler()
        responses = {
            ("read",): RuntimeError("network down"),
            ("network", "requests", "--clear"): {"cleared": True},
            ("open",): RuntimeError("Chrome exited early"),
        }
        crawler._run, _ = _fake_run(responses)

        assert await crawler.crawl_page(URL) == ("", 0, URL)


# ---------------------------------------------------------------------------
# Sessions and environment
# ---------------------------------------------------------------------------


class TestSessionsAndEnv:
    """Test session cleanup and the subprocess environment."""

    async def test_close_closes_each_launched_session(self):
        """close() sends `close` to every session the crawler launched, then forgets them."""
        crawler = AgentBrowserCrawler()
        responses = {
            ("read",): RuntimeError("no read"),
            **_render_responses(200),
            ("close",): {},
        }
        crawler._run, calls = _fake_run(responses)
        await crawler.crawl_page(URL)
        launched = list(crawler._sessions)

        await crawler.close()

        assert [session for args, session in calls if args[0] == "close"] == launched
        assert crawler._sessions == [] and crawler._idle_sessions == []

    def test_sandbox_args_added_when_needed(self):
        """Chromium gets --no-sandbox when the host forbids its sandbox."""
        with (
            patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True),
            patch(
                "app.services.agent_browser_crawler._needs_chromium_sandbox_bypass",
                return_value=True,
            ),
        ):
            env = _browser_env(launches_chromium=True)

        assert env["AGENT_BROWSER_ARGS"] == "--no-sandbox,--disable-dev-shm-usage"

    def test_user_sandbox_args_are_kept(self):
        """An explicit AGENT_BROWSER_ARGS is never overridden."""
        with (
            patch.dict(os.environ, {"AGENT_BROWSER_ARGS": "--custom"}, clear=True),
            patch(
                "app.services.agent_browser_crawler._needs_chromium_sandbox_bypass",
                return_value=True,
            ),
        ):
            env = _browser_env(launches_chromium=True)

        assert env["AGENT_BROWSER_ARGS"] == "--custom"

    def test_secrets_are_not_forwarded(self):
        """API keys and tokens stay out of the browser process; agent-browser config passes."""
        environ = {
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY": "sk-test",
            "GITHUB_TOKEN": "ghp-test",
            "AGENT_BROWSER_ENGINE": "chrome",
        }
        with patch.dict(os.environ, environ, clear=True):
            env = _browser_env(launches_chromium=False)

        assert env == {"PATH": "/usr/bin", "AGENT_BROWSER_ENGINE": "chrome"}
