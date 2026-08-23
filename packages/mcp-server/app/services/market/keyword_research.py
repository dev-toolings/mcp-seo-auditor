"""Keyword research service using pytrends and KeyBERT with TF-IDF backend."""

import logging
from collections import defaultdict
from typing import cast

from pytrends.request import TrendReq
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from tenacity import retry, stop_after_attempt, wait_exponential

from app.services.market._rate_limiter import rate_limit_pytrends as _rate_limit_pytrends

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=6, max=60),
    reraise=True,
)
def _pytrends_suggestions(pytrends: TrendReq, keyword: str) -> list[dict]:
    """Fetch pytrends suggestions with retry on rate limit errors."""
    _rate_limit_pytrends()
    return pytrends.suggestions(keyword=keyword)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=6, max=60),
    reraise=True,
)
def _pytrends_interest_over_time(pytrends: TrendReq, batch: list[str], geo: str):
    """Fetch pytrends interest over time with retry on rate limit errors."""
    _rate_limit_pytrends()
    pytrends.build_payload(batch, geo=geo, timeframe="today 12-m")
    return pytrends.interest_over_time()


class KeywordResearchService:
    """Keyword research using Google Trends + KeyBERT TF-IDF clustering."""

    def __init__(self, hl: str = "fr", tz: int = 60):
        self.pytrends = TrendReq(hl=hl, tz=tz)
        self._kw_model = None

    @property
    def kw_model(self):
        """Lazy-load KeyBERT to avoid slow startup from sentence-transformers."""
        if self._kw_model is None:
            from keybert import KeyBERT

            self._kw_model = KeyBERT()
        return self._kw_model

    def research(
        self,
        seed_keywords: list[str],
        country: str = "fr",
        language: str = "fr",
    ) -> dict:
        """Run keyword research from seed keywords.

        Returns:
            dict with keys: keywords (list), clusters (dict), meta (dict)
        """
        all_keywords = list(seed_keywords)
        keyword_volumes = {}

        # Step 1: Get related keywords from Google Trends suggestions
        for seed in seed_keywords:
            try:
                suggestions = _pytrends_suggestions(self.pytrends, seed)
                for s in suggestions:
                    kw = s.get("title", "").lower().strip()
                    if kw and kw not in all_keywords:
                        all_keywords.append(kw)
            except Exception as e:
                logger.warning(f"Failed to get suggestions for '{seed}': {e}")

        # Step 2: Get relative volumes via interest_over_time (batches of 5)
        for i in range(0, len(all_keywords), 5):
            batch = all_keywords[i : i + 5]
            try:
                df = _pytrends_interest_over_time(self.pytrends, batch, country.upper())
                if not df.empty:
                    for kw in batch:
                        if kw in df.columns:
                            keyword_volumes[kw] = int(df[kw].mean())
            except Exception as e:
                logger.warning(f"Failed to get volume for batch {batch}: {e}")
                for kw in batch:
                    keyword_volumes[kw] = 0

        # Fill missing volumes
        for kw in all_keywords:
            if kw not in keyword_volumes:
                keyword_volumes[kw] = 0

        # Step 3: Cluster keywords using TF-IDF + Agglomerative Clustering
        clusters = self._cluster_keywords(all_keywords)

        # Build results
        results = []
        for kw in all_keywords:
            cluster_label = ""
            related = []
            for label, members in clusters.items():
                if kw in members:
                    cluster_label = label
                    related = [m for m in members if m != kw][:5]
                    break

            results.append(
                {
                    "keyword": kw,
                    "relative_volume": keyword_volumes.get(kw, 0),
                    "cluster": cluster_label,
                    "related_keywords": related,
                }
            )

        # Sort by volume descending
        results.sort(key=lambda x: cast(float, x["relative_volume"]), reverse=True)

        return {
            "keywords": results,
            "clusters": {k: v for k, v in clusters.items()},
            "meta": {
                "seed_keywords": seed_keywords,
                "total_keywords": len(results),
                "total_clusters": len(clusters),
                "country": country,
                "language": language,
                "note": "Volumes are relative indices (0-100) from Google Trends, not absolute search counts.",
            },
        }

    def _cluster_keywords(self, keywords: list[str], n_clusters: int | None = None) -> dict:
        """Cluster keywords using TF-IDF vectors + agglomerative clustering."""
        if len(keywords) < 2:
            return {"cluster_0": keywords}

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        try:
            tfidf_matrix = vectorizer.fit_transform(keywords)
        except ValueError:
            return {"cluster_0": keywords}

        # Auto-determine number of clusters
        if n_clusters is None:
            n_clusters = max(2, min(len(keywords) // 3, 10))

        n_clusters = min(n_clusters, len(keywords))

        clustering = AgglomerativeClustering(
            n_clusters=n_clusters, metric="cosine", linkage="average"
        )
        labels = clustering.fit_predict(tfidf_matrix.toarray())

        clusters = defaultdict(list)
        for kw, label in zip(keywords, labels):
            clusters[f"cluster_{label}"].append(kw)

        # Rename clusters using most representative keyword (highest TF-IDF norm)
        named_clusters = {}
        for label, members in clusters.items():
            # Use the keyword with highest volume or first seed as label
            representative = members[0]
            named_clusters[representative] = members

        return named_clusters

    def extract_keywords_from_text(self, text: str, top_n: int = 10) -> list[dict]:
        """Extract keywords from a text block using KeyBERT with CountVectorizer."""
        vectorizer = CountVectorizer(ngram_range=(1, 3), stop_words=None)
        try:
            keywords = self.kw_model.extract_keywords(
                text,
                vectorizer=vectorizer,
                top_n=top_n,
                use_mmr=True,
                diversity=0.5,
            )
            return [{"keyword": kw, "score": round(score, 4)} for kw, score in keywords]
        except Exception as e:
            logger.warning(f"KeyBERT extraction failed: {e}")
            return []
