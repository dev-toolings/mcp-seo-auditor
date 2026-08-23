"""Tests for KeywordResearchService — real API calls."""

import pytest

from app.services.market.keyword_research import KeywordResearchService


@pytest.fixture(scope="module")
def service():
    return KeywordResearchService()


@pytest.mark.integration
class TestKeywordResearch:
    """Tests with real pytrends API calls."""

    def test_research_returns_keywords(self, service):
        result = service.research(seed_keywords=["crm"], country="fr")

        assert "keywords" in result
        assert "clusters" in result
        assert "meta" in result
        assert result["meta"]["total_keywords"] >= 1
        assert result["meta"]["country"] == "fr"

    def test_research_volumes_structure(self, service):
        result = service.research(seed_keywords=["crm saas"], country="fr")

        # Verify all keywords have the relative_volume field (value may be 0 if rate-limited)
        for kw in result["keywords"]:
            assert "relative_volume" in kw
            assert isinstance(kw["relative_volume"], int)
            assert 0 <= kw["relative_volume"] <= 100

    def test_research_multiple_seeds(self, service):
        result = service.research(seed_keywords=["crm", "erp"], country="fr")

        assert result["meta"]["total_keywords"] >= 2
        keywords = [kw["keyword"] for kw in result["keywords"]]
        assert "crm" in keywords
        assert "erp" in keywords

    def test_clustering_works(self, service):
        result = service.research(seed_keywords=["crm", "erp"], country="fr")

        assert result["meta"]["total_clusters"] >= 1

    def test_extract_keywords_from_text(self, service):
        text = """
        Le CRM est un outil indispensable pour la gestion de la relation client.
        Les logiciels CRM comme Salesforce, HubSpot et Pipedrive permettent
        de suivre les prospects, gérer les ventes et automatiser le marketing.
        """
        result = service.extract_keywords_from_text(text, top_n=5)

        assert len(result) > 0
        assert all("keyword" in kw and "score" in kw for kw in result)


class TestClusteringUnit:
    """Unit tests for clustering (no API needed)."""

    def test_cluster_single_keyword(self):
        svc = KeywordResearchService.__new__(KeywordResearchService)
        clusters = svc._cluster_keywords(["single"])
        assert len(clusters) == 1

    def test_cluster_multiple_keywords(self):
        svc = KeywordResearchService.__new__(KeywordResearchService)
        keywords = [
            "crm logiciel",
            "crm gratuit",
            "erp entreprise",
            "erp cloud",
            "erp gratuit",
            "crm cloud",
        ]
        clusters = svc._cluster_keywords(keywords, n_clusters=2)
        assert len(clusters) == 2
        total = sum(len(v) for v in clusters.values())
        assert total == len(keywords)
