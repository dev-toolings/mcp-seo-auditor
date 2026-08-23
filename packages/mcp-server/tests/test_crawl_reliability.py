"""Crawl reliability: nested sitemap indexes, hreflang from HTML, raw-vs-rendered diff.

No real network and no real browser: HTTP is served by a fake httpx client and the
browser crawler is always mocked (ghostchrome is absent from CI).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.crawler_service import CrawledPage, CrawlerService
from app.services.sitemap_parser import SitemapParserService
from app.services.technical_seo_checker import TechnicalSEOCheckerService

# ---------------------------------------------------------------------------
# Fake HTTP layer
# ---------------------------------------------------------------------------


def _index_xml(*child_urls: str) -> bytes:
    entries = "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in child_urls)
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries.encode()
        + b"</sitemapindex>"
    )


def _urlset_xml(*page_urls: str) -> bytes:
    entries = "".join(f"<url><loc>{u}</loc></url>" for u in page_urls)
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + entries.encode()
        + b"</urlset>"
    )


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Minimal httpx.AsyncClient stand-in serving a dict of url -> xml bytes."""

    def __init__(self, routes: dict[str, bytes]):
        self.routes = routes
        self.requested: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def get(self, url, **_kwargs):
        self.requested.append(url)
        if url not in self.routes:
            return _FakeResponse(b"", status_code=404)
        return _FakeResponse(self.routes[url])


def _parser_with(routes: dict[str, bytes]) -> tuple[SitemapParserService, _FakeClient]:
    client = _FakeClient(routes)
    parser = SitemapParserService()
    return parser, client


# ---------------------------------------------------------------------------
# Nested sitemap indexes
# ---------------------------------------------------------------------------


class TestNestedSitemapIndex:
    """A child sitemap that is itself an index must be followed, not dropped."""

    async def test_two_level_index_returns_all_urls(self):
        """index -> index -> urlset: every URL is collected."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml("https://ex.com/child-index.xml"),
            "https://ex.com/child-index.xml": _index_xml(
                "https://ex.com/pages-a.xml", "https://ex.com/pages-b.xml"
            ),
            "https://ex.com/pages-a.xml": _urlset_xml("https://ex.com/a1", "https://ex.com/a2"),
            "https://ex.com/pages-b.xml": _urlset_xml("https://ex.com/b1"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/sitemap.xml")

        assert sorted(u.loc for u in data.urls) == [
            "https://ex.com/a1",
            "https://ex.com/a2",
            "https://ex.com/b1",
        ]
        assert data.warnings == []
        assert data.is_index is False

    async def test_depth_limit_emits_explicit_warning(self):
        """4 nested index levels: the truncation is reported, never silent."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml("https://ex.com/lvl2.xml"),
            "https://ex.com/lvl2.xml": _index_xml("https://ex.com/lvl3.xml"),
            "https://ex.com/lvl3.xml": _index_xml("https://ex.com/lvl4.xml"),
            "https://ex.com/lvl4.xml": _index_xml("https://ex.com/pages.xml"),
            "https://ex.com/pages.xml": _urlset_xml("https://ex.com/deep"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/sitemap.xml")

        # The deepest urlset is out of reach, but the caller is told so.
        assert data.urls == []
        assert len(data.warnings) == 1
        assert "depth limit" in data.warnings[0]
        assert "https://ex.com/lvl4.xml" in data.warnings[0]
        assert "https://ex.com/pages.xml" not in client.requested

    async def test_depth_limit_is_configurable(self):
        """Raising max_depth reaches the URLs the default depth truncates."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml("https://ex.com/lvl2.xml"),
            "https://ex.com/lvl2.xml": _index_xml("https://ex.com/lvl3.xml"),
            "https://ex.com/lvl3.xml": _index_xml("https://ex.com/lvl4.xml"),
            "https://ex.com/lvl4.xml": _index_xml("https://ex.com/pages.xml"),
            "https://ex.com/pages.xml": _urlset_xml("https://ex.com/deep"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/sitemap.xml", max_depth=4)

        assert [u.loc for u in data.urls] == ["https://ex.com/deep"]
        assert data.warnings == []

    async def test_circular_sitemaps_do_not_loop(self):
        """A -> B -> A terminates and reports the circular reference."""
        routes = {
            "https://ex.com/a.xml": _index_xml("https://ex.com/b.xml"),
            "https://ex.com/b.xml": _index_xml("https://ex.com/a.xml", "https://ex.com/pages.xml"),
            "https://ex.com/pages.xml": _urlset_xml("https://ex.com/p1"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/a.xml")

        assert [u.loc for u in data.urls] == ["https://ex.com/p1"]
        assert any("Circular" in w for w in data.warnings)
        # a.xml fetched once as the root, never re-fetched from b.xml
        assert client.requested.count("https://ex.com/a.xml") == 1

    async def test_self_referencing_index_is_skipped(self):
        """An index listing itself does not recurse forever."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml(
                "https://ex.com/sitemap.xml", "https://ex.com/pages.xml"
            ),
            "https://ex.com/pages.xml": _urlset_xml("https://ex.com/p1"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/sitemap.xml")

        assert [u.loc for u in data.urls] == ["https://ex.com/p1"]
        assert any("Circular" in w for w in data.warnings)

    async def test_unreachable_child_is_reported(self):
        """A child sitemap that fails to fetch surfaces as a warning."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml(
                "https://ex.com/ok.xml", "https://ex.com/gone.xml"
            ),
            "https://ex.com/ok.xml": _urlset_xml("https://ex.com/p1"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            data = await parser.fetch_and_parse("https://ex.com/sitemap.xml")

        assert [u.loc for u in data.urls] == ["https://ex.com/p1"]
        assert any("gone.xml" in w for w in data.warnings)

    async def test_fetch_all_urls_resolves_nested_indexes(self):
        """fetch_all_urls goes through the same recursive resolution."""
        routes = {
            "https://ex.com/sitemap.xml": _index_xml("https://ex.com/child-index.xml"),
            "https://ex.com/child-index.xml": _index_xml("https://ex.com/pages.xml"),
            "https://ex.com/pages.xml": _urlset_xml("https://ex.com/p1", "https://ex.com/p2"),
        }
        parser, client = _parser_with(routes)

        with patch("httpx.AsyncClient", return_value=client):
            urls = await parser.fetch_all_urls("https://ex.com/sitemap.xml")

        assert [u.loc for u in urls] == ["https://ex.com/p1", "https://ex.com/p2"]


class TestSitemapWarningsSurfaceInAudit:
    """audit_sitemap must expose the incompleteness, not report a clean run."""

    async def test_audit_sitemap_exposes_warnings(self):
        from types import SimpleNamespace

        from app.services.ai.audit_orchestrator import AuditOrchestrator
        from app.services.sitemap_parser import SitemapData, SitemapUrl

        sitemap_data = SitemapData(
            urls=[SitemapUrl(loc="https://ex.com/p1")],
            warnings=["Sitemap nesting depth limit (3) reached at https://ex.com/lvl4.xml"],
        )
        ctx = SimpleNamespace(
            sitemap_parser=SimpleNamespace(fetch_and_parse=AsyncMock(return_value=sitemap_data)),
            sitemap_analyzer=SimpleNamespace(
                analyze=lambda _d: [], generate_recommendations=lambda _i: []
            ),
        )

        result = await AuditOrchestrator(ctx).audit_sitemap("https://ex.com/sitemap.xml")

        assert result["complete"] is False
        assert result["warnings"] == sitemap_data.warnings


# ---------------------------------------------------------------------------
# hreflang from crawled HTML
# ---------------------------------------------------------------------------


def _page(url: str, hreflang: dict[str, str]) -> CrawledPage:
    return CrawledPage(url=url, status_code=200, hreflang=hreflang)


class TestHreflangFromHtml:
    """validate_hreflang reads the crawled HTML, not just the sitemap."""

    def test_crawler_extracts_hreflang_links(self):
        html = """
        <html><head>
          <link rel="alternate" hreflang="fr" href="/fr/page">
          <link rel="alternate" hreflang="en-GB" href="https://ex.com/en-gb/page">
          <link rel="alternate" hreflang="x-default" href="https://ex.com/page">
          <link rel="stylesheet" href="/style.css">
        </head><body><h1>Hi</h1></body></html>
        """
        page = CrawledPage(url="https://ex.com/page", status_code=200)
        CrawlerService()._parse_html(page, html)

        assert page.hreflang == {
            "fr": "https://ex.com/fr/page",
            "en-GB": "https://ex.com/en-gb/page",
            "x-default": "https://ex.com/page",
        }

    def test_non_reciprocal_hreflang_detected_from_html(self):
        """EN points to FR, FR only points to itself."""
        pages = [
            _page(
                "https://ex.com/en/page",
                {
                    "en": "https://ex.com/en/page",
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/en/page",
                },
            ),
            _page(
                "https://ex.com/fr/page",
                {
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/fr/page",
                },
            ),
        ]

        issues = TechnicalSEOCheckerService().validate_hreflang(pages=pages)

        reciprocal = [i for i in issues if i["issue"] == "missing_reciprocal_hreflang"]
        assert len(reciprocal) == 1
        assert reciprocal[0]["url"] == "https://ex.com/en/page"
        assert reciprocal[0]["alternate_url"] == "https://ex.com/fr/page"
        assert reciprocal[0]["source"] == "html"

    def test_reciprocal_hreflang_from_html_is_clean(self):
        pages = [
            _page(
                "https://ex.com/en/page",
                {
                    "en": "https://ex.com/en/page",
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/en/page",
                },
            ),
            _page(
                "https://ex.com/fr/page",
                {
                    "en": "https://ex.com/en/page",
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/en/page",
                },
            ),
        ]

        assert TechnicalSEOCheckerService().validate_hreflang(pages=pages) == []

    def test_missing_x_default_detected(self):
        pages = [
            _page(
                "https://ex.com/en/page",
                {"en": "https://ex.com/en/page", "fr": "https://ex.com/fr/page"},
            ),
            _page(
                "https://ex.com/fr/page",
                {"en": "https://ex.com/en/page", "fr": "https://ex.com/fr/page"},
            ),
        ]

        issues = TechnicalSEOCheckerService().validate_hreflang(pages=pages)

        x_default = [i for i in issues if i["issue"] == "missing_x_default_hreflang"]
        assert {i["url"] for i in x_default} == {
            "https://ex.com/en/page",
            "https://ex.com/fr/page",
        }
        assert not [i for i in issues if i["issue"] == "missing_reciprocal_hreflang"]

    def test_invalid_language_code_detected(self):
        pages = [
            _page(
                "https://ex.com/page",
                {
                    "en_US": "https://ex.com/page",
                    "french": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/page",
                },
            )
        ]

        issues = TechnicalSEOCheckerService().validate_hreflang(pages=pages)

        invalid = {i["language"] for i in issues if i["issue"] == "invalid_hreflang_code"}
        assert invalid == {"en_US", "french"}

    def test_html_and_sitemap_sources_are_merged(self):
        """A page annotated in HTML and a sitemap entry describe the same cluster."""
        from app.services.sitemap_parser import SitemapUrl

        pages = [
            _page(
                "https://ex.com/en/page",
                {
                    "en": "https://ex.com/en/page",
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/en/page",
                },
            )
        ]
        sitemap_urls = [
            SitemapUrl(
                loc="https://ex.com/fr/page",
                alternates={
                    "en": "https://ex.com/en/page",
                    "fr": "https://ex.com/fr/page",
                    "x-default": "https://ex.com/en/page",
                },
            )
        ]

        issues = TechnicalSEOCheckerService().validate_hreflang(
            sitemap_urls=sitemap_urls, pages=pages
        )

        assert issues == []

    def test_missing_self_reference_detected(self):
        pages = [
            _page(
                "https://ex.com/en/page",
                {"fr": "https://ex.com/fr/page", "x-default": "https://ex.com/fr/page"},
            )
        ]

        issues = TechnicalSEOCheckerService().validate_hreflang(pages=pages)

        assert any(i["issue"] == "missing_self_hreflang" for i in issues)

    def test_no_annotations_no_issues(self):
        pages = [CrawledPage(url="https://ex.com/page", status_code=200)]

        assert TechnicalSEOCheckerService().validate_hreflang(pages=pages) == []


# ---------------------------------------------------------------------------
# Raw vs rendered diff
# ---------------------------------------------------------------------------

RAW_HTML = (
    "<html><head><title>Raw title</title></head>"
    "<body><main><p>server text</p><a href='/kept'>kept</a></main></body></html>"
)

RENDERED_HTML = (
    "<html><head><title>Raw title</title>"
    '<meta name="description" content="hydrated">'
    '<script type="application/ld+json">{"@type": "Product"}</script></head>'
    "<body><main><p>server text</p><a href='/kept'>kept</a>"
    "<p>client only paragraph</p><a href='/js-only'>js</a></main></body></html>"
)


class TestRenderDiff:
    """The diff must degrade cleanly when ghostchrome is absent."""

    @pytest.fixture(autouse=True)
    def _no_dns(self, monkeypatch):
        """SSRF validation resolves hostnames — keep the tests fully offline."""
        monkeypatch.setattr("app.services.crawler_service.validate_url", lambda url: url)

    async def test_browser_unavailable_returns_status_unavailable(self):
        """No ghostchrome: explicit 'unavailable' status, no exception, no HTTP call."""
        crawler = CrawlerService()
        with patch.object(
            CrawlerService,
            "_get_browser_crawler",
            AsyncMock(side_effect=RuntimeError("ghostchrome is required but not found.")),
        ):
            with patch.object(
                CrawlerService, "fetch_raw_html", AsyncMock(side_effect=AssertionError("no HTTP"))
            ):
                result = await crawler.diff_raw_vs_rendered("https://ex.com/page")

        assert result["status"] == "unavailable"
        assert "ghostchrome" in result["reason"]
        assert result["url"] == "https://ex.com/page"

    async def test_browser_returns_nothing_is_unavailable(self):
        crawler = CrawlerService()
        crawler._browser_crawler = AsyncMock()
        crawler._browser_crawler.crawl_page = AsyncMock(return_value=("", 0, "https://ex.com/page"))

        result = await crawler.diff_raw_vs_rendered("https://ex.com/page")

        assert result["status"] == "unavailable"
        assert "status 0" in result["reason"]

    async def test_raw_fetch_failure_is_reported_not_raised(self):
        crawler = CrawlerService()
        crawler._browser_crawler = AsyncMock()
        crawler._browser_crawler.crawl_page = AsyncMock(
            return_value=(RENDERED_HTML, 200, "https://ex.com/page")
        )

        with patch.object(
            CrawlerService, "fetch_raw_html", AsyncMock(side_effect=RuntimeError("boom"))
        ):
            result = await crawler.diff_raw_vs_rendered("https://ex.com/page")

        assert result["status"] == "error"
        assert "boom" in result["reason"]

    async def test_js_only_content_is_reported(self):
        crawler = CrawlerService()
        crawler._browser_crawler = AsyncMock()
        crawler._browser_crawler.crawl_page = AsyncMock(
            return_value=(RENDERED_HTML, 200, "https://ex.com/page")
        )

        with patch.object(
            CrawlerService,
            "fetch_raw_html",
            AsyncMock(return_value=(RAW_HTML, 200, "https://ex.com/page")),
        ):
            result = await crawler.diff_raw_vs_rendered("https://ex.com/page")

        assert result["status"] == "ok"
        assert result["js_dependent"] is True
        assert result["links_only_in_rendered"] == ["https://ex.com/js-only"]
        assert result["structured_data_only_in_rendered"] == ["Product"]
        assert result["meta_description"]["only_in_rendered"] is True
        assert "client" in result["words_only_in_rendered_sample"]
        assert result["raw_word_count"] < result["rendered_word_count"]

    async def test_identical_html_is_not_js_dependent(self):
        crawler = CrawlerService()
        crawler._browser_crawler = AsyncMock()
        crawler._browser_crawler.crawl_page = AsyncMock(
            return_value=(RAW_HTML, 200, "https://ex.com/page")
        )

        with patch.object(
            CrawlerService,
            "fetch_raw_html",
            AsyncMock(return_value=(RAW_HTML, 200, "https://ex.com/page")),
        ):
            result = await crawler.diff_raw_vs_rendered("https://ex.com/page")

        assert result["status"] == "ok"
        assert result["js_dependent"] is False
        assert result["links_only_in_rendered"] == []
        assert result["words_only_in_rendered"] == 0

    async def test_already_rendered_html_skips_the_browser(self):
        """Passing the DOM from a previous crawl avoids a second render."""
        crawler = CrawlerService()
        with patch.object(
            CrawlerService,
            "_get_browser_crawler",
            AsyncMock(side_effect=AssertionError("browser must not be used")),
        ):
            with patch.object(
                CrawlerService,
                "fetch_raw_html",
                AsyncMock(return_value=(RAW_HTML, 200, "https://ex.com/page")),
            ):
                result = await crawler.diff_raw_vs_rendered(
                    "https://ex.com/page", rendered_html=RENDERED_HTML
                )

        assert result["status"] == "ok"
        assert result["js_dependent"] is True

    async def test_technical_check_reuses_crawled_dom(self):
        """The orchestrator feeds the crawl's rendered HTML into the diff."""
        from types import SimpleNamespace

        from app.services.ai.audit_orchestrator import AuditOrchestrator

        page = CrawledPage(url="https://ex.com/p1", status_code=200, raw_html=RENDERED_HTML)
        crawler = CrawlerService()
        ctx = SimpleNamespace(technical_seo_checker=TechnicalSEOCheckerService(), crawler=crawler)

        with patch.object(
            CrawlerService,
            "_get_browser_crawler",
            AsyncMock(side_effect=AssertionError("browser must not be used")),
        ):
            with patch.object(
                CrawlerService,
                "fetch_raw_html",
                AsyncMock(return_value=(RAW_HTML, 200, "https://ex.com/p1")),
            ):
                result = await AuditOrchestrator(ctx).technical_check(
                    ["https://ex.com/p1"], pages=[page]
                )

        assert result["render_diff"][0]["status"] == "ok"
        assert result["render_diff"][0]["js_dependent"] is True

    async def test_technical_check_degrades_without_browser(self):
        """The orchestrator reports the diff status instead of failing the check."""
        from types import SimpleNamespace

        from app.services.ai.audit_orchestrator import AuditOrchestrator

        pages = [CrawledPage(url="https://ex.com/p1", status_code=200)]
        checker = TechnicalSEOCheckerService()
        crawler = CrawlerService()
        ctx = SimpleNamespace(technical_seo_checker=checker, crawler=crawler)

        with patch.object(
            CrawlerService,
            "_get_browser_crawler",
            AsyncMock(side_effect=RuntimeError("ghostchrome is required but not found.")),
        ):
            result = await AuditOrchestrator(ctx).technical_check(
                ["https://ex.com/p1"], pages=pages
            )

        assert result["render_diff"][0]["status"] == "unavailable"
        assert result["hreflang_issues"] == []
        assert result["pages_analyzed"] == 1


@pytest.mark.parametrize(
    "code,valid",
    [
        ("en", True),
        ("fr-BE", True),
        ("zh-Hant-TW", True),
        ("es-419", True),
        ("x-default", True),
        ("en_US", False),
        ("english", False),
        ("", False),
    ],
)
def test_hreflang_code_validation(code, valid):
    from app.services.technical_seo_checker import _is_valid_hreflang

    assert _is_valid_hreflang(code) is valid
