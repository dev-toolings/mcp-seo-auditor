"""Sitemap analyzer service - detects SEO issues in sitemaps."""

import logging
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from app.models.issue import Issue
from app.services.sitemap_parser import SitemapData, SitemapUrl

logger = logging.getLogger(__name__)


class SitemapAnalyzerService:
    """Analyze sitemap data for SEO issues."""

    def __init__(self, max_depth: int = 5, combination_threshold: int = 1000):
        self.max_depth = max_depth
        self.combination_threshold = combination_threshold

    def analyze(self, sitemap_data: SitemapData) -> list[Issue]:
        """Run all analysis checks on sitemap data."""
        issues = []

        issues.extend(self._check_duplicate_urls(sitemap_data.urls))
        issues.extend(self._check_query_param_vs_routes(sitemap_data.urls))
        issues.extend(self._check_identical_timestamps(sitemap_data.urls))
        issues.extend(self._check_missing_fields(sitemap_data.urls))
        issues.extend(self._check_deep_url_patterns(sitemap_data.urls))

        return issues

    def _check_duplicate_urls(self, urls: list[SitemapUrl]) -> list[Issue]:
        """Find exact duplicate URLs."""
        issues = []
        url_counts = Counter(u.loc for u in urls)

        duplicates = [url for url, count in url_counts.items() if count > 1]
        if duplicates:
            issues.append(
                Issue(
                    issue_type="duplicate_url",
                    severity="critical",
                    urls=duplicates[:10],
                    description=f"Found {len(duplicates)} duplicate URLs in sitemap",
                    recommendation="Remove duplicate entries from sitemap generation logic",
                )
            )

        return issues

    def _check_query_param_vs_routes(self, urls: list[SitemapUrl]) -> list[Issue]:
        """Detect URLs that might cannibalize each other (query params vs clean routes).

        Generic detection: groups URLs with query params and searches for
        equivalent clean routes containing the same parameter values.
        """
        issues: list[Issue] = []

        query_urls = [u for u in urls if "?" in u.loc]
        clean_urls = [u for u in urls if "?" not in u.loc]

        if not query_urls or not clean_urls:
            return issues

        # Build index of clean URL path segments
        clean_by_segment: dict[str, list[str]] = defaultdict(list)
        for u in clean_urls:
            parsed = urlparse(u.loc)
            parts = [p.lower() for p in parsed.path.split("/") if p]
            for part in parts:
                clean_by_segment[part].append(u.loc)

        for qu in query_urls:
            parsed = urlparse(qu.loc)
            params = parse_qs(parsed.query)

            # Extract all param values
            param_values: list[str] = []
            for values in params.values():
                param_values.extend(v.lower() for v in values)

            if not param_values:
                continue

            # Find clean URLs matching any param value
            matching = set()
            for value in param_values:
                for clean_url in clean_by_segment.get(value, []):
                    matching.add(clean_url)

            if matching:
                issues.append(
                    Issue(
                        issue_type="duplicate_url",
                        severity="critical",
                        urls=[qu.loc] + list(matching)[:3],
                        description="Query param URL may cannibalize clean route",
                        recommendation=f"Consolidate to canonical URL {min(matching, key=len)}",
                    )
                )

        return issues

    def _check_identical_timestamps(self, urls: list[SitemapUrl]) -> list[Issue]:
        """Detect if many URLs have identical lastmod timestamps."""
        issues: list[Issue] = []

        timestamps = [u.lastmod for u in urls if u.lastmod]
        if not timestamps:
            return issues

        timestamp_counts = Counter(timestamps)
        most_common = timestamp_counts.most_common(1)

        if most_common:
            ts, count = most_common[0]
            total = len(timestamps)
            ratio = count / total

            if ratio > 0.8 and count > 10:
                issues.append(
                    Issue(
                        issue_type="identical_timestamp",
                        severity="warning",
                        urls=[],
                        description=f"{count}/{total} URLs ({ratio:.0%}) have identical lastmod: {ts}",
                        recommendation="Use actual modification timestamps for each page",
                    )
                )

        # Check for timestamps in the future
        now = datetime.now(tz=timestamps[0].tzinfo if timestamps[0].tzinfo else None)
        future_urls = [u.loc for u in urls if u.lastmod and u.lastmod > now]
        if future_urls:
            issues.append(
                Issue(
                    issue_type="future_timestamp",
                    severity="warning",
                    urls=future_urls[:5],
                    description=f"{len(future_urls)} URLs have lastmod in the future",
                    recommendation="Fix timestamps to be in the past",
                )
            )

        return issues

    def _check_missing_fields(self, urls: list[SitemapUrl]) -> list[Issue]:
        """Check for missing recommended fields."""
        issues = []

        missing_lastmod = [u.loc for u in urls if not u.lastmod]
        if missing_lastmod and len(missing_lastmod) > len(urls) * 0.1:
            issues.append(
                Issue(
                    issue_type="missing_lastmod",
                    severity="info",
                    urls=missing_lastmod[:5],
                    description=f"{len(missing_lastmod)} URLs missing lastmod attribute",
                    recommendation="Add lastmod to help search engines understand content freshness",
                )
            )

        return issues

    def _check_deep_url_patterns(self, urls: list[SitemapUrl]) -> list[Issue]:
        """Detect excessive deep URL patterns (configurable depth threshold)."""
        issues = []

        deep_urls = [
            u.loc
            for u in urls
            if u.loc.count("/") >= self.max_depth + 2  # scheme + domain + depth
            and not u.loc.endswith(".xml")
        ]

        if len(deep_urls) > self.combination_threshold:
            issues.append(
                Issue(
                    issue_type="excessive_deep_urls",
                    severity="warning",
                    urls=deep_urls[:5],
                    description=f"{len(deep_urls)} deep URL patterns detected (depth >= {self.max_depth}) - potential thin content risk",
                    recommendation="Verify each deep URL has substantial content. Remove pages without content from the sitemap.",
                )
            )

        return issues

    def generate_recommendations(self, issues: list[Issue]) -> list[str]:
        """Generate actionable recommendations based on issues found."""
        recommendations = []

        issue_types = {i.issue_type for i in issues}

        if "duplicate_url" in issue_types:
            recommendations.append("Audit sitemap generation logic to eliminate duplicates")
            recommendations.append("Add canonical tags to resolve URL conflicts")

        if "identical_timestamp" in issue_types:
            recommendations.append("Implement real modification date tracking for each page")

        if "excessive_deep_urls" in issue_types:
            recommendations.append("Remove deep URL pages without content from the sitemap")
            recommendations.append("Consider pagination or noindex for low-traffic deep pages")

        if not issues:
            recommendations.append("No major issues detected in the sitemap")

        return recommendations
