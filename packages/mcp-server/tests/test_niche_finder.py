"""Tests for NicheFinderService — real API calls."""

import pytest

from app.services.market.niche_finder import NicheFinderService


@pytest.fixture(scope="module")
def service():
    return NicheFinderService()


@pytest.mark.integration
class TestNicheFinder:
    """Tests with real pytrends API calls."""

    def test_find_niches_returns_results(self, service):
        result = service.find_niches(seed_keywords=["crm"])

        assert "niches" in result
        assert "meta" in result

    def test_niches_sorted_by_opportunity(self, service):
        result = service.find_niches(seed_keywords=["crm"])

        if result["niches"]:
            scores = [n["opportunity_score"] for n in result["niches"]]
            assert scores == sorted(scores, reverse=True)

    def test_niches_have_required_fields(self, service):
        result = service.find_niches(seed_keywords=["crm"])

        for niche in result["niches"]:
            assert "keyword" in niche
            assert "opportunity_score" in niche
            assert "growth_rate" in niche
            assert "relevance" in niche

    def test_max_results_respected(self, service):
        result = service.find_niches(seed_keywords=["crm"], max_results=3)

        assert len(result["niches"]) <= 3

    def test_seed_keywords_excluded(self, service):
        result = service.find_niches(seed_keywords=["crm"])

        niche_keywords = [n["keyword"] for n in result["niches"]]
        assert "crm" not in niche_keywords


class TestNicheFinderUnit:
    """Unit tests for computation methods (no API)."""

    def test_compute_relevance_basic(self):
        seeds = ["crm logiciel"]
        candidates = ["crm cloud", "erp entreprise"]
        scores = NicheFinderService._compute_relevance(seeds, candidates)

        assert "crm cloud" in scores
        assert "erp entreprise" in scores
        assert scores["crm cloud"] > scores["erp entreprise"]

    def test_compute_relevance_empty(self):
        scores = NicheFinderService._compute_relevance(["crm"], [])
        assert scores == {}
