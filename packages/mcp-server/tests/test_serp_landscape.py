"""Tests for SERP landscape service."""

import pytest

from app.services.serp_landscape import SERPLandscapeService


class TestSERPLandscapeService:
    def setup_method(self):
        self.service = SERPLandscapeService()

    def test_classify_intent_informational(self):
        assert self.service._classify_intent("how to bake bread") == "informational"
        assert self.service._classify_intent("what is SEO") == "informational"
        assert self.service._classify_intent("comment faire un gateau") == "informational"

    def test_classify_intent_commercial(self):
        assert self.service._classify_intent("best laptop 2025") == "commercial"
        assert self.service._classify_intent("meilleur CRM comparatif") == "commercial"

    def test_classify_intent_transactional(self):
        assert self.service._classify_intent("buy iPhone 15") == "transactional"
        assert self.service._classify_intent("acheter voiture pas cher") == "transactional"

    def test_classify_intent_navigational(self):
        assert self.service._classify_intent("gmail login") == "navigational"

    def test_classify_intent_default(self):
        # Ambiguous query defaults to informational
        assert self.service._classify_intent("python") == "informational"

    def test_estimate_features_informational(self):
        features = self.service._estimate_features("how to learn python", "informational")
        assert features["featured_snippet"]["likely"] is True
        assert features["people_also_ask"]["likely"] is True

    def test_estimate_features_local(self):
        features = self.service._estimate_features("restaurant near me", "informational")
        assert features["local_pack"]["likely"] is True

    def test_estimate_features_video(self):
        features = self.service._estimate_features("tutorial react hooks", "informational")
        assert features["video_carousel"]["likely"] is True

    def test_estimate_features_shopping(self):
        features = self.service._estimate_features("buy running shoes", "transactional")
        assert features["shopping_results"]["likely"] is True

    def test_guess_snippet_type(self):
        assert self.service._guess_snippet_type("best laptops list") == "list"
        assert self.service._guess_snippet_type("python vs javascript") == "table"
        assert self.service._guess_snippet_type("what is SEO") == "paragraph"
        assert self.service._guess_snippet_type("random query") == "paragraph"

    def test_calculate_opportunity(self):
        features = {
            "featured_snippet": {"likely": True, "opportunity": "high"},
            "people_also_ask": {"likely": True, "opportunity": "high"},
            "faq_rich_result": {"likely": True, "opportunity": "high"},
        }
        score = self.service._calculate_opportunity(features, "informational", None)
        assert score > 50  # High opportunity
        assert score <= 100

    def test_keyword_recommendations(self):
        features = {
            "featured_snippet": {"likely": True, "type": "paragraph"},
            "people_also_ask": {"likely": True},
        }
        recs = self.service._keyword_recommendations("how to learn SEO", features, "informational")
        assert len(recs) > 0
        assert any("snippet" in r.lower() for r in recs)

    def test_build_summary(self):
        results = [
            {
                "keyword": "test",
                "intent": "informational",
                "features": {
                    "featured_snippet": {"likely": True},
                    "people_also_ask": {"likely": True},
                },
                "opportunity_score": 70,
            },
            {
                "keyword": "buy shoes",
                "intent": "transactional",
                "features": {
                    "shopping_results": {"likely": True},
                },
                "opportunity_score": 60,
            },
        ]
        summary = self.service._build_summary(results)
        assert summary["total_keywords"] == 2
        assert summary["avg_opportunity_score"] == 65
        assert "informational" in summary["intent_distribution"]

    def test_build_summary_empty(self):
        assert self.service._build_summary([]) == {}

    def test_identify_opportunities(self):
        results = [
            {
                "keyword": "how to cook pasta",
                "features": {
                    "featured_snippet": {"likely": True, "opportunity": "high", "type": "list"},
                    "people_also_ask": {"likely": True, "opportunity": "high"},
                    "faq_rich_result": {"likely": True, "opportunity": "high"},
                },
            },
        ]
        opps = self.service._identify_opportunities(results, None)
        assert len(opps) > 0
        assert any("featured_snippet" in o["type"] for o in opps)

    @pytest.mark.asyncio
    async def test_analyze_empty_keywords(self):
        result = await self.service.analyze([])
        assert result.get("error") == "No keywords provided"

    @pytest.mark.asyncio
    async def test_analyze_keywords(self):
        result = await self.service.analyze(["how to learn SEO", "best CRM software"])
        assert result["keywords_analyzed"] == 2
        assert len(result["results"]) == 2
        assert "summary" in result
        assert result["ai_enhanced"] is False
