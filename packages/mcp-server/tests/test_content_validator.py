"""Tests for content validator service."""

from app.services.content_validator import ContentValidatorService
from app.services.crawler_service import CrawledPage


class TestContentValidator:
    """Test content validation."""

    def test_detect_thin_content(self):
        """Test detection of thin content."""
        page = CrawledPage(
            url="https://www.iautos.fr/thin",
            status_code=200,
            title="Thin Page",
            word_count=30,
        )

        validator = ContentValidatorService(thin_content_threshold=50)
        issues = validator.validate(page, check_thin_content=True)

        empty_issue = next((i for i in issues if i.issue_type == "empty_page"), None)
        assert empty_issue is not None
        assert empty_issue.severity == "critical"

    def test_detect_empty_listing(self):
        """Test detection of empty listings."""
        page = CrawledPage(
            url="https://www.iautos.fr/products?category=test",
            status_code=200,
            title="Test Listing",
            word_count=100,
            item_count=0,
        )

        validator = ContentValidatorService()
        issues = validator.validate(page, check_empty_listings=True)

        listing_issue = next((i for i in issues if i.issue_type == "empty_listing"), None)
        assert listing_issue is not None
        assert listing_issue.severity == "critical"

    def test_detect_empty_listing_with_url_patterns(self):
        """Test empty listing detection with URL pattern filter."""
        page = CrawledPage(
            url="https://www.iautos.fr/products?category=test",
            status_code=200,
            title="Test Listing",
            word_count=100,
            item_count=0,
        )

        # Should NOT detect because URL doesn't match pattern
        validator = ContentValidatorService(listing_url_patterns=["/shop"])
        issues = validator.validate(page, check_empty_listings=True)
        listing_issue = next((i for i in issues if i.issue_type == "empty_listing"), None)
        assert listing_issue is None

        # Should detect because URL matches pattern
        validator = ContentValidatorService(listing_url_patterns=["/products"])
        issues = validator.validate(page, check_empty_listings=True)
        listing_issue = next((i for i in issues if i.issue_type == "empty_listing"), None)
        assert listing_issue is not None

    def test_detect_missing_meta(self):
        """Test detection of missing meta description."""
        page = CrawledPage(
            url="https://www.iautos.fr/page",
            status_code=200,
            title="Page Title",
            word_count=200,
            meta_description=None,
        )

        validator = ContentValidatorService()
        issues = validator.validate(page)

        meta_issue = next((i for i in issues if i.issue_type == "missing_meta_description"), None)
        assert meta_issue is not None

    def test_detect_duplicate_titles(self):
        """Test detection of duplicate titles."""
        pages = [
            CrawledPage(url="https://www.iautos.fr/page1", status_code=200, title="Same Title"),
            CrawledPage(url="https://www.iautos.fr/page2", status_code=200, title="Same Title"),
            CrawledPage(
                url="https://www.iautos.fr/page3", status_code=200, title="Different Title"
            ),
        ]

        validator = ContentValidatorService()
        issues = validator.find_duplicate_titles(pages)

        assert len(issues) == 1
        assert issues[0].issue_type == "duplicate_title"
        assert len(issues[0].urls) == 2

    def test_valid_page_no_issues(self):
        """Test that valid page has minimal issues."""
        page = CrawledPage(
            url="https://www.iautos.fr/good-page",
            status_code=200,
            title="Good Page Title",
            meta_description="A good meta description for this page",
            h1="Main Heading",
            word_count=500,
            item_count=10,
        )

        validator = ContentValidatorService()
        issues = validator.validate(page)

        critical = [i for i in issues if i.severity == "critical"]
        assert len(critical) == 0

    def test_http_error_page(self):
        """Test that HTTP errors are detected."""
        page = CrawledPage(
            url="https://www.iautos.fr/error",
            status_code=404,
        )

        validator = ContentValidatorService()
        issues = validator.validate(page)

        assert len(issues) == 1
        assert issues[0].issue_type == "http_error"
        assert issues[0].severity == "critical"

    def test_english_issue_messages(self):
        """Test that issue messages are in English."""
        page = CrawledPage(
            url="https://www.iautos.fr/thin",
            status_code=200,
            title=None,
            word_count=30,
        )

        validator = ContentValidatorService(thin_content_threshold=50)
        issues = validator.validate(page)

        for issue in issues:
            # No French text
            assert "manquante" not in issue.description
            assert "vide" not in issue.description
