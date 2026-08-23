"""GSC Volume Calibration — estimate absolute search volumes from GSC + pytrends.

Cross-references real GSC impression data with pytrends relative indices
to extrapolate absolute search volume estimates for any keyword.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VolumeCalibratorService:
    """Calibrate keyword volumes using GSC impressions and pytrends indices."""

    def __init__(self, gsc_service=None, trend_service=None):
        self.gsc = gsc_service
        self.trends = trend_service

    async def calibrate(
        self,
        site_url: str,
        target_keywords: list[str],
        days: int = 28,
        geo: str = "FR",
    ) -> dict[str, Any]:
        """Estimate absolute volumes by calibrating pytrends with GSC data.

        Method:
        1. Get GSC impressions for the site's queries (known data points)
        2. Get pytrends indices for those same queries (relative 0-100)
        3. Build a calibration ratio: impressions / pytrends_index
        4. Apply ratio to target keywords' pytrends indices

        Limitations:
        - Only accurate for queries where the site has GSC visibility
        - Pytrends indices are relative and noisy
        - Best used as directional estimates, not exact volumes
        """
        if not self.gsc or not self.gsc.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        # 1. Get top queries from GSC (these are our calibration data points)
        gsc_queries = await self.gsc.get_top_queries(days=days, limit=100, site_url=site_url)
        if not gsc_queries:
            return {
                "error": "No GSC query data available for calibration",
                "suggestion": "Site needs sufficient organic visibility for calibration",
            }

        # Build calibration map: query -> impressions
        gsc_map = {q.query.lower(): q.impressions for q in gsc_queries}

        # 2. Get pytrends data for calibration queries
        # Pick top 5 GSC queries as calibration anchors (pytrends allows max 5)
        calibration_queries = sorted(gsc_map.items(), key=lambda x: x[1], reverse=True)[:5]
        calibration_keywords = [q[0] for q in calibration_queries]

        if not self.trends or not calibration_keywords:
            return {
                "error": "Trend analysis service not available",
                "gsc_data": {
                    "query_count": len(gsc_map),
                    "top_queries": [
                        {"query": q, "impressions": imp} for q, imp in calibration_queries
                    ],
                },
            }

        # 3. Get pytrends indices for calibration keywords + targets
        # Process in batches of 5 (pytrends limit)
        all_keywords = list(set(calibration_keywords + target_keywords))

        trends_data = {}
        for i in range(0, len(all_keywords), 5):
            batch = all_keywords[i : i + 5]
            try:
                batch_result = await self.trends.get_interest(keywords=batch, geo=geo)
                if isinstance(batch_result, dict):
                    for kw, data in batch_result.items():
                        if isinstance(data, dict) and "average" in data:
                            trends_data[kw.lower()] = data["average"]
                        elif isinstance(data, (int, float)):
                            trends_data[kw.lower()] = data
            except Exception as e:
                logger.warning("Pytrends batch failed: %s", e)

        # 4. Calculate calibration ratio
        ratios = []
        for query, impressions in calibration_queries:
            trend_index = trends_data.get(query, 0)
            if trend_index > 0:
                ratios.append(impressions / trend_index)

        if not ratios:
            return {
                "error": "Could not calibrate — no overlap between GSC and pytrends data",
                "gsc_queries_found": len(gsc_map),
                "trends_data_found": len(trends_data),
            }

        # Use median ratio for robustness
        ratios.sort()
        median_ratio = ratios[len(ratios) // 2]

        # 5. Estimate volumes for target keywords
        estimates = []
        for keyword in target_keywords:
            kw_lower = keyword.lower()
            trend_index = trends_data.get(kw_lower, 0)
            gsc_impressions = gsc_map.get(kw_lower)

            if gsc_impressions is not None:
                # We have real data
                estimates.append(
                    {
                        "keyword": keyword,
                        "estimated_volume": gsc_impressions,
                        "source": "gsc_actual",
                        "confidence": "high",
                        "gsc_impressions": gsc_impressions,
                        "trend_index": trend_index,
                    }
                )
            elif trend_index > 0:
                # Estimate from pytrends
                estimated = int(trend_index * median_ratio)
                estimates.append(
                    {
                        "keyword": keyword,
                        "estimated_volume": estimated,
                        "source": "calibrated_estimate",
                        "confidence": "medium",
                        "trend_index": trend_index,
                        "calibration_ratio": round(median_ratio, 1),
                    }
                )
            else:
                estimates.append(
                    {
                        "keyword": keyword,
                        "estimated_volume": 0,
                        "source": "no_data",
                        "confidence": "low",
                    }
                )

        return {
            "estimates": estimates,
            "calibration": {
                "anchor_queries": len(calibration_queries),
                "calibration_ratio": round(median_ratio, 1),
                "data_points": len(ratios),
                "geo": geo,
                "period_days": days,
            },
            "limitations": (
                "Estimates are directional approximations based on the ratio "
                "between GSC impressions and pytrends indices. Accuracy depends "
                "on the site's organic visibility and pytrends data availability."
            ),
        }
