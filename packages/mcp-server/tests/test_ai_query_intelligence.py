"""Tests for AI Query Intelligence service."""

from app.services.ai.ai_query_intelligence import (
    AIQueryIntelligenceService,
    ClassifiedQuery,
)


class TestDetectAiQueries:
    """Tests for detect_ai_queries classification."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def test_long_query_gets_higher_probability(self):
        """Queries with 10+ words should score higher than short ones."""
        long_query = [
            {
                "query": "comment choisir le meilleur logiciel de gestion de projet pour une startup",
                "clicks": 5,
                "impressions": 100,
                "ctr": 0.05,
                "position": 8.0,
            }
        ]
        short_query = [
            {
                "query": "logiciel gestion projet",
                "clicks": 5,
                "impressions": 100,
                "ctr": 0.05,
                "position": 8.0,
            }
        ]
        long_classified = self.service.detect_ai_queries(long_query, language="fr")
        short_classified = self.service.detect_ai_queries(short_query, language="fr")
        assert long_classified[0].ai_probability > short_classified[0].ai_probability

    def test_very_long_query_gets_maximum_word_count_boost(self):
        """Queries with 15+ words get the highest word-count probability signal."""
        very_long = " ".join(["mot"] * 16)
        classified = self.service.detect_ai_queries(
            [{"query": very_long, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}],
            language="fr",
        )
        assert classified[0].ai_probability >= 0.5
        assert any("very_long_query" in s for s in classified[0].signals)

    def test_french_question_word_increases_probability(self):
        """French question words should trigger question_word signal."""
        classified = self.service.detect_ai_queries(
            [
                {
                    "query": "comment installer python sur mac",
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0.0,
                    "position": 0.0,
                }
            ],
            language="fr",
        )
        assert classified[0].ai_probability > 0
        assert any("question_word" in s for s in classified[0].signals)

    def test_english_question_word_increases_probability(self):
        """English question words should trigger question_word signal."""
        classified = self.service.detect_ai_queries(
            [
                {
                    "query": "how to install python on mac",
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0.0,
                    "position": 0.0,
                }
            ],
            language="en",
        )
        assert any("question_word" in s for s in classified[0].signals)

    def test_keyword_style_query_has_low_probability(self):
        """Short keyword-style queries should have low AI probability."""
        classified = self.service.detect_ai_queries(
            [
                {
                    "query": "voiture occasion",
                    "clicks": 10,
                    "impressions": 200,
                    "ctr": 0.05,
                    "position": 3.0,
                }
            ],
            language="fr",
        )
        assert classified[0].ai_probability < 0.5

    def test_empty_queries_list_returns_empty_list(self):
        """Empty input should return empty output."""
        result = self.service.detect_ai_queries([], language="fr")
        assert result == []

    def test_query_with_empty_string_is_skipped(self):
        """Queries with empty string are filtered out."""
        result = self.service.detect_ai_queries(
            [{"query": "", "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}],
            language="fr",
        )
        assert result == []

    def test_probability_capped_at_one(self):
        """Probability should never exceed 1.0."""
        # A query with all signals firing
        query = (
            "comment faire pour trouver le meilleur comparatif des alternatives "
            "aux logiciels de gestion avec des tutoriels détaillés"
        )
        classified = self.service.detect_ai_queries(
            [{"query": query, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}],
            language="fr",
        )
        assert classified[0].ai_probability <= 1.0

    def test_word_count_is_stored_on_result(self):
        """word_count attribute should reflect actual word count of query."""
        query = "python pour les débutants"
        classified = self.service.detect_ai_queries(
            [{"query": query, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}],
            language="fr",
        )
        assert classified[0].word_count == 4

    def test_page_field_preserved_from_input(self):
        """The page field from input should be passed through to ClassifiedQuery."""
        classified = self.service.detect_ai_queries(
            [
                {
                    "query": "test query",
                    "page": "https://example.com/page",
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0.0,
                    "position": 0.0,
                }
            ],
            language="fr",
        )
        assert classified[0].page == "https://example.com/page"


class TestClassifyIntent:
    """Tests for intent classification accuracy."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def _classify(self, query: str) -> str:
        classified = self.service.detect_ai_queries(
            [{"query": query, "clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}],
            language="fr",
        )
        return classified[0].category

    def test_comparison_query_classified_correctly(self):
        assert self._classify("wordpress vs wix lequel choisir") == "comparison"

    def test_how_to_query_classified_correctly(self):
        assert self._classify("comment créer un site web") == "how_to"

    def test_definition_query_classified_correctly(self):
        assert self._classify("qu'est-ce que le SEO") == "definition"

    def test_guide_query_classified_correctly(self):
        # "guide complet" matches how_to first (guide is in how_to patterns)
        # Use a query that only matches "guide" patterns
        assert self._classify("tout savoir sur le référencement naturel en détail") == "guide"

    def test_best_of_query_classified_correctly(self):
        # "meilleur" matches comparison first; use a best_of-only pattern
        assert self._classify("idéal pour les débutants choix parfait") == "best_of"

    def test_evaluation_query_classified_correctly(self):
        assert self._classify("avis sur hostinger est-ce fiable") == "evaluation"

    def test_unrecognized_query_returns_informational(self):
        assert self._classify("achat chaussure rouge") == "informational"

    def test_english_comparison_classified_correctly(self):
        classified = self.service.detect_ai_queries(
            [
                {
                    "query": "react vs vue which is better",
                    "clicks": 0,
                    "impressions": 0,
                    "ctr": 0.0,
                    "position": 0.0,
                }
            ],
            language="en",
        )
        assert classified[0].category == "comparison"


class TestIsNaturalLanguage:
    """Tests for natural language detection."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def test_french_sentence_with_articles_is_natural(self):
        assert self.service._is_natural_language("le meilleur outil pour la gestion") is True

    def test_english_sentence_with_articles_is_natural(self):
        assert self.service._is_natural_language("the best tool for the project") is True

    def test_keyword_string_is_not_natural(self):
        assert self.service._is_natural_language("achat voiture occasion paris") is False

    def test_single_word_is_not_natural(self):
        assert self.service._is_natural_language("python") is False

    def test_query_with_two_nl_words_qualifies(self):
        # "de" and "pour" are both NL words
        assert self.service._is_natural_language("outil de gestion pour équipe") is True


class TestFindEnrichmentOpportunities:
    """Tests for enrichment opportunity detection."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def _make_query(self, impressions, position, ctr, category="how_to"):
        return ClassifiedQuery(
            query="comment faire quelque chose de très spécifique",
            clicks=int(impressions * ctr),
            impressions=impressions,
            ctr=ctr,
            position=position,
            ai_probability=0.8,
            category=category,
        )

    def test_high_impressions_poor_position_is_opportunity(self):
        """Impressions >= 50 and position > 10 should be flagged."""
        query = self._make_query(impressions=200, position=15.0, ctr=0.03)
        opps = self.service.find_enrichment_opportunities([query])
        assert len(opps) == 1
        assert opps[0]["query"] == query.query

    def test_high_impressions_low_ctr_is_opportunity(self):
        """Impressions >= 50 and CTR < 2% should be flagged regardless of position."""
        query = self._make_query(impressions=100, position=5.0, ctr=0.01)
        opps = self.service.find_enrichment_opportunities([query])
        assert len(opps) == 1

    def test_low_impressions_not_an_opportunity(self):
        """Impressions < 50 should not qualify as opportunity."""
        query = self._make_query(impressions=20, position=15.0, ctr=0.01)
        opps = self.service.find_enrichment_opportunities([query])
        assert len(opps) == 0

    def test_good_position_good_ctr_not_an_opportunity(self):
        """Page ranking well with decent CTR is not an opportunity."""
        query = self._make_query(impressions=500, position=3.0, ctr=0.10)
        opps = self.service.find_enrichment_opportunities([query])
        assert len(opps) == 0

    def test_opportunities_sorted_by_score_descending(self):
        """Results should be sorted with highest opportunity first."""
        q_high = self._make_query(impressions=600, position=25.0, ctr=0.005)
        q_low = self._make_query(impressions=60, position=12.0, ctr=0.03)
        opps = self.service.find_enrichment_opportunities([q_low, q_high])
        assert opps[0]["opportunity_score"] >= opps[-1]["opportunity_score"]

    def test_opportunity_contains_expected_keys(self):
        """Each opportunity dict should have the expected structure."""
        query = self._make_query(impressions=300, position=18.0, ctr=0.01)
        opps = self.service.find_enrichment_opportunities([query])
        assert len(opps) == 1
        opp = opps[0]
        for key in (
            "query",
            "category",
            "impressions",
            "position",
            "ctr",
            "suggested_content_type",
            "opportunity_score",
            "action",
        ):
            assert key in opp


class TestGroupByCategory:
    """Tests for _group_by_category aggregation."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def test_groups_queries_by_category(self):
        queries = [
            ClassifiedQuery(
                query="q1", clicks=10, impressions=100, position=5.0, category="how_to"
            ),
            ClassifiedQuery(query="q2", clicks=5, impressions=50, position=8.0, category="how_to"),
            ClassifiedQuery(
                query="q3", clicks=20, impressions=200, position=3.0, category="comparison"
            ),
        ]
        groups = self.service._group_by_category(queries)
        assert "how_to" in groups
        assert "comparison" in groups
        assert groups["how_to"]["count"] == 2
        assert groups["comparison"]["count"] == 1

    def test_aggregates_clicks_and_impressions(self):
        queries = [
            ClassifiedQuery(
                query="q1", clicks=10, impressions=100, position=5.0, category="how_to"
            ),
            ClassifiedQuery(query="q2", clicks=5, impressions=50, position=8.0, category="how_to"),
        ]
        groups = self.service._group_by_category(queries)
        assert groups["how_to"]["total_clicks"] == 15
        assert groups["how_to"]["total_impressions"] == 150

    def test_calculates_average_position(self):
        queries = [
            ClassifiedQuery(query="q1", position=4.0, category="guide"),
            ClassifiedQuery(query="q2", position=8.0, category="guide"),
        ]
        groups = self.service._group_by_category(queries)
        assert groups["guide"]["avg_position"] == 6.0

    def test_empty_queries_returns_empty_dict(self):
        groups = self.service._group_by_category([])
        assert groups == {}


class TestCalculateGrowth:
    """Tests for _calculate_growth trend computation."""

    def setup_method(self):
        self.service = AIQueryIntelligenceService()

    def test_ascending_ratios_detected_as_growing(self):
        period_data = [
            {"ai_ratio": 0.10},
            {"ai_ratio": 0.15},
            {"ai_ratio": 0.20},
            {"ai_ratio": 0.25},
        ]
        result = self.service._calculate_growth(period_data)
        assert result["trend"] in ("growing", "accelerating")

    def test_descending_ratios_detected_as_declining(self):
        period_data = [
            {"ai_ratio": 0.30},
            {"ai_ratio": 0.25},
            {"ai_ratio": 0.20},
            {"ai_ratio": 0.15},
        ]
        result = self.service._calculate_growth(period_data)
        assert result["trend"] == "declining"

    def test_single_period_returns_insufficient_data(self):
        result = self.service._calculate_growth([{"ai_ratio": 0.2}])
        assert result["trend"] == "insufficient_data"
        assert result["growth_rate"] == 0

    def test_zero_first_ratio_with_growth(self):
        """When first ratio is 0 and last is positive, growth should be 100%."""
        period_data = [{"ai_ratio": 0.0}, {"ai_ratio": 0.1}]
        result = self.service._calculate_growth(period_data)
        assert result["growth_rate"] == 100.0

    def test_growth_rate_positive_when_increasing(self):
        period_data = [{"ai_ratio": 0.10}, {"ai_ratio": 0.20}]
        result = self.service._calculate_growth(period_data)
        assert result["growth_rate"] > 0

    def test_growth_rate_negative_when_declining(self):
        period_data = [{"ai_ratio": 0.20}, {"ai_ratio": 0.10}]
        result = self.service._calculate_growth(period_data)
        assert result["growth_rate"] < 0

    def test_summary_contains_period_count(self):
        period_data = [{"ai_ratio": 0.10}, {"ai_ratio": 0.15}, {"ai_ratio": 0.20}]
        result = self.service._calculate_growth(period_data)
        assert "3 periods" in result["summary"]


class TestAnalyzeRequiresGSC:
    """Tests for analyze() requiring GSC to be configured."""

    async def test_analyze_returns_error_when_gsc_not_configured(self):
        service = AIQueryIntelligenceService(gsc_service=None)
        result = await service.analyze("https://example.com")
        assert "error" in result

    async def test_analyze_returns_error_when_gsc_credentials_missing(self):
        class FakeGSC:
            is_credentials_available = False

        service = AIQueryIntelligenceService(gsc_service=FakeGSC())
        result = await service.analyze("https://example.com")
        assert "error" in result
