"""Cross-tool correlator for detecting compound SEO issues.

Builds a URL x signals matrix from aggregated tool results and
identifies pages with multiple simultaneous problems.
"""

import logging
from typing import Any

from app.core.scoring import (
    COMPOUND_CRITICAL_WEIGHT,
    COMPOUND_THRESHOLD,
    LOW_CWV_THRESHOLD,
    LOW_EEAT_THRESHOLD,
    LOW_GEO_THRESHOLD,
    SIGNAL_WEIGHTS,
    THIN_CONTENT_WORD_THRESHOLD,
)

logger = logging.getLogger(__name__)


class CrossToolCorrelator:
    """Correlate signals across multiple SEO tools."""

    def correlate(self, aggregated_data: dict) -> dict[str, Any]:
        """Build URL x signals matrix and detect compound issues.

        Args:
            aggregated_data: Dict with keys matching tool output names
                (sitemap, content, structured_data, internal_links,
                 technical, cwv, geo, eeat, cannibalization)

        Returns:
            Dict with url_matrix, compound_issues, quick_wins, severity_summary
        """
        url_signals: dict[str, dict[str, Any]] = {}

        # Extract signals from each tool
        self._extract_content_signals(aggregated_data.get("content", {}), url_signals)
        self._extract_schema_signals(aggregated_data.get("structured_data", {}), url_signals)
        self._extract_link_signals(aggregated_data.get("internal_links", {}), url_signals)
        self._extract_technical_signals(aggregated_data.get("technical", {}), url_signals)
        self._extract_cwv_signals(aggregated_data.get("cwv", {}), url_signals)
        self._extract_geo_signals(aggregated_data.get("geo", {}), url_signals)
        self._extract_eeat_signals(aggregated_data.get("eeat", {}), url_signals)
        self._extract_cannibalization_signals(
            aggregated_data.get("cannibalization", {}), url_signals
        )
        self._extract_readability_signals(aggregated_data.get("content", {}), url_signals)

        # Detect compound issues
        compound_issues = self._detect_compound_issues(url_signals)

        # Identify quick wins
        quick_wins = self._identify_quick_wins(url_signals, aggregated_data)

        # Severity summary
        severity_summary = self._build_severity_summary(url_signals)

        return {
            "urls_tracked": len(url_signals),
            "url_matrix": self._format_matrix(url_signals),
            "compound_issues": compound_issues,
            "compound_issues_count": len(compound_issues),
            "quick_wins": quick_wins,
            "severity_summary": severity_summary,
        }

    def _add_signal(
        self,
        url_signals: dict[str, dict],
        url: str,
        signal: str,
        detail: str = "",
    ) -> None:
        """Add a signal to the URL matrix."""
        if url not in url_signals:
            url_signals[url] = {"signals": {}, "total_weight": 0}
        url_signals[url]["signals"][signal] = detail or signal
        url_signals[url]["total_weight"] += SIGNAL_WEIGHTS.get(signal, 1)

    def _extract_content_signals(self, content: dict, url_signals: dict) -> None:
        """Extract signals from content audit results."""
        for page in content.get("pages", []):
            url = page.get("url", "")
            if not url:
                continue

            word_count = page.get("word_count", 0)
            if word_count < THIN_CONTENT_WORD_THRESHOLD:
                self._add_signal(url_signals, url, "thin_content", f"Only {word_count} words")

            issues = page.get("issues", [])
            for issue in issues:
                if isinstance(issue, str):
                    if "meta description" in issue.lower():
                        self._add_signal(url_signals, url, "missing_meta")
                    if "h1" in issue.lower():
                        self._add_signal(url_signals, url, "missing_h1")

    def _extract_schema_signals(self, structured_data: dict, url_signals: dict) -> None:
        """Extract signals from structured data validation."""
        for result in structured_data.get("results", []):
            url = result.get("url", "")
            if not url:
                continue

            valid = result.get("valid_schemas", 0)
            if valid == 0 and not result.get("error"):
                self._add_signal(url_signals, url, "missing_schema")

    def _extract_link_signals(self, links: dict, url_signals: dict) -> None:
        """Extract signals from internal links analysis."""
        for url in links.get("orphan_pages", []):
            self._add_signal(url_signals, url, "orphan_page")

        for broken in links.get("broken_internal_links", []):
            if isinstance(broken, dict):
                target = broken.get("target", broken.get("url", ""))
                source = broken.get("source", "")
                if target:
                    self._add_signal(
                        url_signals, target, "broken_link_target", f"Broken from {source}"
                    )

    def _extract_technical_signals(self, technical: dict, url_signals: dict) -> None:
        """Extract signals from technical SEO check."""
        for issue in technical.get("canonical_issues", []):
            url = issue.get("url", "")
            if url:
                self._add_signal(url_signals, url, "canonical_issue", issue.get("issue", ""))

        for issue in technical.get("meta_robots_issues", []):
            url = issue.get("url", "")
            if url:
                self._add_signal(url_signals, url, "noindex_in_sitemap", issue.get("issue", ""))

    def _extract_cwv_signals(self, cwv: dict, url_signals: dict) -> None:
        """Extract signals from Core Web Vitals."""
        if not cwv:
            return
        for result in cwv.get("results", []):
            if not isinstance(result, dict):
                continue
            url = result.get("url", "")
            perf = result.get("performance_score", 100)
            if url and perf < LOW_CWV_THRESHOLD:
                self._add_signal(url_signals, url, "low_cwv", f"Performance score: {perf}")

    def _extract_geo_signals(self, geo: dict, url_signals: dict) -> None:
        """Extract signals from GEO readiness."""
        if not geo:
            return
        for page in geo.get("page_results", []):
            if not isinstance(page, dict):
                continue
            url = page.get("url", "")
            score = page.get("geo_score", 100)
            if url and score < LOW_GEO_THRESHOLD:
                self._add_signal(url_signals, url, "low_geo", f"GEO score: {score}")

    def _extract_eeat_signals(self, eeat: dict, url_signals: dict) -> None:
        """Extract signals from E-E-A-T audit."""
        if not eeat:
            return
        for page in eeat.get("page_results", []):
            if not isinstance(page, dict):
                continue
            url = page.get("url", "")
            score = page.get("eeat_score", 100)
            if url and score < LOW_EEAT_THRESHOLD:
                self._add_signal(url_signals, url, "low_eeat", f"E-E-A-T score: {score}")

    def _extract_cannibalization_signals(self, cannibalization: dict, url_signals: dict) -> None:
        """Extract signals from cannibalization detection."""
        for group in cannibalization.get("groups", []):
            urls = group.get("urls", [])
            for url in urls:
                self._add_signal(
                    url_signals, url, "cannibalized", f"Competes with {len(urls) - 1} other pages"
                )

    def _extract_readability_signals(self, content: dict, url_signals: dict) -> None:
        """Extract readability signals from content audit results."""
        for page in content.get("pages", []):
            url = page.get("url", "")
            if not url:
                continue
            issues = page.get("issues", [])
            for issue in issues:
                if isinstance(issue, dict) and issue.get("issue_type") == "low_readability":
                    self._add_signal(url_signals, url, "low_readability", "Low readability score")
                elif isinstance(issue, str) and "readability" in issue.lower():
                    self._add_signal(url_signals, url, "low_readability", issue)

    def _detect_compound_issues(self, url_signals: dict[str, dict]) -> list[dict]:
        """Find URLs with 3+ simultaneous problems."""
        compound = []

        for url, data in url_signals.items():
            signal_count = len(data["signals"])
            if signal_count >= COMPOUND_THRESHOLD:
                compound.append(
                    {
                        "url": url,
                        "signal_count": signal_count,
                        "total_weight": data["total_weight"],
                        "signals": list(data["signals"].keys()),
                        "details": data["signals"],
                        "priority": "critical"
                        if data["total_weight"] >= COMPOUND_CRITICAL_WEIGHT
                        else "high",
                    }
                )

        # Sort by weight (severity) descending
        compound.sort(key=lambda x: x["total_weight"], reverse=True)
        return compound[:20]

    def _identify_quick_wins(
        self, url_signals: dict[str, dict], aggregated_data: dict
    ) -> list[dict]:
        """Identify high-impact, low-effort fixes."""
        quick_wins = []

        # Pages with only 1-2 easy-to-fix issues
        easy_fixes = {"missing_meta", "missing_h1", "missing_schema", "missing_alt"}
        for url, data in url_signals.items():
            signals = set(data["signals"].keys())
            easy = signals & easy_fixes
            if easy and len(signals) <= 2:
                for fix in easy:
                    quick_wins.append(
                        {
                            "url": url,
                            "action": f"Fix: {fix.replace('_', ' ')}",
                            "impact": "medium",
                            "effort": "low",
                        }
                    )

        # GSC-based quick wins: high impressions + fixable issues
        # (detected if content data has pages with high impressions but issues)

        # Sort: impact high first, then effort low first
        quick_wins.sort(
            key=lambda x: (
                0 if x.get("impact") == "high" else 1,
                0 if x.get("effort") == "low" else 1,
            )
        )
        return quick_wins[:10]

    def _format_matrix(self, url_signals: dict[str, dict]) -> list[dict]:
        """Format the URL matrix for output (top 20 by weight)."""
        sorted_urls = sorted(
            url_signals.items(),
            key=lambda x: x[1]["total_weight"],
            reverse=True,
        )
        return [
            {
                "url": url,
                "signal_count": len(data["signals"]),
                "total_weight": data["total_weight"],
                "signals": list(data["signals"].keys()),
            }
            for url, data in sorted_urls[:20]
        ]

    def _build_severity_summary(self, url_signals: dict[str, dict]) -> dict:
        """Build signal frequency summary."""
        signal_counts: dict[str, int] = {}
        for data in url_signals.values():
            for signal in data["signals"]:
                signal_counts[signal] = signal_counts.get(signal, 0) + 1

        return {
            "total_urls_with_issues": len(url_signals),
            "signal_frequency": dict(
                sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "most_common_issue": (
                max(signal_counts, key=lambda k: signal_counts[k]) if signal_counts else None
            ),
        }
