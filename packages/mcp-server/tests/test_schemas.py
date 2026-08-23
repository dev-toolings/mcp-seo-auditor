"""Tests for Pydantic input schemas."""

import pytest
from pydantic import ValidationError

from seo_server.schemas.analyze import SeoAnalyzeInput
from seo_server.schemas.audit import SeoAuditInput
from seo_server.schemas.crawl import SeoCrawlInput
from seo_server.schemas.geo import SeoGeoInput
from seo_server.schemas.gsc_analytics import GscAnalyticsInput
from seo_server.schemas.gsc_manage import GscManageInput
from seo_server.schemas.monitor import SeoMonitorInput
from seo_server.schemas.serp import SeoSerpInput
from seo_server.schemas.site import SeoSiteInput
from seo_server.schemas.strategy import SeoStrategyInput


class TestSeoAuditInput:
    def test_valid_minimal(self):
        m = SeoAuditInput(sitemap_url="https://example.com/sitemap.xml")
        assert m.sitemap_url == "https://example.com/sitemap.xml"
        assert m.max_pages == 500
        assert m.include_cwv is False
        assert m.language == "en"

    def test_ssrf_rejected(self):
        with pytest.raises((ValidationError, Exception)):
            SeoAuditInput(sitemap_url="http://127.0.0.1/sitemap.xml")

    def test_max_pages_bounds(self):
        with pytest.raises(ValidationError):
            SeoAuditInput(sitemap_url="https://example.com/sitemap.xml", max_pages=0)
        with pytest.raises(ValidationError):
            SeoAuditInput(sitemap_url="https://example.com/sitemap.xml", max_pages=501)


class TestSeoAnalyzeInput:
    def test_valid(self):
        m = SeoAnalyzeInput(action="content", urls=["https://example.com/page"])
        assert m.action == "content"
        assert m.depth == "quick"
        assert m.strategy == "mobile"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            SeoAnalyzeInput(action="invalid", urls=["https://example.com"])

    def test_ssrf_in_url_list(self):
        with pytest.raises((ValidationError, Exception)):
            SeoAnalyzeInput(action="content", urls=["http://169.254.169.254/latest/meta-data"])


class TestSeoCrawlInput:
    def test_valid(self):
        m = SeoCrawlInput(action="list")
        assert m.action == "list"
        assert m.limit == 20
        assert m.days == 90

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            SeoCrawlInput(action="invalid")

    def test_days_bounds(self):
        with pytest.raises(ValidationError):
            SeoCrawlInput(action="list", days=0)
        with pytest.raises(ValidationError):
            SeoCrawlInput(action="list", days=366)


class TestSeoGeoInput:
    def test_valid(self):
        m = SeoGeoInput(urls=["https://example.com"])
        assert m.include_ai_recommendations is True


class TestGscManageInput:
    def test_valid(self):
        m = GscManageInput(action="sites")
        assert m.action == "sites"
        assert m.force_refresh is False

    def test_site_url_allows_sc_domain(self):
        """site_url is str (not SafeUrl) to allow sc-domain: format."""
        m = GscManageInput(action="sites", site_url="sc-domain:example.com")
        assert m.site_url == "sc-domain:example.com"

    def test_index_action_default_type(self):
        m = GscManageInput(action="index", page_url="https://example.com/a")
        assert m.action == "index"
        assert m.index_type == "URL_UPDATED"

    def test_index_type_invalid(self):
        with pytest.raises(ValidationError):
            GscManageInput(action="index", index_type="BOGUS")


class TestGscAnalyticsInput:
    def test_valid(self):
        m = GscAnalyticsInput(action="query", site_url="sc-domain:example.com")
        assert m.days == 28
        assert m.limit == 50

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            GscAnalyticsInput(action="invalid", site_url="example.com")


class TestSeoStrategyInput:
    def test_valid(self):
        m = SeoStrategyInput(action="action_plan")
        assert m.max_actions == 20
        assert m.language == "en"

    def test_max_actions_bounds(self):
        with pytest.raises(ValidationError):
            SeoStrategyInput(action="action_plan", max_actions=51)


class TestSeoMonitorInput:
    def test_valid(self):
        m = SeoMonitorInput(action="anomalies")
        assert m.days_back == 28
        assert m.issue_type == "indexation_leak"


class TestSeoSerpInput:
    def test_valid(self):
        m = SeoSerpInput(action="predict", keywords=["seo"])
        assert m.engine == "google"

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            SeoSerpInput(action="invalid", keywords=["seo"])


class TestSeoSiteInput:
    def test_valid(self):
        m = SeoSiteInput(action="sitemap")
        assert m.max_pages == 500
        assert m.quick is False

    def test_invalid_action(self):
        with pytest.raises(ValidationError):
            SeoSiteInput(action="invalid")
