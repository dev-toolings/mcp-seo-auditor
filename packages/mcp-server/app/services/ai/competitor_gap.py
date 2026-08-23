"""Competitor gap analysis service."""

import asyncio
import logging
from typing import cast
from urllib.parse import urlparse

from app.services.ai.ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


class CompetitorGapService:
    """Analyzes competitive gaps in SEO coverage."""

    def __init__(
        self,
        sitemap_parser,
        ai_analyzer: AIAnalyzer,
        competitor_analyzer=None,
        trend_analysis=None,
    ):
        self.sitemap_parser = sitemap_parser
        self.ai = ai_analyzer
        self.competitor_analyzer = competitor_analyzer
        self.trend_analysis = trend_analysis

    async def analyze(
        self,
        sitemap_url: str,
        competitor_urls: list[str] | None = None,
        keywords: list[str] | None = None,
    ) -> dict:
        """Analyze competitive gaps.

        1. Get own site data from sitemap
        2. If keywords provided: run competitor analysis + trend analysis
        3. Compare coverage, identify gaps
        4. If LLM: strategic interpretation
        """
        competitor_urls = competitor_urls or []
        keywords = keywords or []

        # 1. Parse own sitemap
        try:
            sitemap_data = await self.sitemap_parser.fetch_and_parse(sitemap_url)
            own_urls = [u.loc for u in sitemap_data.urls]
        except Exception as e:
            return {"error": f"Failed to parse sitemap: {e}"}

        own_domain = urlparse(sitemap_url).netloc
        own_paths = set()
        for url in own_urls:
            parsed = urlparse(url)
            own_paths.add(parsed.path.strip("/").lower())

        # 2. Gather competitive intelligence
        competitor_data: dict = {}
        trend_data: dict = {}

        if keywords:
            results = await asyncio.gather(
                self._gather_competitor_intelligence(keywords),
                self._gather_trend_data(keywords),
                return_exceptions=True,
            )
            competitor_data = (
                cast(dict, results[0]) if not isinstance(results[0], Exception) else {}
            )
            trend_data = cast(dict, results[1]) if not isinstance(results[1], Exception) else {}

        # 3. Analyze competitor URLs if provided
        competitor_analysis = []
        for comp_url in competitor_urls[:5]:
            try:
                comp_sitemap = await self.sitemap_parser.fetch_and_parse(comp_url)
                comp_urls = [u.loc for u in comp_sitemap.urls]
                comp_domain = urlparse(comp_url).netloc
                comp_paths = set()
                for url in comp_urls:
                    parsed = urlparse(url)
                    comp_paths.add(parsed.path.strip("/").lower())

                # Find gaps
                competitor_only = comp_paths - own_paths
                own_only = own_paths - comp_paths

                competitor_analysis.append(
                    {
                        "competitor": comp_domain,
                        "total_urls": len(comp_urls),
                        "unique_to_competitor": len(competitor_only),
                        "unique_to_us": len(own_only),
                        "sample_gaps": list(competitor_only)[:10],
                    }
                )
            except Exception as e:
                competitor_analysis.append(
                    {
                        "competitor": comp_url,
                        "error": str(e),
                    }
                )

        # 4. Build gap analysis
        gap_analysis = {
            "own_site": {
                "domain": own_domain,
                "total_urls": len(own_urls),
            },
            "competitors": competitor_analysis,
            "keyword_intelligence": competitor_data if isinstance(competitor_data, dict) else {},
            "trend_data": trend_data if isinstance(trend_data, dict) else {},
        }

        # 5. Identify opportunities and threats
        opportunities = self._identify_opportunities(gap_analysis)
        threats = self._identify_threats(gap_analysis)

        result = {
            "own_site": gap_analysis["own_site"],
            "competitors_analyzed": len(competitor_analysis),
            "competitors": competitor_analysis,
            "keyword_intelligence": gap_analysis["keyword_intelligence"],
            "trend_summary": gap_analysis["trend_data"],
            "opportunities": opportunities,
            "threats": threats,
            "recommended_actions": self._build_recommendations(opportunities, threats),
            "ai_enhanced": False,
        }

        # 6. LLM enrichment
        if self.ai.ai_available:
            try:
                enrichment = await self.ai.analyze_audit(
                    {
                        "type": "competitor_gap_analysis",
                        **result,
                    }
                )
                if isinstance(enrichment, dict):
                    result["strategic_insights"] = enrichment.get("strategic_insights", [])
                    result["ai_enhanced"] = enrichment.get("ai_enhanced", False)
            except Exception as e:
                logger.warning("LLM competitor gap enrichment failed: %s", e)

        return result

    async def _gather_competitor_intelligence(self, keywords: list[str]) -> dict:
        """Run competitor analysis for given keywords."""
        if not self.competitor_analyzer:
            return {}
        try:
            return await asyncio.to_thread(self.competitor_analyzer.analyze, keywords)
        except Exception as e:
            logger.warning("Competitor intelligence failed: %s", e)
            return {}

    async def _gather_trend_data(self, keywords: list[str]) -> dict:
        """Analyze keyword trends."""
        if not self.trend_analysis:
            return {}
        try:
            return await asyncio.to_thread(self.trend_analysis.analyze, keywords)
        except Exception as e:
            logger.warning("Trend data gathering failed: %s", e)
            return {}

    def _identify_opportunities(self, gap_analysis: dict) -> list[dict]:
        """Identify content and keyword opportunities."""
        opportunities = []

        # Content gaps from competitor sitemaps
        for comp in gap_analysis.get("competitors", []):
            if comp.get("error"):
                continue
            unique_pages = comp.get("unique_to_competitor", 0)
            if unique_pages > 0:
                opportunities.append(
                    {
                        "type": "content_gap",
                        "source": comp.get("competitor", ""),
                        "description": f"Competitor has {unique_pages} pages we don't cover.",
                        "sample_paths": comp.get("sample_gaps", [])[:5],
                        "impact": "high" if unique_pages > 20 else "medium",
                    }
                )

        # Keyword opportunities from market research
        kw_data = gap_analysis.get("keyword_intelligence", {})
        for comp in kw_data.get("competitors", []):
            if isinstance(comp, dict) and comp.get("visibility_score", 0) > 70:
                opportunities.append(
                    {
                        "type": "keyword_opportunity",
                        "source": comp.get("domain", ""),
                        "description": f"High-visibility competitor ({comp.get('visibility_score', 0)}%) - analyze their keyword strategy.",
                        "impact": "high",
                    }
                )

        # Trend-based opportunities
        trends = gap_analysis.get("trend_data", {})
        for kw, data in trends.items() if isinstance(trends, dict) else []:
            if isinstance(data, dict) and data.get("trend_direction") == "rising":
                opportunities.append(
                    {
                        "type": "trending_keyword",
                        "keyword": kw,
                        "description": f"Keyword '{kw}' is trending upward - opportunity to create content.",
                        "impact": "medium",
                    }
                )

        return opportunities

    def _identify_threats(self, gap_analysis: dict) -> list[dict]:
        """Identify competitive threats."""
        threats = []

        for comp in gap_analysis.get("competitors", []):
            if comp.get("error"):
                continue

            # Threat: competitor has significantly more content
            own_total = gap_analysis.get("own_site", {}).get("total_urls", 0)
            comp_total = comp.get("total_urls", 0)
            if comp_total > own_total * 2:
                threats.append(
                    {
                        "type": "content_volume",
                        "competitor": comp.get("competitor", ""),
                        "description": f"Competitor has {comp_total} pages vs our {own_total}.",
                        "severity": "high",
                    }
                )

            # Threat: losing unique differentiators
            own_only = comp.get("unique_to_us", 0)
            if own_only < 5:
                threats.append(
                    {
                        "type": "low_differentiation",
                        "competitor": comp.get("competitor", ""),
                        "description": "Very few unique pages compared to competitor - risk of losing traffic.",
                        "severity": "medium",
                    }
                )

        return threats

    def _build_recommendations(self, opportunities: list[dict], threats: list[dict]) -> list[dict]:
        """Build actionable recommendations from opportunities and threats."""
        recommendations = []

        # Content gap recommendations
        content_gaps = [o for o in opportunities if o.get("type") == "content_gap"]
        if content_gaps:
            total_gaps = sum(len(g.get("sample_paths", [])) for g in content_gaps)
            recommendations.append(
                {
                    "action": "Create content for identified gaps",
                    "description": f"Found {total_gaps}+ content topics covered by competitors but not by your site.",
                    "priority": "high",
                    "effort": "high",
                    "timeline": "medium-term",
                }
            )

        # Trending keyword recommendations
        trending = [o for o in opportunities if o.get("type") == "trending_keyword"]
        if trending:
            recommendations.append(
                {
                    "action": "Target trending keywords",
                    "description": f"{len(trending)} keywords are trending upward and present growth opportunities.",
                    "priority": "medium",
                    "effort": "medium",
                    "timeline": "short-term",
                }
            )

        # Threat mitigation
        volume_threats = [t for t in threats if t.get("type") == "content_volume"]
        if volume_threats:
            recommendations.append(
                {
                    "action": "Scale content production",
                    "description": "Competitors have significantly more content. Prioritize quality-focused content expansion.",
                    "priority": "high",
                    "effort": "high",
                    "timeline": "long-term",
                }
            )

        if not recommendations:
            recommendations.append(
                {
                    "action": "Continue monitoring competitive landscape",
                    "description": "No critical gaps identified. Maintain current strategy and monitor regularly.",
                    "priority": "low",
                    "effort": "minimal",
                    "timeline": "ongoing",
                }
            )

        return recommendations
