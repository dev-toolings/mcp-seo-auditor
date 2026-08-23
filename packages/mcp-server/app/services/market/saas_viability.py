"""SaaS viability assessment service orchestrating all market intelligence tools."""

import logging

from app.core.scoring import (
    SAAS_DIMENSION_WEIGHTS,
    SAAS_RECOMMENDATION_THRESHOLDS,
    SAAS_VERDICT_THRESHOLDS,
)
from app.services.market.competitor_analyzer import CompetitorAnalyzerService
from app.services.market.github_analyzer import GitHubAnalyzerService
from app.services.market.keyword_research import KeywordResearchService
from app.services.market.niche_finder import NicheFinderService
from app.services.market.trend_analysis import TrendAnalysisService

logger = logging.getLogger(__name__)


class SaaSViabilityService:
    """Orchestrate all market services to produce a SaaS viability score."""

    def __init__(self):
        self.keyword_service = KeywordResearchService()
        self.trend_service = TrendAnalysisService()
        self.competitor_service = CompetitorAnalyzerService()
        self.niche_service = NicheFinderService()
        self.github_service = GitHubAnalyzerService()

    async def assess(
        self,
        concept: str,
        target_keywords: list[str],
        market_type: str = "B2B",
        geo: str = "FR",
    ) -> dict:
        """Run a full SaaS viability assessment.

        Scoring (0-100):
        - Demand (30%): relative volume from Google Trends
        - Growth (25%): annual growth rate
        - Competition (25%): inverse of competitor density
        - Open-source (20%): inverse of active GitHub repos

        Verdict:
        - Go: 70+
        - Explore: 40-69
        - No-Go: <40

        Returns:
            dict matching ViabilityReport schema
        """
        # Run keyword research
        keyword_data = self.keyword_service.research(
            seed_keywords=target_keywords, country=geo.lower()
        )

        # Run trend analysis
        trend_data = self.trend_service.analyze(keywords=target_keywords, geo=geo)

        # Run competitor analysis
        competitor_data = self.competitor_service.analyze(keywords=target_keywords, geo=geo)

        # Run GitHub analysis
        github_data = await self.github_service.analyze(concept=concept)

        # === Score each dimension ===

        # 1. Demand score (0-100): average relative volume of target keywords
        demand_score = self._score_demand(keyword_data)

        # 2. Growth score (0-100): based on trend growth rates
        growth_score = self._score_growth(trend_data)

        # 3. Competition score (0-100): inverse of competitor presence
        competition_score = self._score_competition(competitor_data)

        # 4. Open-source score (0-100): inverse of GitHub activity
        opensource_score = self._score_opensource(github_data)

        # Weighted final score
        final_score = (
            demand_score * SAAS_DIMENSION_WEIGHTS["demand"]
            + growth_score * SAAS_DIMENSION_WEIGHTS["growth"]
            + competition_score * SAAS_DIMENSION_WEIGHTS["competition"]
            + opensource_score * SAAS_DIMENSION_WEIGHTS["opensource"]
        )

        # Verdict
        if final_score >= SAAS_VERDICT_THRESHOLDS["go"]:
            verdict = "go"
        elif final_score >= SAAS_VERDICT_THRESHOLDS["explore"]:
            verdict = "explore"
        else:
            verdict = "no-go"

        # Build dimensions
        dimensions = [
            {
                "name": "demand",
                "score": round(demand_score, 1),
                "weight": SAAS_DIMENSION_WEIGHTS["demand"],
                "detail": f"Average relative search volume: {demand_score:.0f}/100",
            },
            {
                "name": "growth",
                "score": round(growth_score, 1),
                "weight": SAAS_DIMENSION_WEIGHTS["growth"],
                "detail": self._growth_detail(trend_data),
            },
            {
                "name": "competition",
                "score": round(competition_score, 1),
                "weight": SAAS_DIMENSION_WEIGHTS["competition"],
                "detail": f"{competitor_data.get('market_overview', {}).get('total_competitors', 0)} competitors found, market {competitor_data.get('market_overview', {}).get('concentration', 'unknown')}",
            },
            {
                "name": "open_source",
                "score": round(opensource_score, 1),
                "weight": SAAS_DIMENSION_WEIGHTS["opensource"],
                "detail": f"{github_data.get('total_repos', 0)} repos, {github_data.get('total_stars', 0)} total stars",
            },
        ]

        # Recommendations
        recommendations = self._generate_recommendations(
            verdict, demand_score, growth_score, competition_score, opensource_score, market_type
        )

        # Build keyword insights (top 10)
        keyword_insights = keyword_data.get("keywords", [])[:10]

        # Build trend insights
        trend_insights = trend_data.get("trends", [])

        # Build competitor insights
        competitor_insights = competitor_data.get("competitors", [])[:5]

        return {
            "score": round(final_score, 1),
            "verdict": verdict,
            "market_type": market_type,
            "dimensions": dimensions,
            "recommendations": recommendations,
            "keyword_insights": keyword_insights,
            "trend_insights": trend_insights,
            "competitor_insights": competitor_insights,
            "github_signal": github_data,
        }

    @staticmethod
    def _score_demand(keyword_data: dict) -> float:
        """Score demand from keyword volumes."""
        keywords = keyword_data.get("keywords", [])
        if not keywords:
            return 0.0

        volumes = [kw.get("relative_volume", 0) for kw in keywords]
        avg = sum(volumes) / len(volumes)
        return min(avg, 100.0)

    @staticmethod
    def _score_growth(trend_data: dict) -> float:
        """Score growth from trend data. Positive growth = higher score."""
        trends = trend_data.get("trends", [])
        if not trends:
            return 50.0  # neutral

        growth_rates = [t.get("growth_rate", 0) for t in trends]
        avg_growth = sum(growth_rates) / len(growth_rates)

        # Map growth rate to 0-100 score
        # -50% or worse -> 0, 0% -> 50, +50% or better -> 100
        score = 50 + avg_growth
        return max(0.0, min(100.0, score))

    @staticmethod
    def _score_competition(competitor_data: dict) -> float:
        """Score competition (inverse: fewer strong competitors = higher score)."""
        competitors = competitor_data.get("competitors", [])
        n = len(competitors)

        if n == 0:
            return 90.0  # No competitors = great opportunity (but maybe no market)

        # Strong competitors: those with relative_interest > 50
        strong = sum(1 for c in competitors if c.get("relative_interest", 0) > 50)

        concentration = competitor_data.get("market_overview", {}).get("concentration", "unknown")

        if concentration == "monopolistic":
            return 15.0
        elif concentration == "concentrated":
            return 30.0
        elif concentration == "oligopolistic":
            return 45.0

        # Fragmented market: score inversely to number of strong competitors
        base = 70.0
        penalty = strong * 10
        return max(10.0, base - penalty)

    @staticmethod
    def _score_opensource(github_data: dict) -> float:
        """Score open-source competition (inverse: more active repos = lower score)."""
        total_repos = github_data.get("total_repos", 0)
        total_stars = github_data.get("total_stars", 0)
        activity = github_data.get("avg_recent_activity", 0)

        if total_repos == 0:
            return 95.0  # No open-source alternatives

        # Penalize based on number of repos and stars
        repo_penalty = min(total_repos / 100, 1.0) * 30
        star_penalty = min(total_stars / 10000, 1.0) * 30
        activity_penalty = min(activity / 100, 1.0) * 20

        score = 95.0 - repo_penalty - star_penalty - activity_penalty
        return max(5.0, score)

    @staticmethod
    def _growth_detail(trend_data: dict) -> str:
        """Generate growth detail text."""
        trends = trend_data.get("trends", [])
        if not trends:
            return "No trend data available"

        directions = [t.get("direction", "stable") for t in trends]
        up = directions.count("up")
        down = directions.count("down")
        stable = directions.count("stable")

        parts = []
        if up:
            parts.append(f"{up} keyword(s) trending up")
        if stable:
            parts.append(f"{stable} stable")
        if down:
            parts.append(f"{down} declining")

        return ", ".join(parts)

    @staticmethod
    def _generate_recommendations(
        verdict: str,
        demand: float,
        growth: float,
        competition: float,
        opensource: float,
        market_type: str,
    ) -> list[str]:
        """Generate strategic recommendations based on scores."""
        recs = []

        if verdict == "go":
            recs.append("Market conditions are favorable. Consider validating with a MVP.")
        elif verdict == "explore":
            recs.append("Market shows potential but requires further validation before committing.")
        else:
            recs.append("Market conditions are challenging. Consider pivoting or finding a niche.")

        if demand < SAAS_RECOMMENDATION_THRESHOLDS["low_demand"]:
            recs.append(
                "Low search demand: validate that the problem exists through direct user interviews."
            )
        elif demand > SAAS_RECOMMENDATION_THRESHOLDS["high_demand"]:
            recs.append("Strong search demand confirms market interest.")

        if growth > SAAS_RECOMMENDATION_THRESHOLDS["high_growth"]:
            recs.append("Growing market: timing is favorable for entry.")
        elif growth < SAAS_RECOMMENDATION_THRESHOLDS["low_growth"]:
            recs.append(
                "Declining interest: evaluate if the market is shrinking or shifting to new terminology."
            )

        if competition < SAAS_RECOMMENDATION_THRESHOLDS["high_competition"]:
            recs.append(
                "High competition from established players. Differentiation is critical. Focus on an underserved niche."
            )
        elif competition > SAAS_RECOMMENDATION_THRESHOLDS["high_demand"]:
            recs.append(
                "Low competition landscape. Validate that there is genuine demand (not just a lack of interest)."
            )

        if opensource < SAAS_RECOMMENDATION_THRESHOLDS["low_opensource"]:
            recs.append(
                "Strong open-source alternatives exist. Your SaaS must offer clear value above self-hosted options (support, integrations, ease of use)."
            )

        if market_type == "marketplace":
            recs.append(
                "For marketplace models, focus on solving the chicken-and-egg problem: which side do you attract first?"
            )
        elif market_type == "B2B":
            recs.append(
                "For B2B, focus on a specific vertical first to build credibility and case studies."
            )

        return recs
