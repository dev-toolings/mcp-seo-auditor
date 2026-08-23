"""Technical SEO checker service."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.core.safe_http import safe_get
from app.core.security import validate_url
from app.services.crawler_service import CrawledPage
from app.services.sitemap_parser import SitemapUrl

logger = logging.getLogger(__name__)

# BCP 47 subset accepted by Google: language[-script][-region],
# region being an ISO 3166-1 alpha-2 code or a UN M49 numeric code.
_HREFLANG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?(-([a-z]{2}|[0-9]{3}))?$", re.IGNORECASE)
_X_DEFAULT = "x-default"


def _is_valid_hreflang(code: str) -> bool:
    """Check a hreflang value against the BCP 47 shape Google accepts."""
    code = code.strip()
    if code.lower() == _X_DEFAULT:
        return True
    return bool(_HREFLANG_RE.match(code))


@dataclass
class RobotsTxtResult:
    """Parsed robots.txt data."""

    url: str
    status_code: int = 0
    rules: list[dict[str, str]] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    disallow_patterns: list[str] = field(default_factory=list)
    allow_patterns: list[str] = field(default_factory=list)
    crawl_delay: Optional[float] = None
    raw_content: str = ""
    error: Optional[str] = None


class TechnicalSEOCheckerService:
    """Technical SEO checks: robots.txt, redirects, canonicals, hreflang, meta robots."""

    def __init__(self, user_agent: str | None = None, timeout: int | None = None):
        self.user_agent = user_agent or settings.CRAWLER_USER_AGENT
        self.timeout = timeout or settings.CRAWLER_TIMEOUT

    async def parse_robots_txt(self, url: str) -> dict[str, Any]:
        """Fetch and parse robots.txt from a URL."""
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        result = RobotsTxtResult(url=robots_url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await safe_get(
                    client,
                    robots_url,
                    headers={"User-Agent": self.user_agent},
                )
                result.status_code = response.status_code

                if response.status_code != 200:
                    result.error = f"HTTP {response.status_code}"
                    return self._robots_to_dict(result)

                result.raw_content = response.text
                self._parse_robots_content(result, response.text)

        except httpx.RequestError as e:
            result.error = str(e)

        return self._robots_to_dict(result)

    def _parse_robots_content(self, result: RobotsTxtResult, content: str):
        """Parse robots.txt content."""
        current_agent = "*"

        for line in content.splitlines():
            line = line.strip()

            # Remove comments
            if "#" in line:
                line = line[: line.index("#")].strip()

            if not line:
                continue

            if ":" not in line:
                continue

            directive, value = line.split(":", 1)
            directive = directive.strip().lower()
            value = value.strip()

            if directive == "user-agent":
                current_agent = value
            elif directive == "disallow":
                if value:
                    result.disallow_patterns.append(value)
                    result.rules.append(
                        {
                            "user_agent": current_agent,
                            "directive": "disallow",
                            "path": value,
                        }
                    )
            elif directive == "allow":
                if value:
                    result.allow_patterns.append(value)
                    result.rules.append(
                        {
                            "user_agent": current_agent,
                            "directive": "allow",
                            "path": value,
                        }
                    )
            elif directive == "sitemap":
                result.sitemaps.append(value)
            elif directive == "crawl-delay":
                try:
                    result.crawl_delay = float(value)
                except ValueError:
                    pass

    def _robots_to_dict(self, result: RobotsTxtResult) -> dict[str, Any]:
        """Convert RobotsTxtResult to dict."""
        return {
            "url": result.url,
            "status_code": result.status_code,
            "rules_count": len(result.rules),
            "rules": result.rules[:50],
            "sitemaps": result.sitemaps,
            "disallow_patterns": result.disallow_patterns,
            "allow_patterns": result.allow_patterns,
            "crawl_delay": result.crawl_delay,
            "error": result.error,
        }

    async def check_redirect_chain(self, url: str, max_redirects: int = 10) -> dict[str, Any]:
        """Follow redirects and report the chain."""
        chain = []
        current_url = validate_url(url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for _ in range(max_redirects):
                    response = await client.get(
                        current_url,
                        headers={"User-Agent": self.user_agent},
                        follow_redirects=False,
                    )

                    chain.append(
                        {
                            "url": current_url,
                            "status_code": response.status_code,
                        }
                    )

                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if location:
                            current_url = validate_url(urljoin(current_url, location))
                        else:
                            break
                    else:
                        break

        except httpx.RequestError as e:
            chain.append({"url": current_url, "error": str(e)})

        return {
            "initial_url": url,
            "final_url": chain[-1]["url"] if chain else url,
            "redirects": len(chain) - 1,
            "chain": chain,
            "has_redirect_chain": len(chain) > 2,
        }

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize URL for comparison: lowercase scheme+host, strip trailing slash, strip www."""
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/") or "/"
        return f"{parsed.scheme}://{netloc}{path}"

    def validate_canonicals(self, pages: list[CrawledPage]) -> list[dict[str, Any]]:
        """Validate canonical URL consistency across crawled pages."""
        issues = []

        for page in pages:
            if page.status_code != 200:
                continue

            # Skip pages that were redirected — the redirect itself handles canonicalization
            if page.final_url:
                continue

            if not page.canonical_url:
                issues.append(
                    {
                        "url": page.url,
                        "issue": "missing_canonical",
                        "description": "No canonical tag found",
                    }
                )
                continue

            # Check self-referencing canonical (with URL normalization)
            # page.final_url is always falsy here (we continued above if truthy)
            if self._normalize_url(page.canonical_url) != self._normalize_url(page.url):
                issues.append(
                    {
                        "url": page.url,
                        "issue": "non_self_canonical",
                        "canonical": page.canonical_url,
                        "description": f"Canonical points to different URL: {page.canonical_url}",
                    }
                )

        return issues

    def validate_hreflang(
        self,
        sitemap_urls: list[SitemapUrl] | None = None,
        pages: list[CrawledPage] | None = None,
    ) -> list[dict[str, Any]]:
        """Validate hreflang annotations from crawled HTML and/or sitemap data.

        Args:
            sitemap_urls: Sitemap entries carrying ``xhtml:link`` alternates.
            pages: Crawled pages carrying ``<link rel="alternate" hreflang>`` tags.

        Checks reciprocity (A points to B but B does not point back), invalid
        language/region codes, missing self-reference and missing ``x-default``.
        """
        issues: list[dict[str, Any]] = []

        # Merge both sources into one map: url -> {lang: href}
        hreflang_map: dict[str, dict[str, str]] = {}
        sources: dict[str, set[str]] = {}
        all_known_urls: set[str] = set()

        for sitemap_url in sitemap_urls or []:
            all_known_urls.add(self._normalize_url(sitemap_url.loc))
            if sitemap_url.alternates:
                hreflang_map.setdefault(sitemap_url.loc, {}).update(sitemap_url.alternates)
                sources.setdefault(sitemap_url.loc, set()).add("sitemap")

        for page in pages or []:
            if page.status_code != 200:
                continue
            all_known_urls.add(self._normalize_url(page.url))
            if page.hreflang:
                hreflang_map.setdefault(page.url, {}).update(page.hreflang)
                sources.setdefault(page.url, set()).add("html")

        # Normalized URL -> the key it is stored under, so www/trailing-slash
        # variants still resolve to the same document.
        by_normalized = {self._normalize_url(url): url for url in hreflang_map}

        for url, alternates in hreflang_map.items():
            normalized_url = self._normalize_url(url)
            source = "+".join(sorted(sources.get(url, set()))) or "unknown"

            for lang, alt_url in alternates.items():
                if not _is_valid_hreflang(lang):
                    issues.append(
                        {
                            "url": url,
                            "issue": "invalid_hreflang_code",
                            "language": lang,
                            "alternate_url": alt_url,
                            "source": source,
                            "description": f"Invalid hreflang value '{lang}' (expected a BCP 47 code like 'en', 'fr-BE' or 'x-default')",
                        }
                    )

                normalized_alt = self._normalize_url(alt_url)
                if normalized_alt == normalized_url:
                    continue  # Skip self-reference

                target_key = by_normalized.get(normalized_alt)
                if target_key is not None:
                    # The alternate should reference back
                    back_refs = {self._normalize_url(v) for v in hreflang_map[target_key].values()}
                    if normalized_url not in back_refs:
                        issues.append(
                            {
                                "url": url,
                                "issue": "missing_reciprocal_hreflang",
                                "language": lang,
                                "alternate_url": alt_url,
                                "source": source,
                                "description": f"Alternate {alt_url} ({lang}) does not reference back to {url}",
                            }
                        )
                elif normalized_alt in all_known_urls:
                    # URL exists but has no hreflang - missing reciprocal
                    issues.append(
                        {
                            "url": url,
                            "issue": "missing_reciprocal_hreflang",
                            "language": lang,
                            "alternate_url": alt_url,
                            "source": source,
                            "description": f"Alternate {alt_url} ({lang}) has no hreflang annotations referencing back to {url}",
                        }
                    )

            if not alternates:
                continue

            # Check self-reference
            has_self_ref = any(
                self._normalize_url(alt_url) == normalized_url for alt_url in alternates.values()
            )
            if not has_self_ref:
                issues.append(
                    {
                        "url": url,
                        "issue": "missing_self_hreflang",
                        "source": source,
                        "description": "Hreflang does not include self-referencing entry",
                    }
                )

            # Check x-default
            if not any(lang.lower() == _X_DEFAULT for lang in alternates):
                issues.append(
                    {
                        "url": url,
                        "issue": "missing_x_default_hreflang",
                        "source": source,
                        "description": "Hreflang cluster has no x-default entry for unmatched languages",
                    }
                )

        return issues

    def check_meta_robots(
        self,
        pages: list[CrawledPage],
        sitemap_urls: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Detect noindex in sitemap and contradictory directives."""
        issues = []
        sitemap_set = set(sitemap_urls or [])

        for page in pages:
            if page.status_code != 200:
                continue

            if not page.meta_robots:
                continue

            directives = {
                d.strip().lower()
                for part in page.meta_robots.split(",")
                for d in part.split()
                if d.strip()
            }
            has_noindex = "noindex" in directives or "none" in directives

            # Check for noindex pages in sitemap
            if has_noindex and page.url in sitemap_set:
                issues.append(
                    {
                        "url": page.url,
                        "issue": "noindex_in_sitemap",
                        "meta_robots": page.meta_robots,
                        "description": "Page has noindex but is present in the sitemap",
                    }
                )

            # Check for contradictory directives
            if has_noindex and "index" in directives:
                issues.append(
                    {
                        "url": page.url,
                        "issue": "contradictory_directives",
                        "meta_robots": page.meta_robots,
                        "description": "Contradictory directives: both index and noindex",
                    }
                )

        return issues
