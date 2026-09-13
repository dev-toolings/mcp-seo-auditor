"""Browser crawler backed by the agent-browser CLI.

Same contract as ``BrowserCrawler`` (ghostchrome): ``crawl_page(url)`` returns
``(html, status_code, final_url)``. Two-pass strategy:
1. ``agent-browser read --raw`` (HTTP only, no Chrome) for server-rendered pages.
2. A headless Chromium session (``open`` + ``eval``) for JS-rendered or thin pages.
   The document status comes from the session's network log, since ``open``
   succeeds on a 404 page too.

Each crawler owns one named ``--session`` browser per concurrent slot and closes
them in ``close()``. ``BROWSER_CDP`` attaches to an existing browser instead.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from app.core.config import settings
from app.services.browser_crawler import (
    DEFAULT_USER_AGENT,
    BrowserCrawler,
    _rendered_html_needs_settle,
)

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_BROWSER = "agent-browser"
_READ_TIMEOUT_SECONDS = 15
_CLOSE_TIMEOUT_SECONDS = 15
_SETTLE_RETRIES = 2
_SETTLE_DELAY_SECONDS = 0.75
_HTTP_STATUS_IN_ERROR = re.compile(r"HTTP (\d{3})")
# Page scripts run inside the browser process: never hand it the server's secrets.
_SECRET_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")


def _find_agent_browser(configured_path: Optional[str] = None) -> Optional[str]:
    # Bun and user-local installs are often missing from an MCP client's $PATH.
    candidates = (
        configured_path,
        _DEFAULT_AGENT_BROWSER,
        str(Path.home() / ".bun" / "bin" / _DEFAULT_AGENT_BROWSER),
        str(Path.home() / ".local" / "bin" / _DEFAULT_AGENT_BROWSER),
        "/opt/bun/bin/agent-browser",
        "/usr/local/bin/agent-browser",
    )
    for candidate in candidates:
        if candidate and (found := shutil.which(candidate)):
            return found
    return None


AGENT_BROWSER_PATH = _find_agent_browser(settings.BROWSER_AGENT_PATH)
AGENT_BROWSER_AVAILABLE = AGENT_BROWSER_PATH is not None


def _needs_chromium_sandbox_bypass() -> bool:
    """Chromium's sandbox cannot start as root, in Docker, or under AppArmor userns limits."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return True
    if Path("/.dockerenv").exists():
        return True
    try:
        restrict = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
        return restrict.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return False


def _browser_env(launches_chromium: bool) -> dict[str, str]:
    """Subprocess env: secrets stripped, sandbox flags added only when Chromium needs them."""
    env = {
        name: value
        for name, value in os.environ.items()
        if name.startswith("AGENT_BROWSER_")
        or not any(marker in name.upper() for marker in _SECRET_ENV_MARKERS)
    }
    if (
        launches_chromium
        and "AGENT_BROWSER_ARGS" not in env
        and "AGENT_BROWSER_CHROME_FLAGS" not in env
        and _needs_chromium_sandbox_bypass()
    ):
        env["AGENT_BROWSER_ARGS"] = "--no-sandbox,--disable-dev-shm-usage"
    return env


def _document_status(requests: list[dict[str, Any]], final_url: str) -> Optional[int]:
    """Status of the main document: the Document request that landed on ``final_url``.

    Redirect hops are logged as Document requests without a status, so they never win.
    """
    documents = [
        r
        for r in requests
        if r.get("resourceType") == "Document" and isinstance(r.get("status"), int)
    ]
    target = final_url.rstrip("/")
    for request in documents:
        if str(request.get("url", "")).rstrip("/") == target:
            return request["status"]
    return documents[0]["status"] if documents else None


class AgentBrowserCrawler:
    """Headless browser crawler using agent-browser.

    Strategy: ``read --raw`` first (pure HTTP, fast), fallback to a Chromium
    session for JS-rendered pages or when blocked.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30,
        idle_timeout: int = 300,
        max_concurrent: int = 3,
        cdp_url: str = "",
        user_agent: str = DEFAULT_USER_AGENT,
        agent_browser_path: Optional[str] = None,
    ):
        self.headless = headless
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.cdp_url = cdp_url
        self.user_agent = user_agent
        # An attached CDP browser is one shared page: crawl it serially.
        self.max_concurrent = 1 if cdp_url else max_concurrent
        self._ab_path = _find_agent_browser(agent_browser_path) or _DEFAULT_AGENT_BROWSER
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        # Sessions launched by this crawler, and those not in use right now.
        # The semaphore bounds the pool to max_concurrent browsers.
        self._sessions: list[str] = []
        self._idle_sessions: list[str] = []

    def _argv(self, args: tuple[str, ...], session: Optional[str]) -> list[str]:
        argv = [self._ab_path]
        if self.cdp_url:
            # Never combine with --session: agent-browser would launch a local
            # browser and silently ignore --cdp.
            argv += ["--cdp", self.cdp_url]
        elif session:
            argv += [
                "--session",
                session,
                "--user-agent",
                self.user_agent,
                # Safety net: the daemon exits on its own if close() never runs.
                "--idle-timeout",
                f"{self.idle_timeout}s",
            ]
            if not self.headless:
                argv.append("--headed")
        return argv + ["--json", *args]

    async def _run(
        self, *args: str, session: Optional[str] = None, timeout: Optional[int] = None
    ) -> dict[str, Any]:
        """Run one agent-browser command and return its JSON ``data``."""
        proc = await asyncio.create_subprocess_exec(
            *self._argv(args, session),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_browser_env(launches_chromium=session is not None and not self.cdp_url),
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout or self.timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        try:
            payload = json.loads(stdout.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            msg = stderr.decode("utf-8", errors="replace").strip() if stderr else ""
            raise RuntimeError(
                f"agent-browser {args[0]} returned no JSON (exit {proc.returncode}): {msg}"
            ) from None
        if not payload.get("success"):
            raise RuntimeError(
                f"agent-browser {args[0]} failed: {payload.get('error') or 'unknown error'}"
            )
        return payload.get("data") or {}

    async def _read(self, url: str) -> tuple[str, int, str]:
        """HTTP-only fetch, the fast path for SSR pages."""
        try:
            data = await self._run("read", url, "--raw", timeout=_READ_TIMEOUT_SECONDS)
        except RuntimeError as e:
            # read reports non-2xx responses as failures ("Read failed with HTTP 404").
            match = _HTTP_STATUS_IN_ERROR.search(str(e))
            if match:
                return "", int(match.group(1)), url
            raise
        html = data.get("content") or ""
        # read negotiates markdown first; only a complete HTML body is an auditable DOM.
        if "html" not in str(data.get("contentType") or "").lower() or data.get("truncated"):
            html = ""
        return html, int(data.get("status") or 200), data.get("finalUrl") or url

    def _acquire_session(self) -> Optional[str]:
        if self.cdp_url:
            return None
        if self._idle_sessions:
            return self._idle_sessions.pop()
        session = f"seo-auditor-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._sessions.append(session)
        return session

    async def _render(self, url: str) -> tuple[str, int, str]:
        """Full Chromium render, the fallback for SPAs and blocked pages."""
        session = self._acquire_session()
        try:
            await self._run("network", "requests", "--clear", session=session)
            nav = await self._run("open", url, session=session)
            final_url = nav.get("url") or url
            network = await self._run("network", "requests", session=session)
            status = _document_status(network.get("requests") or [], final_url)

            html = ""
            for attempt in range(_SETTLE_RETRIES + 1):
                result = await self._run(
                    "eval", "document.documentElement.outerHTML", session=session
                )
                html = str(result.get("result") or "")
                if not _rendered_html_needs_settle(html, status or 200):
                    break
                if attempt < _SETTLE_RETRIES:
                    await asyncio.sleep(_SETTLE_DELAY_SECONDS)
            # An empty network log only happens when the CDP target was not ours.
            if status is None:
                status = 200 if html else 0
            return html, status, final_url
        finally:
            if session:
                self._idle_sessions.append(session)

    async def crawl_page(self, url: str) -> tuple[str, int, str]:
        """Crawl a single page. Tries read first, falls back to Chromium.

        Returns:
            Tuple of (html_content, status_code, final_url).
        """
        async with self._semaphore:
            try:
                html, status, final_url = await self._read(url)
                if BrowserCrawler._fastfetch_has_usable_dom(html, status):
                    return html, status, final_url
                logger.debug(
                    "agent-browser read returned thin HTML for %s (status %d), trying Chrome",
                    url,
                    status,
                )
            except Exception as e:
                logger.debug("agent-browser read failed for %s: %s, trying Chrome", url, e)

            try:
                return await self._render(url)
            except TimeoutError:
                logger.warning("agent-browser timeout for %s", url)
                return "", 0, url
            except Exception as e:
                logger.warning("agent-browser error for %s: %s", url, e)
                return "", 0, url

    async def crawl_pages(self, urls: list[str]) -> dict[str, tuple[str, int, str]]:
        """Crawl multiple pages concurrently."""
        results: dict[str, tuple[str, int, str]] = {}

        async def _crawl(target_url: str) -> None:
            try:
                html, status, final_url = await self.crawl_page(target_url)
                if status != 0:
                    results[target_url] = (html, status, final_url)
            except Exception as exc:
                logger.warning("Browser crawl failed for %s: %s", target_url, exc)

        await asyncio.gather(*[_crawl(u) for u in urls])
        return results

    async def close(self) -> None:
        """Close every browser session this crawler launched."""
        sessions, self._sessions, self._idle_sessions = self._sessions, [], []
        for session in sessions:
            try:
                await self._run("close", session=session, timeout=_CLOSE_TIMEOUT_SECONDS)
            except Exception as e:
                logger.debug("agent-browser close failed for %s: %s", session, e)
