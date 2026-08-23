"""Tests for technical SEO checker service."""

from app.services.crawler_service import CrawledPage
from app.services.sitemap_parser import SitemapUrl
from app.services.technical_seo_checker import TechnicalSEOCheckerService


class TestTechnicalSEOChecker:
    """Test technical SEO checks."""

    def test_missing_canonical(self):
        """Test detection of missing canonical tags."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                canonical_url=None,
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_canonicals(pages)

        assert len(issues) == 1
        assert issues[0]["issue"] == "missing_canonical"

    def test_non_self_canonical(self):
        """Test detection of non-self-referencing canonical."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                canonical_url="https://www.iautos.fr/page2",
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_canonicals(pages)

        assert len(issues) == 1
        assert issues[0]["issue"] == "non_self_canonical"

    def test_self_canonical_ok(self):
        """Test that self-referencing canonical passes."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                canonical_url="https://www.iautos.fr/page1",
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_canonicals(pages)

        assert len(issues) == 0

    def test_noindex_in_sitemap(self):
        """Test detection of noindex pages in sitemap."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                meta_robots="noindex, follow",
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.check_meta_robots(
            pages,
            sitemap_urls=["https://www.iautos.fr/page1"],
        )

        assert len(issues) == 1
        assert issues[0]["issue"] == "noindex_in_sitemap"

    def test_robots_none_in_sitemap(self):
        """Test detection of robots=none pages in sitemap."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                meta_robots="none",
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.check_meta_robots(
            pages,
            sitemap_urls=["https://www.iautos.fr/page1"],
        )

        assert len(issues) == 1
        assert issues[0]["issue"] == "noindex_in_sitemap"

    def test_contradictory_directives(self):
        """Test detection of contradictory meta robots directives."""
        pages = [
            CrawledPage(
                url="https://www.iautos.fr/page1",
                status_code=200,
                meta_robots="index, noindex",
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.check_meta_robots(pages)

        contradictory = [i for i in issues if i["issue"] == "contradictory_directives"]
        assert len(contradictory) == 1

    def test_hreflang_validation(self):
        """Test hreflang reciprocal reference validation."""
        urls = [
            SitemapUrl(
                loc="https://www.iautos.fr/en/page",
                alternates={
                    "fr": "https://www.iautos.fr/fr/page",
                    "en": "https://www.iautos.fr/en/page",
                    "x-default": "https://www.iautos.fr/en/page",
                },
            ),
            SitemapUrl(
                loc="https://www.iautos.fr/fr/page",
                alternates={
                    "en": "https://www.iautos.fr/en/page",
                    "fr": "https://www.iautos.fr/fr/page",
                    "x-default": "https://www.iautos.fr/en/page",
                },
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_hreflang(urls)

        # Should pass - reciprocal references are correct
        assert len(issues) == 0

    def test_hreflang_missing_x_default(self):
        """A complete reciprocal cluster without x-default is still flagged."""
        urls = [
            SitemapUrl(
                loc="https://www.iautos.fr/en/page",
                alternates={
                    "fr": "https://www.iautos.fr/fr/page",
                    "en": "https://www.iautos.fr/en/page",
                },
            ),
            SitemapUrl(
                loc="https://www.iautos.fr/fr/page",
                alternates={
                    "en": "https://www.iautos.fr/en/page",
                    "fr": "https://www.iautos.fr/fr/page",
                },
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_hreflang(urls)

        assert {i["issue"] for i in issues} == {"missing_x_default_hreflang"}
        assert len(issues) == 2

    def test_hreflang_missing_reciprocal(self):
        """Test detection of missing reciprocal hreflang."""
        urls = [
            SitemapUrl(
                loc="https://www.iautos.fr/en/page",
                alternates={
                    "fr": "https://www.iautos.fr/fr/page",
                    "en": "https://www.iautos.fr/en/page",
                    "x-default": "https://www.iautos.fr/en/page",
                },
            ),
            SitemapUrl(
                loc="https://www.iautos.fr/fr/page",
                alternates={},  # No reciprocal reference
            ),
        ]

        checker = TechnicalSEOCheckerService()
        issues = checker.validate_hreflang(urls)

        # The EN page references FR, but FR doesn't reference back
        reciprocal_issues = [i for i in issues if i["issue"] == "missing_reciprocal_hreflang"]
        assert len(reciprocal_issues) >= 1

    def test_robots_txt_parsing(self):
        """Test robots.txt content parsing."""
        from app.services.technical_seo_checker import RobotsTxtResult

        checker = TechnicalSEOCheckerService()
        result = RobotsTxtResult(url="https://www.iautos.fr/robots.txt")

        content = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/
Sitemap: https://www.iautos.fr/sitemap.xml
Crawl-delay: 2
"""
        checker._parse_robots_content(result, content)

        assert len(result.disallow_patterns) == 2
        assert "/admin/" in result.disallow_patterns
        assert len(result.allow_patterns) == 1
        assert len(result.sitemaps) == 1
        assert result.crawl_delay == 2.0
