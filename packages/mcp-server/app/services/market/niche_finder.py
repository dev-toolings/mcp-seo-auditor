"""Niche finder service combining Google Trends rising queries with TF-IDF relevance."""

import logging
from typing import cast

from pytrends.request import TrendReq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.services.market._rate_limiter import rate_limit_pytrends as _rate_limit_pytrends

logger = logging.getLogger(__name__)


class NicheFinderService:
    """Find niche opportunities using rising queries + TF-IDF relevance scoring."""

    def __init__(self, hl: str = "fr", tz: int = 60):
        self.pytrends = TrendReq(hl=hl, tz=tz)

    def find_niches(
        self,
        seed_keywords: list[str],
        max_results: int = 20,
        geo: str = "FR",
        timeframe: str = "today 12-m",
    ) -> dict:
        """Find niche opportunities from seed keywords.

        Algorithm:
        1. Get rising queries from Google Trends for each seed
        2. Score relevance to seeds using TF-IDF cosine similarity
        3. opportunity_score = rising_percentage × relevance_score

        Returns:
            dict with keys: niches (list), meta (dict)
        """
        # Step 1: Collect rising queries
        rising_candidates: dict[str, float] = {}

        for seed in seed_keywords:
            try:
                _rate_limit_pytrends()
                self.pytrends.build_payload([seed], geo=geo, timeframe=timeframe)
                rq = self.pytrends.related_queries()

                if seed in rq and rq[seed] is not None:
                    rising = rq[seed].get("rising")
                    if rising is not None and not rising.empty:
                        for _, row in rising.iterrows():
                            query = row.get("query", "")
                            value = row.get("value", 0)
                            if query and query.lower() not in [s.lower() for s in seed_keywords]:
                                # value for rising queries is percentage growth
                                if query in rising_candidates:
                                    rising_candidates[query] = max(rising_candidates[query], value)
                                else:
                                    rising_candidates[query] = value
            except Exception as e:
                logger.warning(f"Failed to get rising queries for '{seed}': {e}")

        if not rising_candidates:
            return {
                "niches": [],
                "meta": {
                    "seed_keywords": seed_keywords,
                    "total_niches": 0,
                    "geo": geo,
                },
            }

        # Step 2: Score relevance using TF-IDF cosine similarity
        candidate_keywords = list(rising_candidates.keys())
        relevance_scores = self._compute_relevance(seed_keywords, candidate_keywords)

        # Step 3: Compute opportunity score
        niches = []
        for kw in candidate_keywords:
            growth = rising_candidates[kw]
            relevance = relevance_scores.get(kw, 0.0)

            # Normalize growth (cap at 5000% for scoring)
            normalized_growth = min(growth, 5000) / 5000.0

            opportunity = normalized_growth * relevance * 100

            niches.append(
                {
                    "keyword": kw,
                    "opportunity_score": round(opportunity, 2),
                    "growth_rate": growth,
                    "relevance": round(relevance, 4),
                }
            )

        # Sort by opportunity score descending
        niches.sort(key=lambda x: cast(float, x["opportunity_score"]), reverse=True)
        niches = niches[:max_results]

        return {
            "niches": niches,
            "meta": {
                "seed_keywords": seed_keywords,
                "total_niches": len(niches),
                "geo": geo,
                "timeframe": timeframe,
                "note": "Growth rate is percentage increase from Google Trends rising queries. Relevance is TF-IDF cosine similarity to seed keywords.",
            },
        }

    @staticmethod
    def _compute_relevance(seeds: list[str], candidates: list[str]) -> dict[str, float]:
        """Compute TF-IDF cosine similarity between seeds and candidates."""
        if not candidates:
            return {}

        all_texts = seeds + candidates
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))

        try:
            tfidf_matrix = vectorizer.fit_transform(all_texts)
        except ValueError:
            return {c: 0.0 for c in candidates}

        # Seed vectors: first len(seeds) rows
        seed_vectors = tfidf_matrix[: len(seeds)]
        candidate_vectors = tfidf_matrix[len(seeds) :]

        import numpy as np

        # Mean seed vector (convert from matrix to array for sklearn compatibility)
        mean_seed = np.asarray(seed_vectors.mean(axis=0))

        # Cosine similarity between mean seed and each candidate
        similarities = cosine_similarity(mean_seed, candidate_vectors).flatten()

        return {candidate: float(sim) for candidate, sim in zip(candidates, similarities)}
