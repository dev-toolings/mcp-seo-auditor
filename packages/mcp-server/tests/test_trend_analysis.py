"""Tests for TrendAnalysisService — real API calls."""

import pytest

from app.services.market.trend_analysis import TrendAnalysisService


@pytest.fixture(scope="module")
def service():
    return TrendAnalysisService()


@pytest.mark.integration
class TestTrendAnalysis:
    """Tests with real pytrends API calls."""

    def test_analyze_returns_trends(self, service):
        result = service.analyze(keywords=["crm saas"], geo="FR")

        assert "trends" in result
        assert "related_queries" in result
        assert "meta" in result
        assert len(result["trends"]) == 1
        assert result["trends"][0]["keyword"] == "crm saas"

    def test_trend_values_populated(self, service):
        result = service.analyze(keywords=["python"], geo="FR")

        trend = result["trends"][0]
        assert len(trend["trend_values"]) > 0
        assert trend["direction"] in ("up", "stable", "down")

    def test_related_queries_populated(self, service):
        result = service.analyze(keywords=["crm"], geo="FR")

        rq = result["related_queries"].get("crm", {})
        # At least top or rising should have some results for a popular keyword
        assert "top" in rq or "rising" in rq

    def test_multiple_keywords(self, service):
        result = service.analyze(keywords=["crm", "erp"], geo="FR")

        assert len(result["trends"]) == 2
        keywords = [t["keyword"] for t in result["trends"]]
        assert "crm" in keywords
        assert "erp" in keywords


class TestTrendAnalysisUnit:
    """Unit tests for computation methods (no API)."""

    def test_compute_growth_rate_increasing(self):
        values = list(range(20, 72))
        rate = TrendAnalysisService._compute_growth_rate(values)
        assert rate > 0

    def test_compute_growth_rate_decreasing(self):
        values = list(range(72, 20, -1))
        rate = TrendAnalysisService._compute_growth_rate(values)
        assert rate < 0

    def test_compute_growth_rate_stable(self):
        values = [50] * 52
        rate = TrendAnalysisService._compute_growth_rate(values)
        assert abs(rate) < 1

    def test_detect_seasonality_seasonal(self):
        values = []
        for month in range(12):
            base = 80 if 4 <= month <= 8 else 30
            values.extend([base] * 4)
        assert TrendAnalysisService._detect_seasonality(values)

    def test_detect_seasonality_flat(self):
        values = [50] * 52
        assert not TrendAnalysisService._detect_seasonality(values)

    def test_determine_direction(self):
        assert TrendAnalysisService._determine_direction(30) == "up"
        assert TrendAnalysisService._determine_direction(-25) == "down"
        assert TrendAnalysisService._determine_direction(5) == "stable"
