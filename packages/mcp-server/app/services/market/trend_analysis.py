"""Trend analysis service using Google Trends (pytrends)."""

import logging

import numpy as np
from pytrends.request import TrendReq

from app.services.market._rate_limiter import rate_limit_pytrends as _rate_limit_pytrends

logger = logging.getLogger(__name__)


class TrendAnalysisService:
    """Analyze keyword trends using Google Trends."""

    def __init__(self, hl: str = "fr", tz: int = 60):
        self.pytrends = TrendReq(hl=hl, tz=tz)

    def analyze(
        self,
        keywords: list[str],
        timeframe: str = "today 12-m",
        geo: str = "FR",
    ) -> dict:
        """Analyze trends for a list of keywords.

        Returns:
            dict with keys: trends (list of TrendData), related_queries (dict), meta (dict)
        """
        trends = []

        # Process in batches of 5 (Google Trends limit)
        for i in range(0, len(keywords), 5):
            batch = keywords[i : i + 5]
            batch_trends = self._analyze_batch(batch, timeframe, geo)
            trends.extend(batch_trends)

        # Get related queries for each keyword
        related = {}
        for kw in keywords:
            try:
                _rate_limit_pytrends()
                self.pytrends.build_payload([kw], geo=geo, timeframe=timeframe)
                rq = self.pytrends.related_queries()
                if kw in rq and rq[kw] is not None:
                    top = rq[kw].get("top")
                    rising = rq[kw].get("rising")
                    related[kw] = {
                        "top": (
                            top[["query", "value"]].to_dict("records")[:10]
                            if top is not None and not top.empty
                            else []
                        ),
                        "rising": (
                            rising[["query", "value"]].to_dict("records")[:10]
                            if rising is not None and not rising.empty
                            else []
                        ),
                    }
            except Exception as e:
                logger.warning(f"Failed to get related queries for '{kw}': {e}")
                related[kw] = {"top": [], "rising": []}

        return {
            "trends": trends,
            "related_queries": related,
            "meta": {
                "keywords": keywords,
                "timeframe": timeframe,
                "geo": geo,
                "note": "Trend values are relative indices (0-100). Growth rate is computed via linear regression.",
            },
        }

    def _analyze_batch(self, keywords: list[str], timeframe: str, geo: str) -> list[dict]:
        """Analyze a batch of up to 5 keywords."""
        results = []

        try:
            _rate_limit_pytrends()
            self.pytrends.build_payload(keywords, geo=geo, timeframe=timeframe)
            df = self.pytrends.interest_over_time()

            if df.empty:
                for kw in keywords:
                    results.append(self._empty_trend(kw))
                return results

            for kw in keywords:
                if kw not in df.columns:
                    results.append(self._empty_trend(kw))
                    continue

                values = df[kw].tolist()
                growth_rate = self._compute_growth_rate(values)
                is_seasonal = self._detect_seasonality(values)
                direction = self._determine_direction(growth_rate)

                results.append(
                    {
                        "keyword": kw,
                        "trend_values": values,
                        "growth_rate": round(growth_rate, 2),
                        "is_seasonal": is_seasonal,
                        "direction": direction,
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to analyze batch {keywords}: {e}")
            for kw in keywords:
                results.append(self._empty_trend(kw))

        return results

    @staticmethod
    def _compute_growth_rate(values: list[int]) -> float:
        """Compute annual growth rate using linear regression."""
        if len(values) < 4:
            return 0.0

        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)

        # Avoid division by zero
        mean_y = np.mean(y)
        if mean_y == 0:
            return 0.0

        # Simple linear regression: slope
        n = len(x)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)

        # Annualize: slope * 52 weeks / mean_value * 100
        annual_growth = (slope * 52 / mean_y) * 100
        return float(annual_growth)

    @staticmethod
    def _detect_seasonality(values: list[int], threshold: float = 0.35) -> bool:
        """Detect seasonality by comparing monthly standard deviation to mean."""
        if len(values) < 12:
            return False

        arr = np.array(values, dtype=float)
        mean = np.mean(arr)
        if mean == 0:
            return False

        # Group by ~4 week periods (months)
        monthly = []
        for i in range(0, len(arr), 4):
            chunk = arr[i : i + 4]
            if len(chunk) > 0:
                monthly.append(np.mean(chunk))

        if len(monthly) < 4:
            return False

        monthly_arr = np.array(monthly)
        cv = np.std(monthly_arr) / np.mean(monthly_arr)
        return float(cv) > threshold

    @staticmethod
    def _determine_direction(growth_rate: float) -> str:
        """Determine trend direction from growth rate."""
        if growth_rate > 15:
            return "up"
        elif growth_rate < -15:
            return "down"
        return "stable"

    @staticmethod
    def _empty_trend(keyword: str) -> dict:
        return {
            "keyword": keyword,
            "trend_values": [],
            "growth_rate": 0.0,
            "is_seasonal": False,
            "direction": "stable",
        }
