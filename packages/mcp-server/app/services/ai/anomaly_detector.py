"""Anomaly detection service for SEO monitoring."""

import logging
import math

from app.services.ai.ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


class AnomalyDetectorService:
    """Monitors keyword trends and detects anomalies using statistical analysis."""

    # Z-score threshold for anomaly detection
    Z_THRESHOLD = 2.0

    def __init__(self, gsc, ai_analyzer: AIAnalyzer, crawl_repository=None):
        self.gsc = gsc
        self.ai = ai_analyzer
        self.repo = crawl_repository

    async def detect(
        self, keywords: list[str], days_back: int = 28, site_url: str | None = None
    ) -> dict:
        """Monitor keywords and detect anomalies.

        1. Get trend data for keywords
        2. Statistical analysis: z-scores, moving averages
        3. Detect anomalies (significant deviations from trend)
        4. If GSC available: check performance anomalies
        5. If LLM: root cause hypothesis + recommended actions
        6. If no LLM: threshold-based alerts
        """
        if not keywords:
            return {"error": "No keywords provided", "anomalies": [], "alerts": []}

        # 1. Get trend data from rank tracking if available
        trend_data = {}
        if self.repo and site_url:
            try:
                for kw in keywords:
                    history = await self.repo.get_position_history(site_url, kw, days_back)
                    if history:
                        values = [h["position"] for h in history if h.get("position") is not None]
                        if values:
                            trend_data[kw] = values
            except Exception as e:
                logger.warning("Failed to fetch rank history: %s", e)

        # 2. Get GSC data if available (requires site_url)
        gsc_data = {}
        if site_url:
            try:
                gsc_perf = await self.gsc.get_performance(days=days_back, site_url=site_url)
                if not gsc_perf.get("error"):
                    gsc_data = gsc_perf
            except Exception as e:
                logger.warning("GSC data fetch failed: %s", e)

        # 3. Analyze trends for anomalies
        anomalies = []
        trend_summary = {}

        for keyword in keywords:
            kw_trend = self._extract_keyword_trend(trend_data, keyword)
            if kw_trend:
                kw_anomalies = self._detect_statistical_anomalies(keyword, kw_trend)
                anomalies.extend(kw_anomalies)
                trend_summary[keyword] = self._summarize_trend(kw_trend)
            else:
                trend_summary[keyword] = {
                    "status": "no_data",
                    "message": "No trend data available for this keyword.",
                }

        # 4. Check GSC performance anomalies
        gsc_anomalies = self._detect_gsc_anomalies(gsc_data) if gsc_data else []
        anomalies.extend(gsc_anomalies)

        # 5. Generate alerts
        alerts = self._generate_alerts(anomalies)

        result = {
            "keywords_monitored": len(keywords),
            "days_analyzed": days_back,
            "anomalies": anomalies,
            "alerts": alerts,
            "trend_summary": trend_summary,
            "gsc_available": bool(gsc_data),
            "ai_enhanced": False,
        }

        # 6. LLM enrichment
        if self.ai.ai_available and anomalies:
            try:
                enrichment = await self.ai.analyze_anomalies(
                    {
                        "type": "anomaly_detection",
                        "anomalies": anomalies,
                        "trend_summary": trend_summary,
                        "gsc_data_available": bool(gsc_data),
                    }
                )
                if isinstance(enrichment, dict):
                    result["root_cause_hypotheses"] = enrichment.get("root_cause_hypotheses", [])
                    result["recommended_actions"] = enrichment.get("recommended_actions", [])
                    result["ai_enhanced"] = enrichment.get("ai_enhanced", False)
            except Exception as e:
                logger.warning("LLM anomaly enrichment failed: %s", e)

        return result

    def _extract_keyword_trend(self, trend_data: dict, keyword: str) -> list[float]:
        """Extract trend values for a specific keyword from trend data."""
        if not trend_data or not isinstance(trend_data, dict):
            return []

        # Handle different trend data formats
        # Format 1: direct keyword -> values mapping
        if keyword in trend_data:
            values = trend_data[keyword]
            if isinstance(values, list):
                return [float(v) for v in values if v is not None]
            if isinstance(values, dict):
                return [float(v) for v in values.get("values", []) if v is not None]

        # Format 2: nested results structure
        results = trend_data.get("results", {})
        if isinstance(results, dict) and keyword in results:
            kw_data = results[keyword]
            if isinstance(kw_data, dict):
                return [float(v) for v in kw_data.get("values", []) if v is not None]
            if isinstance(kw_data, list):
                return [float(v) for v in kw_data if v is not None]

        # Format 3: keywords array
        for kw_entry in trend_data.get("keywords", []):
            if isinstance(kw_entry, dict) and kw_entry.get("keyword") == keyword:
                return [float(v) for v in kw_entry.get("values", []) if v is not None]

        return []

    def _detect_statistical_anomalies(self, keyword: str, values: list[float]) -> list[dict]:
        """Detect anomalies using z-score analysis."""
        if len(values) < 5:
            return []

        anomalies = []
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = math.sqrt(variance) if variance > 0 else 0

        if std_dev == 0:
            return []

        for i, value in enumerate(values):
            z_score = (value - mean) / std_dev
            if abs(z_score) >= self.Z_THRESHOLD:
                direction = "spike" if z_score > 0 else "drop"
                anomalies.append(
                    {
                        "keyword": keyword,
                        "type": f"trend_{direction}",
                        "position": i,
                        "value": value,
                        "expected": round(mean, 2),
                        "z_score": round(z_score, 2),
                        "severity": "critical" if abs(z_score) >= 3 else "warning",
                        "description": f"{'Unusual spike' if direction == 'spike' else 'Significant drop'} in '{keyword}' trend (z-score: {z_score:.2f}).",
                    }
                )

        # Check for sustained decline (last 5 values trending down)
        if len(values) >= 5:
            recent = values[-5:]
            if all(recent[i] >= recent[i + 1] for i in range(len(recent) - 1)):
                decline_pct = ((recent[0] - recent[-1]) / max(recent[0], 1)) * 100
                if decline_pct > 20:
                    anomalies.append(
                        {
                            "keyword": keyword,
                            "type": "sustained_decline",
                            "decline_percentage": round(decline_pct, 1),
                            "severity": "critical" if decline_pct > 50 else "warning",
                            "description": f"Sustained decline of {decline_pct:.1f}% in '{keyword}' over recent period.",
                        }
                    )

        return anomalies

    def _summarize_trend(self, values: list[float]) -> dict:
        """Compute summary statistics for a trend series."""
        if not values:
            return {"status": "no_data"}

        mean = sum(values) / len(values)
        current = values[-1]
        change = ((current - values[0]) / max(values[0], 1)) * 100 if len(values) > 1 else 0

        # Moving average (last 7 points)
        window = min(7, len(values))
        moving_avg = sum(values[-window:]) / window

        # Determine direction
        if change > 10:
            direction = "rising"
        elif change < -10:
            direction = "declining"
        else:
            direction = "stable"

        return {
            "status": "active",
            "current_value": round(current, 2),
            "mean": round(mean, 2),
            "moving_average": round(moving_avg, 2),
            "change_percentage": round(change, 1),
            "direction": direction,
            "data_points": len(values),
        }

    def _detect_gsc_anomalies(self, gsc_data: dict) -> list[dict]:
        """Detect anomalies in Google Search Console data."""
        anomalies = []

        # Check for significant CTR drops
        ctr = gsc_data.get("ctr")
        if isinstance(ctr, (int, float)) and ctr < 0.02:
            anomalies.append(
                {
                    "keyword": "_site_wide",
                    "type": "low_ctr",
                    "value": round(ctr * 100, 2),
                    "severity": "warning",
                    "description": f"Site-wide CTR is very low ({ctr * 100:.2f}%). Meta titles and descriptions may need improvement.",
                }
            )

        # Check for position drops
        avg_position = gsc_data.get("average_position")
        if isinstance(avg_position, (int, float)) and avg_position > 30:
            anomalies.append(
                {
                    "keyword": "_site_wide",
                    "type": "poor_position",
                    "value": round(avg_position, 1),
                    "severity": "warning",
                    "description": f"Average position is {avg_position:.1f}. Most pages are beyond page 3.",
                }
            )

        return anomalies

    def _generate_alerts(self, anomalies: list[dict]) -> list[dict]:
        """Generate user-friendly alerts from anomalies."""
        alerts = []

        critical = [a for a in anomalies if a.get("severity") == "critical"]
        warnings = [a for a in anomalies if a.get("severity") == "warning"]

        if critical:
            alerts.append(
                {
                    "level": "critical",
                    "count": len(critical),
                    "message": f"{len(critical)} critical anomalies detected requiring immediate attention.",
                    "details": [a.get("description", "") for a in critical],
                }
            )

        if warnings:
            alerts.append(
                {
                    "level": "warning",
                    "count": len(warnings),
                    "message": f"{len(warnings)} warnings detected. Monitor closely.",
                    "details": [a.get("description", "") for a in warnings[:5]],
                }
            )

        if not anomalies:
            alerts.append(
                {
                    "level": "info",
                    "count": 0,
                    "message": "No anomalies detected. All monitored keywords are within normal ranges.",
                    "details": [],
                }
            )

        return alerts
