"""SERP feature analysis service.

Analyzes search engine result pages to detect features (featured snippets,
PAA, AI Overview, Knowledge Panel, Video carousel) and provide strategic
recommendations.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# SERP feature types we detect
SERP_FEATURES = {
    "featured_snippet": "Featured Snippet (Position 0)",
    "people_also_ask": "People Also Ask (PAA)",
    "knowledge_panel": "Knowledge Panel",
    "video_carousel": "Video Carousel",
    "image_pack": "Image Pack",
    "local_pack": "Local Pack / Map Pack",
    "top_stories": "Top Stories",
    "ai_overview": "AI Overview / SGE",
    "shopping_results": "Shopping Results",
    "sitelinks": "Sitelinks",
}


class SERPAnalyzerService:
    """Analyze SERP features and competitive landscape."""

    def __init__(self, serp_scraper=None):
        self.serp_scraper = serp_scraper

    async def analyze(
        self,
        keywords: list[str],
        engine: str = "google",
        site_domain: str | None = None,
    ) -> dict[str, Any]:
        """Analyze SERPs for given keywords using agent-browser scraper."""
        if not keywords:
            return {"error": "No keywords provided"}

        if not self.serp_scraper:
            return {
                "error": "No SERP data source available",
                "suggestion": "Install agent-browser for SERP scraping.",
            }

        results = []
        source = "browser_scraper"

        scrape_results = await self.serp_scraper.scrape(keywords, site_domain=site_domain)
        for sr in scrape_results:
            if sr.get("error"):
                results.append(
                    {
                        "keyword": sr.get("keyword", ""),
                        "error": sr["error"],
                    }
                )
            else:
                analysis = self._analyze_serp_results(sr, site_domain)
                results.append(analysis)

        # Aggregate analysis
        summary = self._build_summary(results, site_domain)

        return {
            "source": source,
            "keywords_analyzed": len(results),
            "results": results,
            "summary": summary,
        }

    def _analyze_serp_results(self, serp_data: dict, site_domain: str | None) -> dict:
        """Analyze a single keyword's SERP results."""
        keyword = serp_data.get("keyword", "")
        organic = serp_data.get("results", [])
        features = serp_data.get("features_detected", [])

        analysis = {
            "keyword": keyword,
            "organic_results": len(organic),
            "features_detected": features,
            "feature_descriptions": [SERP_FEATURES.get(f, f) for f in features],
        }

        # Check if site appears in results
        if site_domain and organic:
            site_positions = []
            for i, result in enumerate(organic):
                url = result.get("url", "")
                if site_domain in url:
                    site_positions.append(
                        {
                            "position": i + 1,
                            "url": url,
                            "title": result.get("title", ""),
                        }
                    )
            analysis["site_positions"] = site_positions
            analysis["site_visible"] = len(site_positions) > 0

        # Competitive analysis
        if organic:
            top_domains = []
            seen = set()
            for result in organic[:10]:
                url = result.get("url", "")
                try:
                    from urllib.parse import urlparse

                    domain = urlparse(url).netloc
                    if domain and domain not in seen:
                        seen.add(domain)
                        top_domains.append(domain)
                except Exception:
                    pass
            analysis["top_competing_domains"] = top_domains[:5]

        # Feature opportunities
        analysis["opportunities"] = self._identify_opportunities(
            keyword, features, organic, site_domain
        )

        return analysis

    def _identify_opportunities(
        self,
        keyword: str,
        features: list[str],
        organic: list[dict],
        site_domain: str | None,
    ) -> list[dict]:
        """Identify SERP feature capture opportunities."""
        opportunities = []

        # Featured snippet opportunity
        if "featured_snippet" not in features:
            opportunities.append(
                {
                    "feature": "featured_snippet",
                    "action": (
                        f"Create concise, direct-answer content for '{keyword}' "
                        "with clear paragraph/list/table format"
                    ),
                    "effort": "medium",
                    "impact": "high",
                }
            )

        # PAA opportunity
        if "people_also_ask" in features:
            opportunities.append(
                {
                    "feature": "people_also_ask",
                    "action": (
                        f"Add FAQ section targeting PAA questions for '{keyword}'. "
                        "Use FAQPage schema."
                    ),
                    "effort": "low",
                    "impact": "medium",
                }
            )

        # Video opportunity
        if "video_carousel" in features and site_domain:
            opportunities.append(
                {
                    "feature": "video_carousel",
                    "action": (
                        f"Create video content for '{keyword}' and embed on page "
                        "with VideoObject schema"
                    ),
                    "effort": "high",
                    "impact": "medium",
                }
            )

        return opportunities

    def _build_summary(self, results: list[dict], site_domain: str | None) -> dict:
        """Build aggregate SERP analysis summary."""
        all_features = []
        site_visible_count = 0
        total_analyzed = 0

        for r in results:
            if r.get("error"):
                continue
            total_analyzed += 1
            all_features.extend(r.get("features_detected", []))
            if r.get("site_visible"):
                site_visible_count += 1

        # Feature frequency
        feature_freq: dict[str, int] = {}
        for f in all_features:
            feature_freq[f] = feature_freq.get(f, 0) + 1

        summary = {
            "total_keywords_analyzed": total_analyzed,
            "feature_frequency": feature_freq,
            "most_common_feature": (
                max(feature_freq, key=lambda f: feature_freq[f]) if feature_freq else None
            ),
        }

        if site_domain:
            summary["site_visibility"] = {
                "visible_in": site_visible_count,
                "total": total_analyzed,
                "visibility_rate": (round(site_visible_count / max(total_analyzed, 1) * 100, 1)),
            }

        return summary
