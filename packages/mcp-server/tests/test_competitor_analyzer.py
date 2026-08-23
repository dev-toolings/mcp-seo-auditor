"""Tests for CompetitorAnalyzerService — real API calls."""

import pytest

from app.services.market.competitor_analyzer import CompetitorAnalyzerService


@pytest.fixture(scope="module")
def service():
    return CompetitorAnalyzerService()


@pytest.mark.integration
class TestCompetitorAnalyzer:
    """Tests with real pytrends API calls."""

    def test_analyze_finds_competitors(self, service):
        result = service.analyze(keywords=["crm"], max_results=5)

        assert "competitors" in result
        assert "market_overview" in result
        assert "meta" in result

    def test_competitors_have_required_fields(self, service):
        result = service.analyze(keywords=["crm"], max_results=5)

        for comp in result["competitors"]:
            assert "name" in comp
            assert "relative_interest" in comp
            assert "trend_direction" in comp
            assert comp["trend_direction"] in ("up", "stable", "down")

    def test_market_overview_structure(self, service):
        result = service.analyze(keywords=["crm"])

        overview = result["market_overview"]
        assert "total_competitors" in overview
        assert "concentration" in overview

    def test_max_results_respected(self, service):
        result = service.analyze(keywords=["crm"], max_results=3)

        assert len(result["competitors"]) <= 3


class TestCompetitorAnalyzerUnit:
    """Unit tests for computation methods (no API)."""

    def test_compute_direction_up(self):
        values = list(range(20, 72))
        assert CompetitorAnalyzerService._compute_direction(values) == "up"

    def test_compute_direction_down(self):
        values = list(range(72, 20, -1))
        assert CompetitorAnalyzerService._compute_direction(values) == "down"

    def test_compute_direction_stable(self):
        values = [50] * 52
        assert CompetitorAnalyzerService._compute_direction(values) == "stable"

    def test_assess_concentration_monopolistic(self):
        competitors = [
            {"relative_interest": 90},
            {"relative_interest": 5},
            {"relative_interest": 5},
        ]
        assert CompetitorAnalyzerService._assess_concentration(competitors) == "monopolistic"

    def test_assess_concentration_fragmented(self):
        competitors = [
            {"relative_interest": 25},
            {"relative_interest": 20},
            {"relative_interest": 18},
            {"relative_interest": 15},
            {"relative_interest": 12},
        ]
        assert CompetitorAnalyzerService._assess_concentration(competitors) == "fragmented"

    def test_assess_concentration_empty(self):
        assert CompetitorAnalyzerService._assess_concentration([]) == "unknown"
