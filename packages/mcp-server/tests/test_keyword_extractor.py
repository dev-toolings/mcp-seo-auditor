"""Tests for keyword extractor service."""

from app.services.keyword_extractor import SPACY_MODELS, STOPWORDS, KeywordExtractorService


class TestKeywordExtractor:
    """Test keyword extraction."""

    def test_extract_simple_keywords_english(self):
        """Test basic keyword extraction in English."""
        extractor = KeywordExtractorService(language="en")

        text = """
        Python programming language is widely used for web development.
        Python frameworks like Django and Flask are popular choices.
        Web development with Python is efficient and productive.
        """

        keywords = extractor.extract_keywords(text, max_keywords=10, language="en")

        assert len(keywords) > 0
        keywords_lower = [k.lower() for k in keywords]
        assert any("python" in k for k in keywords_lower)

    def test_extract_simple_keywords_french(self):
        """Test basic keyword extraction in French."""
        extractor = KeywordExtractorService(language="fr")

        text = """
        Voiture d'occasion Renault Clio disponible.
        Cette Renault Clio est en excellent état.
        Prix négociable pour cette voiture.
        """

        keywords = extractor.extract_keywords(text, max_keywords=10, language="fr")

        assert len(keywords) > 0
        keywords_lower = [k.lower() for k in keywords]
        assert any("renault" in k for k in keywords_lower) or any(
            "clio" in k for k in keywords_lower
        )

    def test_title_weighting(self):
        """Test that title keywords are weighted higher."""
        extractor = KeywordExtractorService(language="en")

        text = "General content about various topics and miscellaneous items."
        title = "Special Product Review"

        keywords = extractor.extract_keywords(text, title=title, max_keywords=10, language="en")

        keywords_lower = [k.lower() for k in keywords]
        assert any("special" in k or "product" in k or "review" in k for k in keywords_lower)

    def test_similarity_calculation(self):
        """Test Jaccard similarity calculation."""
        extractor = KeywordExtractorService()

        keywords1 = ["car", "renault", "clio", "paris"]
        keywords2 = ["car", "renault", "megane", "lyon"]

        similarity = extractor.calculate_similarity(keywords1, keywords2)

        assert 0 < similarity < 1

    def test_identical_keywords_similarity(self):
        """Test similarity of identical keyword lists."""
        extractor = KeywordExtractorService()

        keywords = ["car", "used", "paris"]

        similarity = extractor.calculate_similarity(keywords, keywords)

        assert similarity == 1.0

    def test_no_common_keywords_similarity(self):
        """Test similarity of completely different keywords."""
        extractor = KeywordExtractorService()

        keywords1 = ["car", "automobile", "vehicle"]
        keywords2 = ["house", "apartment", "real_estate"]

        similarity = extractor.calculate_similarity(keywords1, keywords2)

        assert similarity == 0.0

    def test_multi_language_stopwords(self):
        """Test that stopwords exist for multiple languages."""
        assert "fr" in STOPWORDS
        assert "en" in STOPWORDS
        assert len(STOPWORDS["fr"]) > 20
        assert len(STOPWORDS["en"]) > 20

    def test_spacy_models_mapping(self):
        """Test that spaCy model mapping covers expected languages."""
        expected_langs = {"fr", "en", "es", "de", "it", "pt", "nl"}
        assert expected_langs.issubset(set(SPACY_MODELS.keys()))

    def test_language_parameter(self):
        """Test that language parameter works."""
        extractor = KeywordExtractorService(language="en")

        text = "The quick brown fox jumps over the lazy dog repeatedly"
        keywords_en = extractor.extract_keywords(text, language="en")

        # Should filter English stopwords
        assert "the" not in keywords_en
        assert "over" not in keywords_en
