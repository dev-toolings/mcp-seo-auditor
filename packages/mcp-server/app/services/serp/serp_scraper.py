"""Direct SERP scraper using agent-browser CLI — no external API required.

Scrapes Google search results using agent-browser with a persistent
profile (cookies survive across runs → no repeat consent pages).
"""

import asyncio
import json
import logging
import os
import random
from pathlib import Path
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Safety limits
MAX_KEYWORDS_PER_CALL = 10
MIN_DELAY_BETWEEN_REQUESTS = 3.0  # seconds
MAX_DELAY_BETWEEN_REQUESTS = 6.0  # seconds

# Persistent profile directory for cookies/consent
_PROFILE_DIR = Path.home() / ".cache" / "seo-auditor" / "browser-profile"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_SESSION_NAME = "serp-scraper"
_CMD_TIMEOUT = 30  # seconds


def _attr_str(value: object) -> str:
    """Coerce a BeautifulSoup attribute value to str (href is single-valued)."""
    return value if isinstance(value, str) else ""


def _get_cdp_url() -> str:
    """Read CDP URL from settings or env, fallback to empty string."""
    try:
        from app.core.config import settings

        return getattr(settings, "BROWSER_CDP", "") or ""
    except Exception:
        return os.environ.get("BROWSER_CDP", "")


class SERPScraper:
    """Scrape Google SERPs using agent-browser CLI with persistent profile."""

    def __init__(self, crawler_service=None, cdp_url: str = ""):
        self._cdp_url = cdp_url
        self._session_ready = False

    def _base_args(self) -> list[str]:
        """Build base args for every agent-browser command."""
        args = [
            "agent-browser",
            "--session",
            _SESSION_NAME,
            "--profile",
            str(_PROFILE_DIR),
            "--user-agent",
            _USER_AGENT,
        ]
        cdp = self._cdp_url or _get_cdp_url()
        if cdp:
            args.extend(["--cdp", cdp])
        return args

    async def _run_cmd(self, *args: str) -> dict:
        """Run an agent-browser command with --json and return parsed output.

        Raises RuntimeError on timeout or non-zero exit code.
        """
        cmd = self._base_args() + ["--json"] + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CMD_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f"agent-browser timed out after {_CMD_TIMEOUT}s: {' '.join(args)}")

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"agent-browser exited {proc.returncode}: {err}")

        raw = stdout.decode(errors="replace").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    async def _run_cmd_raw(self, *args: str) -> tuple[int, str, str]:
        """Run an agent-browser command and return (returncode, stdout, stderr).

        Does not add --json. Swallows timeouts (returns rc=1).
        """
        cmd = self._base_args() + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CMD_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            return (1, "", "timeout")

        return (
            proc.returncode or 0,
            stdout.decode(errors="replace").strip(),
            stderr.decode(errors="replace").strip(),
        )

    async def _ensure_session(self):
        """Mark session as ready. No explicit launch needed — daemon auto-starts."""
        if self._session_ready:
            return
        _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._session_ready = True
        logger.info(
            "SERP scraper session '%s' initialized (profile: %s)",
            _SESSION_NAME,
            _PROFILE_DIR,
        )

    async def scrape(
        self,
        keywords: list[str],
        lang: str = "fr",
        geo: str = "FR",
        num_results: int = 20,
        site_domain: str | None = None,
    ) -> list[dict]:
        """Scrape Google SERPs for given keywords.

        Args:
            keywords: Keywords to search (max 10)
            lang: Language (hl parameter)
            geo: Country (gl parameter)
            num_results: Number of results to request
            site_domain: Optional domain to find position for

        Returns:
            List of result dicts per keyword
        """
        keywords = keywords[:MAX_KEYWORDS_PER_CALL]
        results = []

        for i, keyword in enumerate(keywords):
            if i > 0:
                delay = random.uniform(
                    MIN_DELAY_BETWEEN_REQUESTS,
                    MAX_DELAY_BETWEEN_REQUESTS,
                )
                await asyncio.sleep(delay)

            try:
                result = await self._scrape_keyword(keyword, lang, geo, num_results, site_domain)
                results.append(result)
            except Exception as e:
                logger.warning("SERP scrape failed for '%s': %s", keyword, e)
                results.append({"keyword": keyword, "error": str(e)})

        return results

    async def _scrape_keyword(
        self,
        keyword: str,
        lang: str,
        geo: str,
        num: int,
        site_domain: str | None,
    ) -> dict:
        """Scrape SERP for a single keyword."""
        url = f"https://www.google.com/search?q={quote_plus(keyword)}&hl={lang}&gl={geo}&num={num}"

        await self._ensure_session()

        # Navigate to Google SERP
        await self._run_cmd("open", url)

        # Check current URL for consent/captcha redirects
        url_result = await self._run_cmd("get", "url")
        current_url = url_result.get("url", url_result.get("raw", ""))

        # Handle Google consent page
        if "consent.google" in current_url:
            await self._handle_consent()
            # Re-check URL after consent
            url_result = await self._run_cmd("get", "url")
            current_url = url_result.get("url", url_result.get("raw", ""))

        # Handle CAPTCHA
        if "/sorry/" in current_url:
            return {
                "keyword": keyword,
                "error": (
                    "Google CAPTCHA detected — try again later or use BROWSER_CDP for a real Chrome"
                ),
            }

        # Wait for results to render (swallow errors)
        await self._run_cmd_raw("wait", "div#search", "--timeout", "5000")

        # Get page HTML
        html_result = await self._run_cmd("get", "html", "html")
        html = html_result.get("html", html_result.get("raw", ""))

        if not html:
            return {"keyword": keyword, "error": "Empty HTML response"}

        return self._parse_serp(html, keyword, site_domain)

    async def _handle_consent(self) -> None:
        """Dismiss Google consent/cookie dialog."""
        consent_selectors = [
            "button#L2AGLb",
            "button[aria-label*='Accept']",
            "button[aria-label*='Accepter']",
            "form[action*='consent'] button",
        ]
        for selector in consent_selectors:
            rc, _, _ = await self._run_cmd_raw("click", selector)
            if rc == 0:
                # Consent dismissed — wait for page to settle
                await self._run_cmd_raw("wait", "body", "--timeout", "2000")
                return
        logger.warning("Could not dismiss Google consent page")

    async def close(self):
        """Close the agent-browser session."""
        if self._session_ready:
            await self._run_cmd_raw("close")
            self._session_ready = False

    def _parse_serp(self, html: str, keyword: str, site_domain: str | None) -> dict:
        """Parse Google SERP HTML and extract results + features."""
        soup = BeautifulSoup(html, "html.parser")

        # Extract organic results
        organic_results = self._extract_organic_results(soup)

        # Detect SERP features
        features = self._detect_features(soup, html)

        # Find site position
        site_positions = []
        if site_domain and organic_results:
            for r in organic_results:
                r_domain = urlparse(r.get("url", "")).netloc
                if site_domain in r_domain:
                    site_positions.append(
                        {
                            "position": r["position"],
                            "url": r["url"],
                            "title": r["title"],
                        }
                    )

        return {
            "keyword": keyword,
            "results": organic_results,
            "features_detected": features,
            "total_results": len(organic_results),
            "site_positions": site_positions if site_domain else None,
            "site_visible": bool(site_positions) if site_domain else None,
        }

    def _extract_organic_results(self, soup: BeautifulSoup) -> list[dict]:
        """Extract organic search results from Google SERP.

        Uses h3 > parent <a> pattern which is stable across Google layouts.
        Falls back to div.g for older markup.
        """
        results = []
        seen_urls = set()
        position = 0

        # Primary: find all h3 with a parent <a href="http...">
        for h3 in soup.select("h3"):
            parent_a = h3.find_parent("a")
            if not parent_a:
                continue
            href = _attr_str(parent_a.get("href", ""))
            if not href.startswith("http"):
                continue
            if "google.com" in href and "/search" in href:
                continue
            if href in seen_urls:
                continue

            seen_urls.add(href)
            position += 1
            title = h3.get_text(strip=True)

            # Snippet: sibling or nearby text after the link
            snippet = ""
            container = parent_a.find_parent(
                "div", attrs={"data-sokoban": True}
            ) or parent_a.find_parent("div")
            if container:
                for el in container.select("[data-sncf], .VwiC3b, div[style*='line']"):
                    text = el.get_text(strip=True)
                    if text and text != title:
                        snippet = text[:300]
                        break

            results.append(
                {
                    "position": position,
                    "url": href,
                    "title": title,
                    "snippet": snippet,
                }
            )

        # Fallback: div.g (older Google markup)
        if not results:
            for g_div in soup.select("div.g"):
                link = g_div.select_one("a[href]")
                if not link:
                    continue
                href = _attr_str(link.get("href", ""))
                if not href.startswith("http"):
                    continue
                if "google.com" in href:
                    continue
                if href in seen_urls:
                    continue

                seen_urls.add(href)
                position += 1
                title_el = g_div.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet_el = g_div.select_one(".VwiC3b") or g_div.select_one("div.IsZvec")
                snippet = snippet_el.get_text(strip=True)[:300] if snippet_el else ""
                results.append(
                    {
                        "position": position,
                        "url": href,
                        "title": title,
                        "snippet": snippet,
                    }
                )

        return results

    def _detect_features(self, soup: BeautifulSoup, html: str) -> list[str]:
        """Detect SERP features present on the page."""
        features = []

        # Featured Snippet (position 0 answer box)
        if soup.select_one("div.xpdopen") or soup.select_one("div[data-attrid='wa:/description']"):
            features.append("featured_snippet")

        # People Also Ask
        if (
            soup.select_one("div.related-question-pair")
            or "People also ask" in html
            or "Autres questions posées" in html
        ):
            features.append("people_also_ask")

        # Knowledge Panel (right sidebar)
        if soup.select_one("div.kp-wholepage") or soup.select_one("div[data-attrid]"):
            features.append("knowledge_panel")

        # Video Carousel
        if soup.select_one("div.HD8Pae") or soup.select_one("video-voyager"):
            features.append("video_carousel")

        # Image Pack
        if soup.select_one("div.islrc") or soup.select_one("g-scrolling-carousel[data-lpage]"):
            features.append("image_pack")

        # Local Pack / Map
        if soup.select_one("div.VkpGBb") or "local-pack" in html.lower():
            features.append("local_pack")

        # Top Stories
        if soup.select_one("g-section-with-header[data-hveid]") or soup.select_one("div.JJZKK"):
            features.append("top_stories")

        # AI Overview / SGE
        if soup.select_one("div[data-sgrd]") or "ai-overview" in html.lower():
            features.append("ai_overview")

        # Shopping Results
        if soup.select_one("div.commercial-unit-desktop-top"):
            features.append("shopping_results")

        # Sitelinks
        if soup.select_one("div.usJj9c") or soup.select_one("table.jmjoTe"):
            features.append("sitelinks")

        return features
