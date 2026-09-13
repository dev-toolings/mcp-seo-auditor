"""Async crawler service using a browser backend (ghostchrome or agent-browser) for all pages."""

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
from app.core.safe_http import safe_get
from app.core.security import validate_url

logger = logging.getLogger(__name__)

# Share of the rendered text that exists only after JS before a page is flagged
# as JS-dependent in the raw-vs-rendered diff.
_JS_CONTENT_GAP_THRESHOLD = 0.3

# Link targets outside the crawl get a plain status check, capped per analysis.
_MAX_LINK_STATUS_CHECKS = 500
_BOT_BLOCK_STATUSES = {401, 403, 429}

_BROWSER_INSTALL_HINTS = {
    "ghostchrome": "https://github.com/dev-toolings/ghostchrome",
    "agent-browser": "bun add -g agent-browser && agent-browser install",
}


def _resolve_browser_backend(requested: str) -> str:
    """Pick the crawler backend from BROWSER_BACKEND (auto, ghostchrome, agent-browser).

    ``auto`` keeps ghostchrome first, the historical default, and falls back to
    agent-browser, so a host with either binary can crawl.
    """
    from app.services import agent_browser_crawler, browser_crawler

    available = {
        "ghostchrome": browser_crawler.GHOSTCHROME_AVAILABLE,
        "agent-browser": agent_browser_crawler.AGENT_BROWSER_AVAILABLE,
    }
    choice = (requested or "auto").strip().lower()
    if choice == "auto":
        for name, is_available in available.items():
            if is_available:
                return name
        raise RuntimeError(
            "A browser is required but none was found. Install ghostchrome "
            f"({_BROWSER_INSTALL_HINTS['ghostchrome']}) or agent-browser "
            f"({_BROWSER_INSTALL_HINTS['agent-browser']})."
        )
    if choice not in available:
        raise RuntimeError(
            f"Unknown BROWSER_BACKEND {requested!r}: use auto, ghostchrome or agent-browser."
        )
    if not available[choice]:
        raise RuntimeError(
            f"{choice} is required but not found. Install: {_BROWSER_INSTALL_HINTS[choice]}"
        )
    return choice


def _schema_types(structured_data: list[dict]) -> set[str]:
    """Collect the @type values of a page's JSON-LD blocks (including @graph nodes)."""
    types: set[str] = set()

    def collect(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                collect(item)
            return
        if not isinstance(node, dict):
            return
        raw_type = node.get("@type")
        if isinstance(raw_type, str):
            types.add(raw_type)
        elif isinstance(raw_type, list):
            types.update(t for t in raw_type if isinstance(t, str))
        collect(node.get("@graph"))

    collect(structured_data)
    return types


def _attr_str(value: object, default: str = "") -> str:
    """Coerce a single-valued BeautifulSoup attribute to str.

    Single-valued attrs (href, content) are ``str`` at runtime; the typed
    ``AttributeValueList``/``None`` cases are impossible and map to ``default``.
    """
    return value if isinstance(value, str) else default


@dataclass
class LinkInfo:
    """Details about a link found on a page."""

    href: str
    rel: Optional[str] = None
    anchor_text: str = ""
    is_internal: bool = False
    nofollow: bool = False


@dataclass
class ListingConfig:
    """Configuration for detecting listing pages and counting items."""

    css_selectors: list[str] = field(
        default_factory=lambda: [
            "[class*='product']",
            "[class*='listing']",
            "[class*='item']",
            "[class*='card']",
            "[class*='result']",
        ]
    )
    count_css_selector: Optional[str] = None
    text_patterns: list[str] = field(
        default_factory=lambda: [
            r"(\d+)\s*results?",
            r"(\d+)\s*items?",
            r"(\d+)\s*products?",
        ]
    )


@dataclass
class CrawledPage:
    """Result of crawling a single page."""

    url: str
    status_code: int
    final_url: Optional[str] = None
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: Optional[str] = None
    content: str = ""
    raw_html: Optional[str] = None
    word_count: int = 0
    item_count: Optional[int] = None
    canonical_url: Optional[str] = None
    meta_robots: Optional[str] = None
    hreflang: dict[str, str] = field(default_factory=dict)  # hreflang -> absolute href
    structured_data: list[dict] = field(default_factory=list)
    internal_links: list[str] = field(default_factory=list)
    link_details: list[LinkInfo] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None
    js_rendered: bool = False


class CrawlerService:
    """Async crawler using agent-browser for all pages."""

    def __init__(
        self,
        timeout: Optional[int] = None,
        max_concurrent: Optional[int] = None,
        user_agent: Optional[str] = None,
        listing_config: Optional[ListingConfig] = None,
    ):
        self.timeout = timeout or settings.CRAWLER_TIMEOUT
        self.max_concurrent = max_concurrent or settings.CRAWLER_MAX_CONCURRENT
        self.user_agent = user_agent or settings.CRAWLER_USER_AGENT
        self.listing_config = listing_config
        self._browser_crawler = None

    async def crawl_pages(
        self,
        urls: list[str],
        on_page_crawled: Optional[Callable[["CrawledPage", int, int], Awaitable[None]]] = None,
        abort_signal: Optional[list[bool]] = None,
    ) -> list[CrawledPage]:
        """Crawl multiple pages concurrently using agent-browser.

        Args:
            abort_signal: Mutable single-element list. When set to [True] by the caller
                (e.g. from on_page_crawled callback), remaining pages waiting for the
                semaphore are skipped without attempting a crawl.
        """
        browser = await self._get_browser_crawler()
        semaphore = asyncio.Semaphore(self.max_concurrent)
        total = len(urls)
        crawled_count = 0
        lock = asyncio.Lock()

        async def crawl_one(url: str) -> CrawledPage:
            nonlocal crawled_count
            validate_url(url)
            async with semaphore:
                if abort_signal and abort_signal[0]:
                    return CrawledPage(
                        url=url, status_code=0, error="Crawl aborted (high error rate)"
                    )
                try:
                    html, status, final_url = await browser.crawl_page(url)
                    page = CrawledPage(
                        url=url,
                        status_code=status,
                        final_url=final_url if final_url != url else None,
                        js_rendered=True,
                    )
                    if status == 200 and html:
                        page.raw_html = html
                        self._parse_html(page, html)
                    return page
                except Exception as e:
                    logger.warning("Failed to crawl %s: %s", url, e)
                    return CrawledPage(url=url, status_code=0, error=str(e))

        async def crawl_and_notify(url: str) -> CrawledPage:
            nonlocal crawled_count
            page = await crawl_one(url)
            if on_page_crawled:
                async with lock:
                    crawled_count += 1
                    await on_page_crawled(page, crawled_count, total)
            return page

        tasks = [crawl_and_notify(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        pages = []
        for url, result in zip(urls, results):
            if isinstance(result, CrawledPage):
                pages.append(result)
            else:
                pages.append(CrawledPage(url=url, status_code=0, error=str(result)))

        return pages

    async def check_link_statuses(
        self, urls: list[str], limit: int = _MAX_LINK_STATUS_CHECKS
    ) -> dict[str, int]:
        """HTTP status of link targets the crawl did not visit (plain GET, redirects followed).

        Returns 0 for a target that could not be checked: a network failure, or
        401/403/429, which on an otherwise crawlable site means bot protection
        rather than a missing page. The links analyzer never counts 0 as broken.
        """
        if len(urls) > limit:
            logger.warning("Checking %d of %d uncrawled link targets", limit, len(urls))
            urls = urls[:limit]
        semaphore = asyncio.Semaphore(self.max_concurrent)
        statuses: dict[str, int] = {}

        async with httpx.AsyncClient(timeout=self.timeout) as client:

            async def check(url: str) -> None:
                async with semaphore:
                    try:
                        response = await safe_get(
                            client, url, headers={"User-Agent": self.user_agent}
                        )
                    except Exception as e:
                        logger.debug("Link target check failed for %s: %s", url, e)
                        statuses[url] = 0
                        return
                    status = response.status_code
                    statuses[url] = 0 if status in _BOT_BLOCK_STATUSES else status

            await asyncio.gather(*(check(url) for url in urls))
        return statuses

    async def fetch_raw_html(self, url: str) -> tuple[str, int, str]:
        """Fetch the server HTML with a plain HTTP GET — no JS execution.

        This is what a non-rendering crawler (and the first Googlebot pass) sees.
        Returns (html, status_code, final_url).
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await safe_get(
                client,
                url,
                headers={"User-Agent": self.user_agent},
            )
            return response.text, response.status_code, str(response.url)

    async def diff_raw_vs_rendered(
        self, url: str, rendered_html: Optional[str] = None
    ) -> dict[str, Any]:
        """Compare the raw server HTML with the browser-rendered DOM.

        Reports what exists ONLY after JS execution (text, links, title/meta,
        JSON-LD) — the signal that separates a site broken for a non-rendering
        crawler from a healthy one.

        Args:
            url: Page to diff.
            rendered_html: Already-rendered DOM (e.g. ``CrawledPage.raw_html`` from a
                previous crawl). When given, the browser is not driven a second time.

        Degrades cleanly: when the browser crawler is missing or returns nothing,
        the result is ``{"status": "unavailable", "reason": ...}``; it never raises.
        """
        validate_url(url)

        rendered_status = 200
        if rendered_html is None:
            try:
                browser = await self._get_browser_crawler()
                rendered_html, rendered_status, _ = await browser.crawl_page(url)
            except Exception as e:
                logger.info("Render diff unavailable for %s: %s", url, e)
                return {"url": url, "status": "unavailable", "reason": str(e)}

        if rendered_status != 200 or not rendered_html:
            return {
                "url": url,
                "status": "unavailable",
                "reason": f"browser returned no rendered HTML (status {rendered_status})",
            }

        try:
            raw_html, raw_status, _ = await self.fetch_raw_html(url)
        except Exception as e:
            logger.warning("Raw fetch failed for %s: %s", url, e)
            return {"url": url, "status": "error", "reason": f"raw fetch failed: {e}"}

        if raw_status != 200 or not raw_html:
            return {
                "url": url,
                "status": "error",
                "reason": f"raw fetch returned HTTP {raw_status}",
            }

        raw_page = CrawledPage(url=url, status_code=raw_status)
        self._parse_html(raw_page, raw_html)
        rendered_page = CrawledPage(url=url, status_code=rendered_status, js_rendered=True)
        self._parse_html(rendered_page, rendered_html)

        return self._build_render_diff(raw_page, rendered_page)

    async def diff_raw_vs_rendered_batch(
        self, pages: list[CrawledPage], sample: int = 2
    ) -> list[dict[str, Any]]:
        """Run :meth:`diff_raw_vs_rendered` over a sample of successfully crawled pages.

        ``CrawledPage.raw_html`` already holds the browser-rendered DOM, so only the
        no-JS fetch is new work. Degrades to a per-URL ``status: unavailable/error``
        entry — never raises, so a missing browser cannot fail a technical check.
        """
        targets = [p for p in pages if p.status_code == 200][:sample]
        if not targets:
            return []

        try:
            results = await asyncio.gather(
                *(self.diff_raw_vs_rendered(p.url, rendered_html=p.raw_html) for p in targets),
                return_exceptions=True,
            )
        except Exception as e:  # a stubbed crawler without diff support
            logger.warning("Render diff unavailable: %s", e)
            return [{"url": p.url, "status": "unavailable", "reason": str(e)} for p in targets]

        return [
            result
            if isinstance(result, dict)
            else {"url": page.url, "status": "error", "reason": str(result)}
            for page, result in zip(targets, results)
        ]

    def _build_render_diff(self, raw: CrawledPage, rendered: CrawledPage) -> dict[str, Any]:
        """Build the raw-vs-rendered report from two parsed versions of a page."""
        raw_words = set(raw.content.lower().split())
        rendered_only_words: list[str] = []
        seen_words: set[str] = set()
        for word in rendered.content.lower().split():
            if word not in raw_words and word not in seen_words:
                seen_words.add(word)
                rendered_only_words.append(word)

        raw_links = {link.href for link in raw.link_details}
        links_only_in_rendered = sorted({link.href for link in rendered.link_details} - raw_links)

        raw_schema = _schema_types(raw.structured_data)
        schema_only_in_rendered = sorted(_schema_types(rendered.structured_data) - raw_schema)

        content_gap_ratio = (
            len(rendered_only_words) / rendered.word_count if rendered.word_count else 0.0
        )

        title_only_in_rendered = bool(rendered.title and not raw.title)
        meta_only_in_rendered = bool(rendered.meta_description and not raw.meta_description)

        return {
            "url": raw.url,
            "status": "ok",
            "js_dependent": bool(
                title_only_in_rendered
                or meta_only_in_rendered
                or links_only_in_rendered
                or schema_only_in_rendered
                or content_gap_ratio >= _JS_CONTENT_GAP_THRESHOLD
            ),
            "raw_word_count": raw.word_count,
            "rendered_word_count": rendered.word_count,
            "content_gap_ratio": round(content_gap_ratio, 3),
            "words_only_in_rendered": len(rendered_only_words),
            "words_only_in_rendered_sample": rendered_only_words[:25],
            "links_only_in_rendered": links_only_in_rendered[:50],
            "links_only_in_rendered_count": len(links_only_in_rendered),
            "structured_data_only_in_rendered": schema_only_in_rendered,
            "title": {
                "raw": raw.title,
                "rendered": rendered.title,
                "only_in_rendered": title_only_in_rendered,
                "differs": raw.title != rendered.title,
            },
            "meta_description": {
                "raw": raw.meta_description,
                "rendered": rendered.meta_description,
                "only_in_rendered": meta_only_in_rendered,
                "differs": raw.meta_description != rendered.meta_description,
            },
        }

    async def _get_browser_crawler(self):
        """Lazy-init the BROWSER_BACKEND crawler. Raises RuntimeError if none is usable."""
        if self._browser_crawler is None:
            backend = _resolve_browser_backend(settings.BROWSER_BACKEND)
            if backend == "agent-browser":
                from app.services.agent_browser_crawler import AgentBrowserCrawler

                self._browser_crawler = AgentBrowserCrawler(
                    headless=settings.BROWSER_HEADLESS,
                    timeout=settings.BROWSER_TIMEOUT,
                    idle_timeout=settings.BROWSER_IDLE_TIMEOUT,
                    max_concurrent=settings.BROWSER_MAX_CONCURRENT,
                    cdp_url=settings.BROWSER_CDP,
                    agent_browser_path=settings.BROWSER_AGENT_PATH,
                )
            else:
                from app.services.browser_crawler import BrowserCrawler

                self._browser_crawler = BrowserCrawler(
                    headless=settings.BROWSER_HEADLESS,
                    timeout=settings.BROWSER_TIMEOUT,
                    idle_timeout=settings.BROWSER_IDLE_TIMEOUT,
                    max_concurrent=settings.BROWSER_MAX_CONCURRENT,
                    cdp_url=settings.BROWSER_CDP,
                    ghostchrome_path=settings.GHOSTCHROME_PATH,
                )
            logger.info("Browser crawler backend: %s", backend)
        return self._browser_crawler

    async def close(self):
        """Clean up browser resources."""
        if self._browser_crawler:
            await self._browser_crawler.close()
            self._browser_crawler = None

    def _parse_html(self, page: CrawledPage, html: str):
        """Parse HTML content and extract SEO-relevant data."""
        soup = BeautifulSoup(html, "lxml")

        # Title
        title_tag = soup.find("title")
        if title_tag:
            page.title = title_tag.get_text(strip=True)

        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            page.meta_description = _attr_str(meta_desc.get("content", ""))

        # H1
        h1_tag = soup.find("h1")
        if h1_tag:
            page.h1 = h1_tag.get_text(strip=True)

        # Canonical URL
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        if canonical_tag:
            page.canonical_url = _attr_str(canonical_tag.get("href", ""))

        # Meta robots
        meta_robots = soup.find("meta", attrs={"name": "robots"})
        if meta_robots:
            page.meta_robots = _attr_str(meta_robots.get("content", ""))

        # hreflang annotations (<link rel="alternate" hreflang="..." href="...">)
        for link in soup.find_all("link", attrs={"hreflang": True}):
            rel_raw = link.get("rel")
            rel_values = rel_raw if isinstance(rel_raw, list) else ([rel_raw] if rel_raw else [])
            if "alternate" not in [r.lower() for r in rel_values if isinstance(r, str)]:
                continue
            lang = _attr_str(link.get("hreflang")).strip()
            href = _attr_str(link.get("href")).strip()
            if lang and href:
                page.hreflang[lang] = urljoin(page.url, href)

        # Structured data (JSON-LD)
        for script in soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        page.structured_data.extend(data)
                    else:
                        page.structured_data.append(data)
                except (json.JSONDecodeError, TypeError):
                    pass

        # Internal links + link details
        parsed_page = urlparse(page.url)
        base_domain = f"{parsed_page.scheme}://{parsed_page.netloc}"
        for a_tag in soup.find_all("a", href=True):
            href = _attr_str(a_tag["href"])
            absolute_url = urljoin(base_domain, href)
            parsed_link = urlparse(absolute_url)
            is_internal = parsed_link.netloc == parsed_page.netloc

            # Build rel string from BS4 (rel is multi-valued → list[str] at runtime)
            rel_raw = a_tag.get("rel")
            rel_attr = rel_raw if isinstance(rel_raw, list) else ([rel_raw] if rel_raw else [])
            rel_str = " ".join(rel_attr) if rel_attr else None
            nofollow = "nofollow" in rel_attr

            if is_internal:
                page.internal_links.append(absolute_url)

            page.link_details.append(
                LinkInfo(
                    href=absolute_url,
                    rel=rel_str,
                    anchor_text=a_tag.get_text(strip=True)[:200],
                    is_internal=is_internal,
                    nofollow=nofollow,
                )
            )

        # Main content
        noise_tags = ["script", "style", "nav", "footer", "header", "template"]
        main_content = soup.find("main") or soup.find("article") or soup.find("body")
        if main_content:
            for tag in main_content.find_all(noise_tags):
                tag.decompose()

            text = main_content.get_text(separator=" ", strip=True)

            # React 19 / Next.js streaming (PPR/Suspense) delivers the real content
            # inside sibling <template> holders, leaving <main>/<article> almost empty
            # until JS hydration. Fall back to <body> so streamed SSR pages are not
            # mistaken for thin content (word_count = 0).
            if len(text.split()) < 50 and main_content.name != "body":
                body = soup.find("body")
                if body:
                    for tag in body.find_all(noise_tags):
                        tag.decompose()
                    text = body.get_text(separator=" ", strip=True)

            page.content = text
            page.word_count = len(text.split())

        # Listing item count (if config provided)
        if self.listing_config:
            page.item_count = self._count_listing_items(soup, html, self.listing_config)

    def _count_listing_items(
        self, soup: BeautifulSoup, html: str, config: ListingConfig
    ) -> Optional[int]:
        """Count listing items on the page using configurable selectors."""
        # Method 1: CSS selectors
        for selector in config.css_selectors:
            try:
                items = soup.select(selector)
                if items:
                    return len(items)
            except Exception:
                continue

        # Method 2: Specific count selector
        if config.count_css_selector:
            try:
                count_el = soup.select_one(config.count_css_selector)
                if count_el:
                    text = count_el.get_text(strip=True)
                    match = re.search(r"(\d+)", text)
                    if match:
                        return int(match.group(1))
            except Exception:
                pass

        # Method 3: Text patterns
        for pattern in config.text_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                return int(match.group(1))

        return None

    async def check_url_status(self, url: str) -> tuple[int, Optional[str]]:
        """Quick SSRF-safe reachability check."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await safe_get(client, url, headers={"User-Agent": self.user_agent})
                return response.status_code, None
        except Exception as e:
            return 0, str(e)
