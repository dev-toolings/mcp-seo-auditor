"""Browser-based crawler using ghostchrome.

Two-pass strategy:
1. fastfetch (HTTP-only, ~50ms) — works for SSR pages, via the ghostchrome CLI
2. Chrome fallback — for SPAs or anti-bot blocked pages, via the ghostchrome Python
   SDK (persistent agent: navigate + eval). The SDK is optional; the fastfetch path
   works without it.
"""

import asyncio
import json
import logging
import shutil
import time
from typing import Optional

from bs4 import BeautifulSoup

try:
    from ghostchrome import Ghostchrome
except ImportError:  # SDK is optional — the fastfetch HTTP path works without it
    Ghostchrome = None  # type: ignore[assignment, misc]  # optional dependency fallback

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 "
    "SEOAuditor/2.0"
)

_DEFAULT_GHOSTCHROME = "ghostchrome"
_MIN_FASTFETCH_BYTES = 500
_MIN_FASTFETCH_VISIBLE_WORDS = 300
_MIN_FASTFETCH_H1_VISIBLE_WORDS = 100
_MIN_RENDERED_VISIBLE_WORDS = 50
_CHROME_SETTLE_RETRIES = 2
_CHROME_SETTLE_DELAY_SECONDS = 0.75


def _find_ghostchrome(configured_path: Optional[str] = None) -> Optional[str]:
    if configured_path and shutil.which(configured_path):
        return configured_path
    if shutil.which(_DEFAULT_GHOSTCHROME):
        return _DEFAULT_GHOSTCHROME
    for candidate in ("/usr/local/bin/ghostchrome", "/usr/bin/ghostchrome"):
        if shutil.which(candidate):
            return candidate
    return None


GHOSTCHROME_PATH = _find_ghostchrome()
GHOSTCHROME_AVAILABLE = GHOSTCHROME_PATH is not None
GHOSTCHROME_SDK_AVAILABLE = Ghostchrome is not None


class BrowserCrawler:
    """Headless browser crawler using ghostchrome.

    Strategy: fastfetch first (pure HTTP, fast), fallback to Chrome
    eval for JS-rendered pages or when blocked.
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
        self.max_concurrent = max_concurrent
        self.cdp_url = cdp_url
        self.user_agent = user_agent
        self._gc_path = _find_ghostchrome(agent_browser_path) or _DEFAULT_GHOSTCHROME
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_cmd(self, *args: str, timeout: Optional[int] = None) -> bytes:
        t = timeout or self.timeout
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                self._gc_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=t,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=t)
        if proc.returncode != 0:
            msg = stderr.decode().strip() if stderr else "unknown error"
            raise RuntimeError(f"ghostchrome exited {proc.returncode}: {msg}")
        return stdout

    async def _fastfetch(self, url: str) -> tuple[str, int, str]:
        """HTTP-only fetch — fast path for SSR pages."""
        stdout = await self._run_cmd(
            "fastfetch",
            "--format",
            "json",
            "--raw",
            url,
            timeout=15,
        )
        # fastfetch --raw --format json outputs raw HTML to stdout
        # but with --format json it outputs JSON envelope
        # We need to handle both: try JSON first, fall back to raw HTML
        text = stdout.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
            status = data.get("status", 200)
            final_url = data.get("url", url)
            html = data.get("html", "")
            if not html:
                # JSON mode without --raw doesn't include HTML body
                # Re-fetch with just --raw
                raw_stdout = await self._run_cmd("fastfetch", "--raw", url, timeout=15)
                html = raw_stdout.decode("utf-8", errors="replace")
            return html, status, final_url
        except json.JSONDecodeError:
            # Got raw HTML directly
            return text, 200, url

    async def _chrome_fetch(self, url: str) -> tuple[str, int, str]:
        """Full Chrome fetch via the ghostchrome SDK — fallback for SPAs and blocked pages.

        The SDK client is synchronous (drives a persistent agent over stdin/stdout),
        so it runs in a worker thread to avoid blocking the event loop.
        """
        return await asyncio.to_thread(self._chrome_fetch_sync, url)

    def _chrome_fetch_sync(self, url: str) -> tuple[str, int, str]:
        """Navigate + eval through a per-page ghostchrome agent (synchronous SDK)."""
        if Ghostchrome is None:
            raise RuntimeError(
                "ghostchrome SDK not installed. Install it from the ghostchrome repo "
                "(pip install <ghostchrome>/sdk/python) to enable the Chrome fallback."
            )

        flags: list[str] = []
        if not self.headless:
            flags.append("--headless=false")
        if self.cdp_url:
            flags.append(f"--connect={self.cdp_url}")

        with Ghostchrome(command=self._gc_path, extra_flags=flags, timeout=self.timeout) as gc:
            nav, _ = gc.navigate(url, wait="stable")
            html = ""
            for attempt in range(_CHROME_SETTLE_RETRIES + 1):
                html_result, _ = gc.eval_("document.documentElement.outerHTML")
                html = html_result.value or ""
                if not _rendered_html_needs_settle(html, nav.status):
                    break
                if attempt < _CHROME_SETTLE_RETRIES:
                    time.sleep(_CHROME_SETTLE_DELAY_SECONDS)
            return html, nav.status, (nav.url or url)

    async def crawl_page(self, url: str) -> tuple[str, int, str]:
        """Crawl a single page. Tries fastfetch first, falls back to Chrome.

        Returns:
            Tuple of (html_content, status_code, final_url).
        """
        async with self._semaphore:
            # Pass 1: fastfetch (HTTP-only, ~50ms)
            try:
                html, status, final_url = await self._fastfetch(url)
                if self._fastfetch_has_usable_dom(html, status):
                    return html, status, final_url
                logger.debug(
                    "fastfetch returned thin HTML for %s (%d bytes), trying Chrome", url, len(html)
                )
            except Exception as e:
                logger.debug("fastfetch failed for %s: %s, trying Chrome", url, e)

            # Pass 2: Chrome CDP (full JS rendering)
            try:
                return await self._chrome_fetch(url)
            except TimeoutError:
                logger.warning("ghostchrome timeout for %s", url)
                return "", 0, url
            except Exception as e:
                logger.warning("ghostchrome error for %s: %s", url, e)
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

    @staticmethod
    def _fastfetch_has_usable_dom(html: str, status: int) -> bool:
        """Return True when HTTP-only HTML is safe to audit without Chrome.

        Next.js PPR/streaming pages can produce a large HTML payload mostly made
        of React Flight scripts while the visible DOM is still thin or missing
        headings. Byte length alone would mark these pages as complete and cause
        false thin-content / missing-H1 findings.
        """
        if not html or status != 200 or len(html) <= _MIN_FASTFETCH_BYTES:
            return False

        if not _looks_like_next_streaming(html):
            return True

        word_count, h1_count = _visible_dom_stats(html)
        if h1_count > 0 and word_count >= _MIN_FASTFETCH_VISIBLE_WORDS:
            return True
        return h1_count > 0 and word_count >= _MIN_FASTFETCH_H1_VISIBLE_WORDS

    async def close(self) -> None:
        """No persistent sessions to clean up with ghostchrome."""
        pass


def _looks_like_next_streaming(html: str) -> bool:
    """Detect Next.js streaming/PPR markers in a raw HTML response."""
    return "self.__next_f.push" in html or "__next_f.push" in html or 'id="P:' in html


def _visible_dom_stats(html: str) -> tuple[int, int]:
    """Count visible words and H1s after removing non-visible payload holders."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "template", "noscript"]):
        tag.decompose()
    body = soup.find("body") or soup
    text = body.get_text(separator=" ", strip=True)
    return len(text.split()), len(body.find_all("h1"))


def _rendered_html_needs_settle(html: str, status: int) -> bool:
    """Return True when a Chrome snapshot still looks like a pre-hydration shell."""
    if not html or status != 200:
        return False
    if not _looks_like_next_streaming(html):
        return False
    word_count, h1_count = _visible_dom_stats(html)
    return h1_count == 0 or word_count < _MIN_RENDERED_VISIBLE_WORDS
