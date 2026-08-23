"""Tests for internal links analyzer service."""

from app.services.crawler_service import CrawledPage
from app.services.internal_links_analyzer import InternalLinksAnalyzerService


class TestInternalLinksAnalyzer:
    """Test internal link analysis."""

    def _make_page(self, url, links=None, status=200):
        return CrawledPage(
            url=url,
            status_code=status,
            title=f"Page {url}",
            internal_links=links or [],
        )

    def test_basic_analysis(self):
        """Test basic link graph analysis."""
        pages = [
            self._make_page(
                "https://www.iautos.fr/a", ["https://www.iautos.fr/b", "https://www.iautos.fr/c"]
            ),
            self._make_page("https://www.iautos.fr/b", ["https://www.iautos.fr/a"]),
            self._make_page(
                "https://www.iautos.fr/c", ["https://www.iautos.fr/a", "https://www.iautos.fr/b"]
            ),
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages)

        assert result["total_pages"] == 3
        assert result["total_internal_links"] > 0
        assert result["avg_links_per_page"] > 0

    def test_orphan_page_detection(self):
        """Test detection of orphan pages (in sitemap but no inbound links)."""
        pages = [
            self._make_page("https://www.iautos.fr/a", ["https://www.iautos.fr/b"]),
            self._make_page("https://www.iautos.fr/b", ["https://www.iautos.fr/a"]),
            self._make_page("https://www.iautos.fr/orphan", []),  # No links to this page
        ]

        sitemap_urls = [
            "https://www.iautos.fr/a",
            "https://www.iautos.fr/b",
            "https://www.iautos.fr/orphan",
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages, sitemap_urls=sitemap_urls)

        assert result["orphan_count"] >= 1
        assert "https://www.iautos.fr/orphan" in result["orphan_pages"]

    def test_broken_internal_links(self):
        """Test detection of broken internal links."""
        pages = [
            self._make_page("https://www.iautos.fr/a", ["https://www.iautos.fr/broken"]),
            self._make_page("https://www.iautos.fr/broken", [], status=404),
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages)

        assert result["broken_count"] >= 1

    def test_crawl_failure_is_not_broken_link(self):
        """A crawler timeout/status=0 is not proof of a broken HTTP target."""
        pages = [
            self._make_page("https://www.iautos.fr/a", ["https://www.iautos.fr/slow"]),
            self._make_page("https://www.iautos.fr/slow", [], status=0),
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages)

        assert result["broken_count"] == 0
        assert result["crawl_failed_internal_target_count"] == 1

    def test_pagerank_computation(self):
        """Test PageRank computation."""
        pages = [
            self._make_page(
                "https://www.iautos.fr/hub",
                [
                    "https://www.iautos.fr/a",
                    "https://www.iautos.fr/b",
                    "https://www.iautos.fr/c",
                ],
            ),
            self._make_page("https://www.iautos.fr/a", ["https://www.iautos.fr/hub"]),
            self._make_page("https://www.iautos.fr/b", ["https://www.iautos.fr/hub"]),
            self._make_page("https://www.iautos.fr/c", ["https://www.iautos.fr/hub"]),
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages)

        assert len(result["top_pages_by_pagerank"]) > 0
        # Hub page should have high PageRank (most inbound links)
        top_url = result["top_pages_by_pagerank"][0]["url"]
        assert top_url == "https://www.iautos.fr/hub"

    def test_empty_pages(self):
        """Test analysis with no pages."""
        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze([])

        assert result["total_pages"] == 0
        assert result["total_internal_links"] == 0

    def test_url_normalization(self):
        """Test that URLs are normalized (trailing slash, fragment)."""
        analyzer = InternalLinksAnalyzerService()

        assert (
            analyzer._normalize_url("https://www.iautos.fr/page/") == "https://www.iautos.fr/page"
        )
        assert (
            analyzer._normalize_url("https://www.iautos.fr/page#section")
            == "https://www.iautos.fr/page"
        )
        assert (
            analyzer._normalize_url("https://www.iautos.fr/page?q=1")
            == "https://www.iautos.fr/page?q=1"
        )

    def test_orphan_detection_normalizes_crawled_urls(self):
        """Trailing-slash differences must not create false orphan pages."""
        pages = [
            self._make_page("https://www.iautos.fr/a/", ["https://www.iautos.fr/b/"]),
            self._make_page("https://www.iautos.fr/b/", ["https://www.iautos.fr/a/"]),
        ]
        sitemap_urls = ["https://www.iautos.fr/a", "https://www.iautos.fr/b"]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages, sitemap_urls=sitemap_urls)

        assert result["orphan_count"] == 0

    def test_broken_internal_links_normalize_target_statuses(self):
        """Broken links are detected even if crawled target URL has a slash."""
        pages = [
            self._make_page("https://www.iautos.fr/a", ["https://www.iautos.fr/broken"]),
            self._make_page("https://www.iautos.fr/broken/", [], status=404),
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages)

        assert result["broken_count"] == 1
        assert result["broken_internal_links"][0]["target"] == "https://www.iautos.fr/broken"

    def test_orphan_detection_skipped_for_partial_crawl(self):
        """A partial crawl cannot prove sitemap orphan pages."""
        pages = [
            self._make_page("https://www.iautos.fr/a", []),
        ]
        sitemap_urls = [
            "https://www.iautos.fr/a",
            "https://www.iautos.fr/b",
        ]

        analyzer = InternalLinksAnalyzerService()
        result = analyzer.analyze(pages, sitemap_urls=sitemap_urls)

        assert result["orphan_count"] == 0
        assert result["orphan_detection_skipped"] is True
