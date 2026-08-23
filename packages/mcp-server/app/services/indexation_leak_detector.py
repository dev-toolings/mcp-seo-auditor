"""Indexation leak detector — finds internal links that leak crawl budget to noindex/auth pages."""

import re
from urllib.parse import urlparse

# Auth path patterns (without and with query strings)
AUTH_PATH_PATTERNS = re.compile(
    r"^/(connexion|login|signin|inscription|register|signup|mot-de-passe|forgot-password)(/|$|\?)",
    re.IGNORECASE,
)


class IndexationLeakDetectorService:
    """Detects internal links that leak indexation equity (no nofollow) to non-indexable targets."""

    def detect_leaks(
        self,
        source_pages,
        disallow_patterns: list[str],
        target_pages: dict | None = None,
        redirect_results: dict | None = None,
    ) -> dict:
        """Analyze source pages for indexation leaks.

        Args:
            source_pages: List of CrawledPage objects (with link_details populated).
            disallow_patterns: Disallow patterns from robots.txt.
            target_pages: Dict of url -> CrawledPage for target checking (optional).
            redirect_results: Dict of url -> final redirect URL (optional).

        Returns:
            Report dict with leaks found, severity, and recommendations.
        """
        target_pages = target_pages or {}
        redirect_results = redirect_results or {}

        leaks = []
        seen = set()
        total_links = 0

        for page in source_pages:
            for link in page.link_details:
                if not link.is_internal or link.nofollow:
                    continue

                total_links += 1
                parsed = urlparse(link.href)
                path = parsed.path

                # Check all leak types
                leak_types = []

                # 1. robots_disallow
                if self._url_matches_any_disallow(path, disallow_patterns):
                    leak_types.append("robots_disallow")

                # 2. auth_redirect_pattern
                if self._check_auth_pattern(path):
                    leak_types.append("auth_redirect_pattern")

                # 3. noindex_target
                target = target_pages.get(link.href)
                if target and target.meta_robots and "noindex" in target.meta_robots.lower():
                    leak_types.append("noindex_target")

                # 4. redirect_to_auth
                final_url = redirect_results.get(link.href)
                if final_url and self._check_auth_pattern(urlparse(final_url).path):
                    leak_types.append("redirect_to_auth")

                for leak_type in leak_types:
                    key = (page.url, link.href, leak_type)
                    if key in seen:
                        continue
                    seen.add(key)

                    leaks.append(
                        {
                            "source_url": page.url,
                            "target_url": link.href,
                            "leak_type": leak_type,
                            "anchor_text": link.anchor_text,
                            "rel": link.rel,
                            "fix": self._get_fix(leak_type),
                        }
                    )

        return self._build_report(leaks, len(source_pages), total_links, disallow_patterns)

    def _url_matches_any_disallow(self, path: str, patterns: list[str]) -> bool:
        """Check if path matches any disallow pattern."""
        return any(self._url_matches_disallow(path, p) for p in patterns)

    @staticmethod
    def _url_matches_disallow(path: str, pattern: str) -> bool:
        """Match a path against a robots.txt Disallow pattern.

        Supports prefix match, wildcard (*), and end anchor ($).
        """
        if not pattern:
            return False

        # End anchor
        if pattern.endswith("$"):
            regex_pattern = re.escape(pattern[:-1]).replace(r"\*", ".*") + "$"
        else:
            regex_pattern = re.escape(pattern).replace(r"\*", ".*")

        return bool(re.match(regex_pattern, path))

    @staticmethod
    def _check_auth_pattern(path: str) -> bool:
        """Check if a URL path matches an auth/login pattern."""
        return bool(AUTH_PATH_PATTERNS.search(path))

    @staticmethod
    def _get_fix(leak_type: str) -> str:
        fixes = {
            "robots_disallow": 'Add rel="nofollow" — target is blocked by robots.txt',
            "auth_redirect_pattern": 'Add rel="nofollow" — link points to auth/login page',
            "noindex_target": 'Add rel="nofollow" — target has meta robots noindex',
            "redirect_to_auth": 'Add rel="nofollow" — target redirects to auth page',
        }
        return fixes.get(leak_type, 'Add rel="nofollow" to this link')

    @staticmethod
    def _build_report(
        leaks: list[dict],
        pages_audited: int,
        total_links: int,
        disallow_patterns: list[str],
        max_leaks: int = 20,
    ) -> dict:
        """Build the final report with severity and summary.

        Truncates detailed leaks to max_leaks to keep MCP response compact.
        Full data is available via summary_by_type and affected_targets.
        """
        leak_count = len(leaks)

        if leak_count > 20:
            severity = "critical"
        elif leak_count > 5:
            severity = "high"
        elif leak_count > 0:
            severity = "medium"
        else:
            severity = "none"

        summary_by_type: dict[str, dict] = {}
        for leak in leaks:
            lt = leak["leak_type"]
            if lt not in summary_by_type:
                summary_by_type[lt] = {"count": 0, "affected_targets": set()}
            summary_by_type[lt]["count"] += 1
            summary_by_type[lt]["affected_targets"].add(leak["target_url"])

        # Convert sets to sorted lists for JSON serialization
        summary = {
            lt: {
                "count": data["count"],
                "unique_targets": len(data["affected_targets"]),
                "sample_targets": sorted(data["affected_targets"])[:5],
            }
            for lt, data in summary_by_type.items()
        }

        result = {
            "pages_audited": pages_audited,
            "total_links_analyzed": total_links,
            "leaks_found": leak_count,
            "severity": severity,
            "robots_txt_disallows": disallow_patterns,
            "summary_by_type": summary,
            "leaks": leaks[:max_leaks],
        }

        if leak_count > max_leaks:
            result["truncated"] = True
            result["showing"] = max_leaks

        return result
