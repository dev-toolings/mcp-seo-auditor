"""Keyword extraction service using spaCy NLP (multi-language)."""

import logging
import re
from collections import Counter
from typing import Any, Optional

logger = logging.getLogger(__name__)

# spaCy model mapping by language
SPACY_MODELS: dict[str, str] = {
    "fr": "fr_core_news_sm",
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "de": "de_core_news_sm",
    "it": "it_core_news_sm",
    "pt": "pt_core_news_sm",
    "nl": "nl_core_news_sm",
    "ja": "ja_core_news_sm",
    "zh": "zh_core_web_sm",
}

# Stopwords by language
STOPWORDS: dict[str, set[str]] = {
    "fr": {
        "de",
        "la",
        "le",
        "les",
        "du",
        "des",
        "un",
        "une",
        "et",
        "en",
        "à",
        "au",
        "aux",
        "ce",
        "cette",
        "ces",
        "son",
        "sa",
        "ses",
        "notre",
        "nos",
        "votre",
        "vos",
        "leur",
        "leurs",
        "qui",
        "que",
        "quoi",
        "dont",
        "où",
        "pour",
        "par",
        "avec",
        "sans",
        "sur",
        "sous",
        "dans",
        "entre",
        "vers",
        "chez",
        "contre",
        "après",
        "avant",
        "depuis",
        "pendant",
        "plus",
        "moins",
        "très",
        "bien",
        "aussi",
        "comme",
        "mais",
        "ou",
        "donc",
        "car",
        "ni",
        "ne",
        "pas",
        "rien",
        "tout",
        "tous",
        "toutes",
        "même",
        "autre",
        "autres",
        "être",
        "avoir",
        "faire",
        "aller",
        "voir",
        "venir",
        "pouvoir",
        "vouloir",
        "devoir",
        "falloir",
        "dit",
        "fait",
        "page",
        "site",
        "cliquez",
        "ici",
        "accueil",
    },
    "en": {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "their",
        "we",
        "our",
        "you",
        "your",
        "my",
        "not",
        "no",
        "nor",
        "so",
        "if",
        "then",
        "than",
        "too",
        "very",
        "just",
        "about",
        "above",
        "after",
        "again",
        "all",
        "also",
        "any",
        "as",
        "each",
        "even",
        "more",
        "most",
        "other",
        "some",
        "such",
        "into",
        "over",
        "own",
        "same",
        "up",
        "out",
        "how",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "page",
        "site",
        "click",
        "here",
        "home",
    },
}


class KeywordExtractorService:
    """Extract keywords from text using NLP (spaCy) with multi-language support."""

    _nlp_cache: dict[str, Any] = {}

    def __init__(self, nlp: Optional[Any] = None, language: str = "en"):
        """Initialize with optional pre-loaded spaCy model."""
        self.language = language
        self.stopwords = STOPWORDS.get(language, STOPWORDS["en"])

        if nlp is not None:
            self._nlp_cache[language] = nlp

    def _get_nlp(self, language: str) -> Optional[Any]:
        """Get or lazy-load the spaCy model for a given language."""
        if language in self._nlp_cache:
            return self._nlp_cache[language]

        model_name = SPACY_MODELS.get(language)
        if not model_name:
            logger.warning(f"No spaCy model configured for language: {language}")
            return None

        try:
            import spacy

            nlp = spacy.load(model_name)
            self._nlp_cache[language] = nlp
            return nlp
        except Exception as e:
            logger.warning(f"spaCy model '{model_name}' not available: {e}")
            return None

    def extract_keywords(
        self,
        text: str,
        title: Optional[str] = None,
        max_keywords: int = 20,
        language: Optional[str] = None,
    ) -> list[str]:
        """Extract keywords from text. Returns a list of keywords sorted by importance."""
        lang = language or self.language
        stopwords = STOPWORDS.get(lang, STOPWORDS["en"])

        # Combine title (with higher weight) and content
        full_text = ""
        if title:
            full_text = (title + " ") * 3
        full_text += text

        nlp = self._get_nlp(lang)
        if nlp:
            return self._extract_with_spacy(full_text, max_keywords, nlp, stopwords)
        else:
            return self._extract_simple(full_text, max_keywords, stopwords)

    def _extract_with_spacy(
        self, text: str, max_keywords: int, nlp: Any, stopwords: set[str]
    ) -> list[str]:
        """Extract keywords using spaCy NLP."""
        text = text[:50000]

        doc = nlp(text)

        keywords = []

        # Extract named entities (high value)
        for ent in doc.ents:
            if ent.label_ in ("ORG", "PRODUCT", "LOC", "GPE"):
                keywords.append(ent.text.lower())

        # Extract nouns and noun phrases
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                lemma = token.lemma_.lower()
                if len(lemma) > 2 and lemma not in stopwords:
                    keywords.append(lemma)

        # Extract noun chunks (2-3 word phrases)
        for chunk in doc.noun_chunks:
            phrase = chunk.text.lower().strip()
            if 2 <= len(phrase.split()) <= 3:
                first_word = phrase.split()[0]
                if first_word not in stopwords:
                    keywords.append(phrase)

        keyword_counts = Counter(keywords)
        top_keywords = [kw for kw, _ in keyword_counts.most_common(max_keywords)]

        return top_keywords

    def _extract_simple(self, text: str, max_keywords: int, stopwords: set[str]) -> list[str]:
        """Simple keyword extraction without NLP (fallback)."""
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        words = text.split()

        words = [w for w in words if len(w) > 2 and w not in stopwords and not w.isdigit()]

        word_counts = Counter(words)

        # Also extract 2-word phrases
        bigrams = []
        for i in range(len(words) - 1):
            if words[i] not in stopwords and words[i + 1] not in stopwords:
                bigrams.append(f"{words[i]} {words[i + 1]}")

        bigram_counts = Counter(bigrams)

        all_counts = word_counts + bigram_counts
        top_keywords = [kw for kw, _ in all_counts.most_common(max_keywords)]

        return top_keywords

    def calculate_similarity(self, keywords1: list[str], keywords2: list[str]) -> float:
        """Calculate Jaccard similarity between two keyword lists."""
        if not keywords1 or not keywords2:
            return 0.0

        set1 = set(keywords1)
        set2 = set(keywords2)

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0
