"""Tests for SaaSViabilityService — real API calls."""

import pytest

from app.services.market.saas_viability import SaaSViabilityService


@pytest.fixture(scope="module")
def service():
    return SaaSViabilityService()


@pytest.mark.integration
class TestSaaSViability:
    """Integration tests with real API calls."""

    @pytest.mark.asyncio
    async def test_assess_returns_full_report(self, service):
        result = await service.assess(
            concept="CRM SaaS",
            target_keywords=["crm saas"],
            market_type="B2B",
        )

        assert "score" in result
        assert "verdict" in result
        assert "dimensions" in result
        assert "recommendations" in result
        assert 0 <= result["score"] <= 100
        assert result["verdict"] in ("go", "explore", "no-go")

    @pytest.mark.asyncio
    async def test_assess_has_four_dimensions(self, service):
        result = await service.assess(concept="CRM SaaS", target_keywords=["crm saas"])

        assert len(result["dimensions"]) == 4
        names = [d["name"] for d in result["dimensions"]]
        assert "demand" in names
        assert "growth" in names
        assert "competition" in names
        assert "open_source" in names

    @pytest.mark.asyncio
    async def test_assess_has_keyword_insights(self, service):
        result = await service.assess(concept="CRM SaaS", target_keywords=["crm saas"])

        assert "keyword_insights" in result

    @pytest.mark.asyncio
    async def test_assess_has_github_signal(self, service):
        result = await service.assess(concept="CRM SaaS", target_keywords=["crm saas"])

        assert result["github_signal"] is not None
        assert "total_repos" in result["github_signal"]

    @pytest.mark.asyncio
    async def test_assess_marketplace_type(self, service):
        result = await service.assess(
            concept="marketplace immobilier",
            target_keywords=["marketplace immobilier"],
            market_type="marketplace",
        )

        assert result["market_type"] == "marketplace"
        assert any("marketplace" in r.lower() for r in result["recommendations"])


class TestScoringUnit:
    """Unit tests for scoring methods (no API)."""

    def test_score_demand(self):
        keyword_data = {"keywords": [{"relative_volume": 60}, {"relative_volume": 80}]}
        assert SaaSViabilityService._score_demand(keyword_data) == 70.0

    def test_score_demand_empty(self):
        assert SaaSViabilityService._score_demand({"keywords": []}) == 0.0

    def test_score_growth_positive(self):
        trend_data = {"trends": [{"growth_rate": 30}]}
        assert SaaSViabilityService._score_growth(trend_data) == 80.0

    def test_score_growth_negative(self):
        trend_data = {"trends": [{"growth_rate": -30}]}
        assert SaaSViabilityService._score_growth(trend_data) == 20.0

    def test_score_growth_no_data(self):
        assert SaaSViabilityService._score_growth({"trends": []}) == 50.0

    def test_score_competition_monopolistic(self):
        data = {
            "competitors": [{"relative_interest": 90}],
            "market_overview": {"concentration": "monopolistic"},
        }
        assert SaaSViabilityService._score_competition(data) == 15.0

    def test_score_competition_no_competitors(self):
        data = {"competitors": [], "market_overview": {"concentration": "unknown"}}
        assert SaaSViabilityService._score_competition(data) == 90.0

    def test_score_opensource_none(self):
        data = {"total_repos": 0, "total_stars": 0, "avg_recent_activity": 0}
        assert SaaSViabilityService._score_opensource(data) == 95.0

    def test_score_opensource_heavy(self):
        data = {"total_repos": 500, "total_stars": 50000, "avg_recent_activity": 100}
        assert SaaSViabilityService._score_opensource(data) < 30

    def test_verdict_go_recommendations(self):
        svc = SaaSViabilityService.__new__(SaaSViabilityService)
        recs = svc._generate_recommendations("go", 80, 75, 80, 90, "B2B")
        assert any("favorable" in r.lower() for r in recs)

    def test_verdict_no_go_recommendations(self):
        svc = SaaSViabilityService.__new__(SaaSViabilityService)
        recs = svc._generate_recommendations("no-go", 20, 30, 15, 20, "B2B")
        assert any("challenging" in r.lower() for r in recs)
