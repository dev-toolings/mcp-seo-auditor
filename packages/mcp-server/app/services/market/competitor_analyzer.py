"""Competitor analysis service using Google Trends."""

import logging
from typing import cast

import numpy as np
from pytrends.request import TrendReq

from app.services.market._rate_limiter import rate_limit_pytrends as _rate_limit_pytrends

logger = logging.getLogger(__name__)


class CompetitorAnalyzerService:
    """Identify and analyze competitors using Google Trends."""

    def __init__(self, hl: str = "fr", tz: int = 60):
        self.pytrends = TrendReq(hl=hl, tz=tz)

    def analyze(
        self,
        keywords: list[str],
        max_results: int = 10,
        geo: str = "FR",
        timeframe: str = "today 12-m",
    ) -> dict:
        """Identify competitors from keyword analysis.

        Uses related_queries and related_topics from Google Trends to detect
        brand names and competitors, then compares their relative interest.

        Returns:
            dict with keys: competitors (list), market_overview (dict), meta (dict)
        """
        # Step 1: Collect competitor names from related queries/topics
        candidate_brands = set()

        for kw in keywords:
            try:
                _rate_limit_pytrends()
                self.pytrends.build_payload([kw], geo=geo, timeframe=timeframe)

                # Related topics often contain brand names
                topics = self.pytrends.related_topics()
                if kw in topics and topics[kw] is not None:
                    top_topics = topics[kw].get("top")
                    if top_topics is not None and not top_topics.empty:
                        for _, row in top_topics.head(15).iterrows():
                            title = row.get("topic_title", "")
                            topic_type = row.get("topic_type", "")
                            # Filter for likely brand/product names
                            if topic_type in ("Software", "Company", "Website", "Product", "Brand"):
                                candidate_brands.add(title)
                            elif title and len(title.split()) <= 3:
                                candidate_brands.add(title)

                # Related queries can also reveal competitors
                queries = self.pytrends.related_queries()
                if kw in queries and queries[kw] is not None:
                    top_queries = queries[kw].get("top")
                    if top_queries is not None and not top_queries.empty:
                        for _, row in top_queries.head(10).iterrows():
                            query = row.get("query", "")
                            # Queries with brand-like patterns
                            if query and query.lower() not in [k.lower() for k in keywords]:
                                candidate_brands.add(query)

            except Exception as e:
                logger.warning(f"Failed to get related data for '{kw}': {e}")

        # Remove seed keywords from candidates
        lower_seeds = {k.lower() for k in keywords}
        candidate_brands = {b for b in candidate_brands if b.lower() not in lower_seeds}

        # Limit candidates
        candidates = list(candidate_brands)[: max_results * 2]

        if not candidates:
            return {
                "competitors": [],
                "market_overview": {"total_competitors": 0, "concentration": "unknown"},
                "meta": {"keywords": keywords, "geo": geo},
            }

        # Step 2: Compare relative interest for top candidates
        competitors = self._compare_interest(candidates, geo, timeframe, max_results)

        # Step 3: Build market overview
        total_interest = sum(c["relative_interest"] for c in competitors)
        market_overview = {
            "total_competitors": len(competitors),
            "concentration": self._assess_concentration(competitors),
            "total_relative_interest": total_interest,
        }

        return {
            "competitors": competitors,
            "market_overview": market_overview,
            "meta": {
                "keywords": keywords,
                "geo": geo,
                "timeframe": timeframe,
                "note": "Relative interest values are from Google Trends (0-100). They represent search interest, not market share.",
            },
        }

    def _compare_interest(
        self,
        candidates: list[str],
        geo: str,
        timeframe: str,
        max_results: int,
    ) -> list[dict]:
        """Compare search interest for candidate competitors."""
        competitor_data = {}

        # Query in batches of 5
        for i in range(0, len(candidates), 5):
            batch = candidates[i : i + 5]
            try:
                _rate_limit_pytrends()
                self.pytrends.build_payload(batch, geo=geo, timeframe=timeframe)
                df = self.pytrends.interest_over_time()

                if not df.empty:
                    for name in batch:
                        if name in df.columns:
                            values = df[name].tolist()
                            avg_interest = int(np.mean(values))
                            growth = self._compute_direction(values)
                            competitor_data[name] = {
                                "name": name,
                                "relative_interest": avg_interest,
                                "trend_direction": growth,
                            }
            except Exception as e:
                logger.warning(f"Failed to compare batch {batch}: {e}")

        # Sort by interest and limit
        competitors = sorted(
            competitor_data.values(),
            key=lambda x: cast(float, x["relative_interest"]),
            reverse=True,
        )[:max_results]

        return competitors

    @staticmethod
    def _compute_direction(values: list[int]) -> str:
        """Determine trend direction from a series of values."""
        if len(values) < 4:
            return "stable"

        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)

        mean_y = np.mean(y)
        if mean_y == 0:
            return "stable"

        n = len(x)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)

        growth = (slope * 52 / mean_y) * 100

        if growth > 15:
            return "up"
        elif growth < -15:
            return "down"
        return "stable"

    @staticmethod
    def _assess_concentration(competitors: list[dict]) -> str:
        """Assess market concentration."""
        if not competitors:
            return "unknown"

        interests = [c["relative_interest"] for c in competitors]
        total = sum(interests)
        if total == 0:
            return "unknown"

        # Top competitor share
        top_share = interests[0] / total if interests else 0

        if top_share > 0.6:
            return "monopolistic"
        elif top_share > 0.35:
            return "concentrated"
        elif len(competitors) <= 3:
            return "oligopolistic"
        return "fragmented"
