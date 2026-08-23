"""Tests for sitemap analyzer service."""

from datetime import datetime

from app.services.sitemap_analyzer import SitemapAnalyzerService
from app.services.sitemap_parser import SitemapData, SitemapUrl


class TestSitemapAnalyzer:
    """Test sitemap analysis."""

    def test_detect_duplicate_urls(self):
        """Test detection of duplicate URLs."""
        sitemap_data = SitemapData(
            urls=[
                SitemapUrl(loc="https://www.iautos.fr/page1"),
                SitemapUrl(loc="https://www.iautos.fr/page1"),
                SitemapUrl(loc="https://www.iautos.fr/page2"),
            ]
        )

        analyzer = SitemapAnalyzerService()
        issues = analyzer._check_duplicate_urls(sitemap_data.urls)

        assert len(issues) == 1
        assert issues[0].issue_type == "duplicate_url"
        assert issues[0].severity == "critical"

    def test_detect_identical_timestamps(self):
        """Test detection of identical timestamps."""
        same_time = datetime(2024, 1, 15, 12, 0, 0)

        sitemap_data = SitemapData(
            urls=[
                SitemapUrl(loc=f"https://www.iautos.fr/page{i}", lastmod=same_time)
                for i in range(20)
            ]
        )

        analyzer = SitemapAnalyzerService()
        issues = analyzer._check_identical_timestamps(sitemap_data.urls)

        assert len(issues) >= 1
        timestamp_issue = next((i for i in issues if i.issue_type == "identical_timestamp"), None)
        assert timestamp_issue is not None
        assert timestamp_issue.severity == "warning"

    def test_detect_query_param_cannibalization_generic(self):
        """Test generic detection of query params vs clean routes."""
        sitemap_data = SitemapData(
            urls=[
                SitemapUrl(loc="https://www.iautos.fr/products?brand=nike&city=paris"),
                SitemapUrl(loc="https://www.iautos.fr/paris/nike"),
            ]
        )

        analyzer = SitemapAnalyzerService()
        issues = analyzer._check_query_param_vs_routes(sitemap_data.urls)

        assert len(issues) >= 1
        assert issues[0].issue_type == "duplicate_url"

    def test_no_issues_for_clean_sitemap(self):
        """Test that clean sitemap has no issues."""
        sitemap_data = SitemapData(
            urls=[
                SitemapUrl(
                    loc=f"https://www.iautos.fr/page{i}",
                    lastmod=datetime(2024, 1, i + 1),
                )
                for i in range(5)
            ]
        )

        analyzer = SitemapAnalyzerService()
        issues = analyzer.analyze(sitemap_data)

        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0

    def test_deep_url_detection_configurable(self):
        """Test that deep URL detection is configurable."""
        urls = [SitemapUrl(loc=f"https://www.iautos.fr/a/b/c/d/e/f{i}") for i in range(1100)]
        sitemap_data = SitemapData(urls=urls)

        # Default threshold (1000)
        analyzer = SitemapAnalyzerService()
        issues = analyzer._check_deep_url_patterns(sitemap_data.urls)
        assert len(issues) == 1
        assert issues[0].issue_type == "excessive_deep_urls"

        # Higher threshold
        analyzer = SitemapAnalyzerService(combination_threshold=2000)
        issues = analyzer._check_deep_url_patterns(sitemap_data.urls)
        assert len(issues) == 0

    def test_english_messages(self):
        """Test that messages are in English."""
        sitemap_data = SitemapData(
            urls=[
                SitemapUrl(loc="https://www.iautos.fr/page1"),
                SitemapUrl(loc="https://www.iautos.fr/page1"),
            ]
        )

        analyzer = SitemapAnalyzerService()
        issues = analyzer.analyze(sitemap_data)
        recommendations = analyzer.generate_recommendations(issues)

        for rec in recommendations:
            assert (
                "sitemap" in rec.lower() or "canonical" in rec.lower() or "duplicate" in rec.lower()
            )
