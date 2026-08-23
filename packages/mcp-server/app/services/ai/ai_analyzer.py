"""Core AI analyzer with deterministic fallback."""

import logging
from typing import Optional, cast

from app.core.scoring import DIMENSION_WEIGHTS, EFFORT_MAP, RECOMMENDATION_THRESHOLDS, AuditScorer
from app.services.llm.base_provider import BaseLLMProvider
from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_SEO_ANALYST,
    build_action_plan_prompt,
    build_anomaly_analysis_prompt,
    build_content_plan_prompt,
    build_executive_summary_prompt,
    build_full_audit_prompt,
    build_gsc_keyword_insights_prompt,
    build_keyword_insights_prompt,
    build_topical_authority_prompt,
)
from app.services.llm.token_budget import TokenBudget

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """AI-powered SEO analysis with graceful fallback to deterministic scoring."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    @property
    def ai_available(self) -> bool:
        """Check if AI analysis is available (sync check)."""
        if self.llm is None:
            return False
        config = getattr(self.llm, "config", None)
        if config is None:
            return self.llm is not None
        if getattr(config, "provider", "") == "ollama":
            return bool(getattr(config, "base_url", ""))
        return bool(getattr(config, "api_key", ""))

    async def analyze_audit(self, audit_data: dict, context: str = "") -> dict:
        """Enrich audit data with AI analysis. Always returns deterministic + optional AI."""
        result = self._deterministic_analysis(audit_data)

        if self.ai_available:
            try:
                compressed = TokenBudget.prepare_audit_data(audit_data)
                ai_enrichment = await self._ai_analyze(compressed, context)
                result.update(ai_enrichment)
                result["ai_enhanced"] = True
            except Exception as e:
                logger.warning("AI analysis failed, using fallback: %s", e)
                result["ai_enhanced"] = False
                result["ai_error"] = f"LLM analysis failed, using deterministic fallback: {e}"
        else:
            result["ai_enhanced"] = False

        return result

    async def generate_action_plan(self, audit_data: dict, business_context: str = "") -> dict:
        """Generate a prioritized action plan."""
        if not self.ai_available:
            return self._deterministic_action_plan(audit_data)
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(audit_data)
            prompt = build_action_plan_prompt(compressed, business_context)
            return await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
        except Exception as e:
            logger.warning("AI action plan failed: %s", e)
            return self._deterministic_action_plan(audit_data)

    async def generate_executive_summary(self, report_data: dict) -> dict:
        """Generate an executive summary of the full report."""
        if not self.ai_available:
            return self._deterministic_summary(report_data)
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(report_data)
            prompt = build_executive_summary_prompt(compressed)
            return await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
        except Exception as e:
            logger.warning("AI summary failed: %s", e)
            return self._deterministic_summary(report_data)

    async def _ai_analyze(self, audit_data: dict, context: str) -> dict:
        """Run AI-powered analysis via LLM."""
        assert self.llm is not None  # only called when ai_available is True
        prompt = build_full_audit_prompt(audit_data)
        if context:
            prompt += f"\n\nADDITIONAL CONTEXT:\n{context}"
        return await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)

    async def analyze_keyword_insights(self, market_data: dict) -> dict:
        """Analyze market research data to identify high-impact keywords."""
        if not self.ai_available:
            return {"ai_enhanced": False}
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(market_data)
            prompt = build_keyword_insights_prompt(compressed)
            result = await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
            result["ai_enhanced"] = True
            return result
        except Exception as e:
            logger.warning("AI keyword insights failed: %s", e)
            return {"ai_enhanced": False, "ai_error": str(e)}

    async def analyze_gsc_keywords(self, gsc_data: dict) -> dict:
        """Analyze GSC query portfolio for keyword opportunities."""
        if not self.ai_available:
            return {"ai_enhanced": False}
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(gsc_data)
            prompt = build_gsc_keyword_insights_prompt(compressed)
            result = await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
            result["ai_enhanced"] = True
            return result
        except Exception as e:
            logger.warning("AI GSC keyword analysis failed: %s", e)
            return {"ai_enhanced": False, "ai_error": str(e)}

    async def analyze_topical_clusters(self, cluster_data: dict) -> dict:
        """Analyze topical authority clusters for strategic insights."""
        if not self.ai_available:
            return {"ai_enhanced": False}
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(cluster_data)
            prompt = build_topical_authority_prompt(compressed)
            result = await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
            result["ai_enhanced"] = True
            return result
        except Exception as e:
            logger.warning("AI topical authority analysis failed: %s", e)
            return {"ai_enhanced": False, "ai_error": str(e)}

    async def generate_content_plan(self, site_data: dict) -> dict:
        """Generate a prioritized editorial content plan with per-article LLM prompts."""
        if not self.ai_available:
            return {"ai_enhanced": False, "error": "LLM not available for content plan generation"}
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            compressed = TokenBudget.prepare_audit_data(site_data, max_tokens=8000)
            prompt = build_content_plan_prompt(compressed)
            # Content plan with full generation prompts needs a higher output budget —
            # passed per call so it never mutates the shared config (avoids a race).
            plan_max_tokens = max(self.llm.config.max_tokens, 16000)
            result = await self.llm.complete_json(
                SYSTEM_PROMPT_SEO_ANALYST, prompt, max_tokens=plan_max_tokens
            )
            result["ai_enhanced"] = True
            return result
        except Exception as e:
            logger.warning("AI content plan generation failed: %s", e)
            return {"ai_enhanced": False, "ai_error": str(e)}

    async def analyze_anomalies(self, anomaly_data: dict) -> dict:
        """Enrich anomaly detection results with AI analysis."""
        if not self.ai_available:
            return {}
        assert self.llm is not None  # ai_available guarantees a provider

        try:
            prompt = build_anomaly_analysis_prompt(anomaly_data)
            return await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
        except Exception as e:
            logger.warning("AI anomaly analysis failed: %s", e)
            return {}

    def _deterministic_analysis(
        self,
        audit_data: dict,
        dimension_scores: dict[str, int] | None = None,
    ) -> dict:
        """Score-based analysis without LLM.

        If *dimension_scores* are provided (e.g. pre-calculated by
        FullAuditService), they are used directly.  Otherwise a basic
        fallback assigns 50 to every dimension.
        """
        if dimension_scores is None:
            # Use pre-calculated scores from audit_data when available,
            # otherwise fall back to neutral defaults.
            dimension_scores = audit_data.get(
                "dimension_scores",
                {k: 50 for k in DIMENSION_WEIGHTS},
            )

        overall = AuditScorer.calculate_overall_score(dimension_scores)
        recommendations = self._generate_rule_based_recommendations(audit_data, dimension_scores)

        return {
            "overall_score": overall,
            "dimension_scores": dimension_scores,
            "prioritized_recommendations": recommendations,
            "quick_wins": self._identify_quick_wins(audit_data, dimension_scores),
            "risk_factors": self._identify_risks(audit_data, dimension_scores),
            "executive_summary": self._build_deterministic_summary(overall, dimension_scores),
            "strategic_insights": [],
            "ai_enhanced": False,
        }

    def _generate_rule_based_recommendations(
        self, data: dict, scores: dict[str, int]
    ) -> list[dict]:
        """Generate recommendations based on scores and thresholds."""
        recommendations = []

        if scores.get("technical", 100) < RECOMMENDATION_THRESHOLDS["technical"]:
            recommendations.append(
                {
                    "title": "Fix critical technical SEO issues",
                    "description": f"Found {data.get('issues_critical', 0)} critical issues affecting crawlability and indexing.",
                    "impact": "critical",
                    "effort": "medium",
                    "priority_score": 95,
                    "category": "technical",
                    "timeline": "immediate",
                    "rationale": "Technical issues block search engines from properly indexing your site.",
                }
            )

        if scores.get("content", 100) < RECOMMENDATION_THRESHOLDS["content"]:
            recommendations.append(
                {
                    "title": "Improve content quality and coverage",
                    "description": "Content analysis shows thin or missing content on multiple pages.",
                    "impact": "high",
                    "effort": "high",
                    "priority_score": 80,
                    "category": "content",
                    "timeline": "short-term",
                    "rationale": "Quality content is the primary ranking factor for search engines.",
                }
            )

        if scores.get("schema", 100) < RECOMMENDATION_THRESHOLDS["schema"]:
            recommendations.append(
                {
                    "title": "Add structured data markup",
                    "description": "Schema.org markup is missing or incomplete across the site.",
                    "impact": "medium",
                    "effort": "low",
                    "priority_score": 70,
                    "category": "schema",
                    "timeline": "short-term",
                    "rationale": "Structured data enables rich results and improves AI engine visibility.",
                }
            )

        if scores.get("links", 100) < RECOMMENDATION_THRESHOLDS["links"]:
            recommendations.append(
                {
                    "title": "Fix internal linking structure",
                    "description": "Internal link issues detected: orphan pages or broken links.",
                    "impact": "high",
                    "effort": "medium",
                    "priority_score": 75,
                    "category": "links",
                    "timeline": "short-term",
                    "rationale": "Internal linking distributes authority and helps search engines discover content.",
                }
            )

        if scores.get("performance", 100) < RECOMMENDATION_THRESHOLDS["performance"]:
            recommendations.append(
                {
                    "title": "Optimize page performance",
                    "description": "Core Web Vitals scores indicate performance issues.",
                    "impact": "high",
                    "effort": "medium",
                    "priority_score": 72,
                    "category": "performance",
                    "timeline": "medium-term",
                    "rationale": "Page speed is a ranking factor and impacts user experience.",
                }
            )

        if scores.get("geo", 100) < RECOMMENDATION_THRESHOLDS["geo"]:
            recommendations.append(
                {
                    "title": "Improve GEO readiness",
                    "description": "Content is not optimized for AI-powered search engines.",
                    "impact": "medium",
                    "effort": "medium",
                    "priority_score": 60,
                    "category": "geo",
                    "timeline": "medium-term",
                    "rationale": "AI search engines are increasingly used for information retrieval.",
                }
            )

        # Sort by priority_score descending
        recommendations.sort(key=lambda r: cast(int, r["priority_score"]), reverse=True)
        return recommendations

    def _identify_quick_wins(self, data: dict, scores: dict[str, int]) -> list[str]:
        """Identify easy improvements with high impact."""
        quick_wins = []

        if scores.get("schema", 100) < 50:
            quick_wins.append(
                "Add JSON-LD structured data to key pages (low effort, high SEO impact)"
            )

        metadata = data.get("metadata", {})
        content = metadata.get("content", {})
        if content.get("missing_meta_description", 0) > 0:
            quick_wins.append(
                f"Write meta descriptions for {content['missing_meta_description']} pages missing them"
            )

        if content.get("missing_h1", 0) > 0:
            quick_wins.append(f"Add H1 headings to {content['missing_h1']} pages")

        if scores.get("performance", 100) < 70:
            quick_wins.append("Enable image compression and lazy loading for faster page loads")

        return quick_wins

    def _identify_risks(self, data: dict, scores: dict[str, int]) -> list[str]:
        """Identify critical risks from audit data."""
        risks = []

        if data.get("issues_critical", 0) > 5:
            risks.append(
                f"{data['issues_critical']} critical issues may cause significant ranking loss"
            )

        if scores.get("technical", 100) < 40:
            risks.append("Very low technical score - search engines may struggle to crawl the site")

        if scores.get("content", 100) < 30:
            risks.append("Content quality is critically low - risk of thin content penalty")

        return risks

    def _build_deterministic_summary(self, overall: int, scores: dict[str, int]) -> str:
        """Build a text summary from deterministic scores."""
        if overall >= 80:
            grade = "good"
        elif overall >= 60:
            grade = "average"
        elif overall >= 40:
            grade = "below average"
        else:
            grade = "poor"

        weakest = min(scores, key=lambda k: scores[k]) if scores else "unknown"
        strongest = max(scores, key=lambda k: scores[k]) if scores else "unknown"

        return (
            f"Overall SEO health is {grade} with a score of {overall}/100. "
            f"Strongest dimension: {strongest} ({scores.get(strongest, 0)}/100). "
            f"Weakest dimension: {weakest} ({scores.get(weakest, 0)}/100). "
            f"Focus improvements on {weakest} for the biggest impact."
        )

    def _deterministic_action_plan(self, audit_data: dict) -> dict:
        """Generate a rule-based action plan without AI."""
        scores = audit_data.get(
            "dimension_scores",
            {k: 50 for k in DIMENSION_WEIGHTS},
        )
        recommendations = self._generate_rule_based_recommendations(audit_data, scores)
        actions = []
        for rec in recommendations:
            actions.append(
                {
                    "action": rec["title"],
                    "description": rec["description"],
                    "impact_score": min(10, int(rec["priority_score"] / 10)),
                    "effort_score": EFFORT_MAP.get(rec["effort"], 5),
                    "priority": rec["impact"],
                    "category": rec["category"],
                    "timeline": rec["timeline"],
                    "expected_outcome": rec["rationale"],
                }
            )
        return {"actions": actions, "ai_enhanced": False}

    def _deterministic_summary(self, report_data: dict) -> dict:
        """Generate a rule-based executive summary without AI."""
        score = report_data.get("score", report_data.get("overall_score", 50))
        return {
            "headline": f"SEO Audit Score: {score}/100",
            "score_interpretation": self._build_deterministic_summary(
                score, report_data.get("dimension_scores", {})
            ),
            "top_3_priorities": [],
            "business_impact": "See detailed recommendations for business impact analysis.",
            "timeline_recommendation": "Focus on critical issues first, then high-impact quick wins.",
            "investment_areas": [],
            "ai_enhanced": False,
        }
