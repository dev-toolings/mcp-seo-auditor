"""SERP landscape analysis service.

Detects SERP features present for given keywords and identifies
opportunities for the target site.
"""

import logging
from typing import Any, Optional

from app.services.llm.base_provider import BaseLLMProvider
from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_SEO_ANALYST,
    build_serp_analysis_prompt,
)

logger = logging.getLogger(__name__)

# SERP feature types we detect
SERP_FEATURES = [
    "featured_snippet",
    "people_also_ask",
    "knowledge_panel",
    "local_pack",
    "image_pack",
    "video_carousel",
    "shopping_results",
    "top_stories",
    "sitelinks",
    "faq_rich_result",
]

# Intent classification keywords
INTENT_SIGNALS = {
    "informational": [
        "what",
        "how",
        "why",
        "when",
        "who",
        "guide",
        "tutorial",
        "definition",
        "meaning",
        "explain",
        "comment",
        "pourquoi",
        "qu'est-ce",
        "quoi",
    ],
    "commercial": [
        "best",
        "top",
        "review",
        "compare",
        "vs",
        "alternative",
        "meilleur",
        "comparatif",
        "avis",
    ],
    "transactional": [
        "buy",
        "price",
        "cheap",
        "deal",
        "coupon",
        "order",
        "acheter",
        "prix",
        "pas cher",
        "promo",
    ],
    "navigational": [
        "login",
        "sign in",
        "official",
        "site",
        "app",
        "connexion",
    ],
}


class SERPLandscapeService:
    """Analyze SERP landscape for given keywords."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    async def analyze(
        self,
        keywords: list[str],
        site_domain: str | None = None,
    ) -> dict[str, Any]:
        """Analyze SERP landscape for keywords.

        Args:
            keywords: Keywords to analyze
            site_domain: Optional domain to check presence for

        Returns:
            Dict with features per keyword, opportunities, and summary
        """
        if not keywords:
            return {"error": "No keywords provided"}

        results = []
        for keyword in keywords[:20]:  # Cap at 20 keywords
            try:
                result = await self._analyze_keyword(keyword, site_domain)
                results.append(result)
            except Exception as e:
                logger.warning("SERP analysis failed for '%s': %s", keyword, e)
                results.append(
                    {
                        "keyword": keyword,
                        "error": str(e),
                        "features": {},
                        "intent": self._classify_intent(keyword),
                    }
                )

        # If LLM available, enrich with strategic analysis
        if self.llm and self.llm.is_available():
            try:
                enrichment = await self._enrich_with_llm(results, site_domain)
                return {
                    "keywords_analyzed": len(results),
                    "results": results,
                    "opportunities": self._identify_opportunities(results, site_domain),
                    "summary": self._build_summary(results),
                    "strategic_analysis": enrichment,
                    "ai_enhanced": True,
                }
            except Exception as e:
                logger.warning("LLM SERP enrichment failed: %s", e)

        return {
            "keywords_analyzed": len(results),
            "results": results,
            "opportunities": self._identify_opportunities(results, site_domain),
            "summary": self._build_summary(results),
            "ai_enhanced": False,
        }

    async def _analyze_keyword(
        self,
        keyword: str,
        site_domain: str | None = None,
    ) -> dict[str, Any]:
        """Analyze SERP features for a single keyword."""
        intent = self._classify_intent(keyword)

        # Estimate SERP features based on intent + keyword patterns
        features = self._estimate_features(keyword, intent)

        # Calculate opportunity score
        opportunity_score = self._calculate_opportunity(features, intent, site_domain)

        return {
            "keyword": keyword,
            "intent": intent,
            "features": features,
            "opportunity_score": opportunity_score,
            "feature_count": sum(1 for f in features.values() if f.get("likely", False)),
            "recommendations": self._keyword_recommendations(keyword, features, intent),
        }

    def _classify_intent(self, keyword: str) -> str:
        """Classify search intent of a keyword."""
        kw_lower = keyword.lower()

        scores = {intent: 0 for intent in INTENT_SIGNALS}
        for intent, signals in INTENT_SIGNALS.items():
            for signal in signals:
                if signal in kw_lower:
                    scores[intent] += 1

        best_intent = max(scores, key=lambda k: scores[k])
        if scores[best_intent] > 0:
            return best_intent
        return "informational"  # default

    def _estimate_features(self, keyword: str, intent: str) -> dict[str, dict]:
        """Estimate which SERP features are likely present."""
        kw_lower = keyword.lower()
        features = {}

        # Featured snippet: informational queries with question words
        features["featured_snippet"] = {
            "likely": intent == "informational"
            and any(
                w in kw_lower for w in ["what", "how", "why", "definition", "comment", "pourquoi"]
            ),
            "type": self._guess_snippet_type(kw_lower),
            "opportunity": "high" if intent == "informational" else "low",
        }

        # People Also Ask: most queries
        features["people_also_ask"] = {
            "likely": len(keyword.split()) >= 2,
            "opportunity": "high",
        }

        # Knowledge panel: branded, entity queries
        features["knowledge_panel"] = {
            "likely": len(keyword.split()) <= 2 and intent == "navigational",
            "opportunity": "medium",
        }

        # Local pack: location-based queries
        local_signals = [
            "near me",
            "nearby",
            "local",
            "closest",
            "à proximité",
            "près de",
            "restaurant",
            "hotel",
            "store",
            "magasin",
        ]
        features["local_pack"] = {
            "likely": any(s in kw_lower for s in local_signals),
            "opportunity": "high" if any(s in kw_lower for s in local_signals) else "low",
        }

        # Image pack: visual queries
        image_signals = [
            "photo",
            "image",
            "picture",
            "design",
            "logo",
            "infographic",
            "diagram",
            "chart",
            "gallery",
            "wallpaper",
        ]
        features["image_pack"] = {
            "likely": any(s in kw_lower for s in image_signals),
            "opportunity": "medium",
        }

        # Video carousel: tutorial, how-to, review
        video_signals = [
            "video",
            "tutorial",
            "how to",
            "review",
            "unboxing",
            "demo",
            "tuto",
            "comment faire",
        ]
        features["video_carousel"] = {
            "likely": any(s in kw_lower for s in video_signals),
            "opportunity": "high" if any(s in kw_lower for s in video_signals) else "low",
        }

        # Shopping: transactional queries
        features["shopping_results"] = {
            "likely": intent == "transactional",
            "opportunity": "high" if intent == "transactional" else "low",
        }

        # Top stories: news-related queries
        news_signals = [
            "news",
            "latest",
            "update",
            "breaking",
            "today",
            "actualité",
            "dernière",
            "2025",
            "2026",
        ]
        features["top_stories"] = {
            "likely": any(s in kw_lower for s in news_signals),
            "opportunity": "medium",
        }

        # FAQ rich result
        features["faq_rich_result"] = {
            "likely": intent in ("informational", "commercial"),
            "opportunity": "high",
        }

        # Sitelinks: branded queries
        features["sitelinks"] = {
            "likely": intent == "navigational" and len(keyword.split()) <= 3,
            "opportunity": "low",
        }

        return features

    def _guess_snippet_type(self, keyword: str) -> str:
        """Guess the type of featured snippet expected."""
        if any(w in keyword for w in ["list", "top", "best", "steps", "meilleur"]):
            return "list"
        if any(w in keyword for w in ["vs", "compare", "difference", "comparatif"]):
            return "table"
        if any(w in keyword for w in ["definition", "what is", "qu'est-ce"]):
            return "paragraph"
        return "paragraph"

    def _calculate_opportunity(
        self,
        features: dict[str, dict],
        intent: str,
        site_domain: str | None,
    ) -> int:
        """Calculate opportunity score (0-100) for this keyword."""
        score = 50  # Base score

        # More features = more opportunity
        feature_count = sum(1 for f in features.values() if f.get("likely", False))
        score += feature_count * 5

        # High opportunity features
        high_opp = sum(
            1 for f in features.values() if f.get("opportunity") == "high" and f.get("likely")
        )
        score += high_opp * 10

        # Intent bonus
        if intent in ("informational", "commercial"):
            score += 10  # More content-driven opportunities

        return max(0, min(100, score))

    def _identify_opportunities(self, results: list[dict], site_domain: str | None) -> list[dict]:
        """Identify top opportunities across all keywords."""
        opportunities = []

        for r in results:
            if r.get("error"):
                continue

            features = r.get("features", {})
            keyword = r.get("keyword", "")

            # Featured snippet opportunity
            fs = features.get("featured_snippet", {})
            if fs.get("likely") and fs.get("opportunity") == "high":
                opportunities.append(
                    {
                        "keyword": keyword,
                        "type": "featured_snippet",
                        "action": f"Optimize content for {fs.get('type', 'paragraph')} "
                        f"featured snippet targeting '{keyword}'",
                        "impact": "high",
                        "effort": "medium",
                    }
                )

            # FAQ opportunity
            faq = features.get("faq_rich_result", {})
            paa = features.get("people_also_ask", {})
            if faq.get("likely") and paa.get("likely"):
                opportunities.append(
                    {
                        "keyword": keyword,
                        "type": "faq_rich_result",
                        "action": f"Add FAQPage schema with common questions about '{keyword}'",
                        "impact": "high",
                        "effort": "low",
                    }
                )

            # Video opportunity
            video = features.get("video_carousel", {})
            if video.get("likely") and video.get("opportunity") == "high":
                opportunities.append(
                    {
                        "keyword": keyword,
                        "type": "video",
                        "action": f"Create video content for '{keyword}' to "
                        f"capture video carousel placement",
                        "impact": "high",
                        "effort": "high",
                    }
                )

        # Sort by impact (high first), then effort (low first)
        effort_order = {"low": 0, "medium": 1, "high": 2}
        opportunities.sort(
            key=lambda x: (
                0 if x.get("impact") == "high" else 1,
                effort_order.get(x.get("effort", "medium"), 1),
            )
        )
        return opportunities[:15]

    def _keyword_recommendations(self, keyword: str, features: dict, intent: str) -> list[str]:
        """Generate recommendations for a specific keyword."""
        recs = []

        if features.get("featured_snippet", {}).get("likely"):
            snippet_type = features["featured_snippet"].get("type", "paragraph")
            recs.append(
                f"Target featured snippet with {snippet_type} format. "
                "Use clear question-answer structure."
            )

        if features.get("people_also_ask", {}).get("likely"):
            recs.append(
                "Add FAQ section targeting related questions. "
                "Use FAQPage schema for rich result eligibility."
            )

        if features.get("video_carousel", {}).get("likely"):
            recs.append(
                "Create video content with VideoObject schema. "
                "Embed on page with transcript for SEO."
            )

        if intent == "commercial":
            recs.append(
                "Add comparison tables, pros/cons, and review schema "
                "to capture commercial intent queries."
            )

        return recs[:3]

    def _build_summary(self, results: list[dict]) -> dict:
        """Build summary statistics across all keywords."""
        total = len(results)
        if total == 0:
            return {}

        valid = [r for r in results if not r.get("error")]
        intent_dist: dict[str, int] = {}
        feature_freq: dict[str, int] = {}

        for r in valid:
            intent = r.get("intent", "unknown")
            intent_dist[intent] = intent_dist.get(intent, 0) + 1

            for fname, fdata in r.get("features", {}).items():
                if fdata.get("likely"):
                    feature_freq[fname] = feature_freq.get(fname, 0) + 1

        avg_opp = (
            int(sum(r.get("opportunity_score", 0) for r in valid) / len(valid)) if valid else 0
        )

        return {
            "total_keywords": total,
            "analyzed": len(valid),
            "avg_opportunity_score": avg_opp,
            "intent_distribution": intent_dist,
            "feature_frequency": dict(
                sorted(feature_freq.items(), key=lambda x: x[1], reverse=True)
            ),
        }

    async def _enrich_with_llm(self, results: list[dict], site_domain: str | None) -> dict:
        """Use LLM for strategic SERP analysis."""
        assert self.llm is not None  # guarded by caller (self.llm.is_available())
        prompt = build_serp_analysis_prompt(results, site_domain)
        response = await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
        return response if isinstance(response, dict) else {}
