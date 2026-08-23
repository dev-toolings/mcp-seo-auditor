"""Action plan generation service."""

import logging

from app.core.scoring import (
    QUICK_WIN_MAX_EFFORT,
    QUICK_WIN_MIN_IMPACT,
    STRATEGIC_MIN_EFFORT,
    STRATEGIC_MIN_IMPACT,
    TIMELINE_ORDER,
)
from app.services.ai.ai_analyzer import AIAnalyzer

logger = logging.getLogger(__name__)


class ActionPlanService:
    """Generates prioritized action plans from audit data."""

    def __init__(self, ai_analyzer: AIAnalyzer):
        self.ai = ai_analyzer

    async def generate(
        self,
        audit_data: dict,
        business_context: str = "",
        max_actions: int = 20,
    ) -> dict:
        """Generate prioritized action plan from audit data.

        If LLM is available, enriches the plan with strategic rationale.
        Otherwise, uses deterministic priority scoring.
        """
        # Try LLM-enhanced plan first
        if self.ai.ai_available:
            try:
                plan = await self.ai.generate_action_plan(audit_data, business_context)
                actions = plan.get("actions", [])
                if actions:
                    return self._format_plan(actions[:max_actions], ai_enhanced=True)
            except Exception as e:
                logger.warning("LLM action plan failed, using deterministic: %s", e)

        # Deterministic fallback: extract issues from all dimensions
        actions = self._extract_actions(audit_data)
        actions.sort(
            key=lambda a: (
                -a["impact_score"],
                a["effort_score"],
                TIMELINE_ORDER.index(a["timeline"]) if a["timeline"] in TIMELINE_ORDER else 99,
            )
        )
        return self._format_plan(actions[:max_actions], ai_enhanced=False)

    def _extract_actions(self, audit_data: dict) -> list[dict]:
        """Extract actionable items from all audit dimensions."""
        actions = []

        # Sitemap issues
        sitemap = audit_data.get("sitemap", {})
        for issue in sitemap.get("issues", []):
            severity = issue.get("severity", "warning")
            actions.append(
                {
                    "action": f"Fix sitemap issue: {issue.get('type', 'unknown')}",
                    "description": issue.get("description", ""),
                    "impact_score": 9 if severity == "critical" else 6,
                    "effort_score": 3,
                    "priority": "critical" if severity == "critical" else "high",
                    "category": "technical",
                    "timeline": "immediate" if severity == "critical" else "short-term",
                    "expected_outcome": issue.get("recommendation", "Improved crawlability"),
                }
            )

        # Content issues
        content = audit_data.get("content", {})
        content_score = content.get("score", 100)
        pages_with_issues = content.get("pages_with_issues", 0)
        if content_score < 70 and pages_with_issues > 0:
            actions.append(
                {
                    "action": "Improve thin content pages",
                    "description": f"{pages_with_issues} pages have content quality issues.",
                    "impact_score": 8,
                    "effort_score": 7,
                    "priority": "high",
                    "category": "content",
                    "timeline": "short-term",
                    "expected_outcome": "Better rankings through improved content quality and relevance.",
                }
            )

        for page in content.get("pages", []):
            if page.get("word_count", 0) < 50 and page.get("status") == 200:
                actions.append(
                    {
                        "action": f"Add content to thin page: {page.get('url', '')}",
                        "description": f"Page has only {page.get('word_count', 0)} words.",
                        "impact_score": 7,
                        "effort_score": 5,
                        "priority": "high",
                        "category": "content",
                        "timeline": "short-term",
                        "expected_outcome": "Page will be indexed and rank for target keywords.",
                    }
                )

        # Technical issues
        technical = audit_data.get("technical", {})
        for issue in technical.get("canonical_issues", []):
            actions.append(
                {
                    "action": f"Fix canonical issue: {issue.get('url', '')}",
                    "description": issue.get("issue", "Canonical URL mismatch"),
                    "impact_score": 8,
                    "effort_score": 2,
                    "priority": "critical",
                    "category": "technical",
                    "timeline": "immediate",
                    "expected_outcome": "Correct consolidation of page signals.",
                }
            )

        for issue in technical.get("meta_robots_issues", []):
            actions.append(
                {
                    "action": f"Fix meta robots: {issue.get('url', '')}",
                    "description": issue.get("issue", "Meta robots directive conflict"),
                    "impact_score": 9,
                    "effort_score": 2,
                    "priority": "critical",
                    "category": "technical",
                    "timeline": "immediate",
                    "expected_outcome": "Pages will be properly indexed by search engines.",
                }
            )

        # Internal links issues
        links = audit_data.get("internal_links", {})
        orphan_pages = links.get("orphan_pages", [])
        if orphan_pages:
            actions.append(
                {
                    "action": f"Link {len(orphan_pages)} orphan pages",
                    "description": "Pages without internal links are hard for search engines to discover.",
                    "impact_score": 7,
                    "effort_score": 4,
                    "priority": "high",
                    "category": "links",
                    "timeline": "short-term",
                    "expected_outcome": "Better crawl coverage and link equity distribution.",
                }
            )

        broken_links = links.get("broken_internal_links", [])
        if broken_links:
            actions.append(
                {
                    "action": f"Fix {len(broken_links)} broken internal links",
                    "description": "Broken links waste crawl budget and harm user experience.",
                    "impact_score": 8,
                    "effort_score": 3,
                    "priority": "critical",
                    "category": "links",
                    "timeline": "immediate",
                    "expected_outcome": "Eliminated 404 errors and recovered link equity.",
                }
            )

        # Structured data issues
        sd = audit_data.get("structured_data", {})
        sd_results = sd.get("results", [])
        pages_without_schema = sum(1 for r in sd_results if r.get("valid_schemas", 0) == 0)
        if pages_without_schema > 0:
            actions.append(
                {
                    "action": f"Add structured data to {pages_without_schema} pages",
                    "description": "Pages without schema markup miss rich result opportunities.",
                    "impact_score": 6,
                    "effort_score": 3,
                    "priority": "medium",
                    "category": "schema",
                    "timeline": "short-term",
                    "expected_outcome": "Eligibility for rich snippets and improved AI visibility.",
                }
            )

        # GEO issues
        geo = audit_data.get("geo")
        if geo:
            geo_score = geo.get("geo_score", 100)
            if geo_score < 60:
                actions.append(
                    {
                        "action": "Improve GEO readiness for AI search engines",
                        "description": f"GEO score is {geo_score}/100. Content needs optimization for AI-powered search.",
                        "impact_score": 7,
                        "effort_score": 6,
                        "priority": "high" if geo_score < 40 else "medium",
                        "category": "geo",
                        "timeline": "medium-term",
                        "expected_outcome": "Better visibility in AI-powered search results (ChatGPT, Perplexity, etc.).",
                    }
                )

            # Specific GEO dimension issues
            for dim in geo.get("dimensions", []):
                if isinstance(dim, dict) and dim.get("score", 100) < 50:
                    dim_name = dim.get("name", "unknown")
                    actions.append(
                        {
                            "action": f"Improve GEO dimension: {dim_name}",
                            "description": f"{dim_name} scored {dim.get('score', 0)}/100.",
                            "impact_score": 5,
                            "effort_score": 4,
                            "priority": "medium",
                            "category": "geo",
                            "timeline": "medium-term",
                            "expected_outcome": f"Improved {dim_name} for AI search engine citation.",
                        }
                    )

        # Performance issues
        cwv = audit_data.get("cwv")
        if cwv:
            cwv_results = cwv.get("results", [])
            slow_pages = [
                r
                for r in cwv_results
                if isinstance(r, dict) and r.get("performance_score", 100) < 50
            ]
            if slow_pages:
                actions.append(
                    {
                        "action": f"Optimize performance for {len(slow_pages)} slow pages",
                        "description": "Pages with low Core Web Vitals scores impact rankings and UX.",
                        "impact_score": 7,
                        "effort_score": 6,
                        "priority": "high",
                        "category": "performance",
                        "timeline": "medium-term",
                        "expected_outcome": "Better Core Web Vitals and improved page experience signal.",
                    }
                )

        return actions

    def _format_plan(self, actions: list[dict], ai_enhanced: bool) -> dict:
        """Format the action plan with summary and grouping."""
        # Group by timeline
        groups: dict[str, list[dict]] = {}
        for action in actions:
            timeline = action.get("timeline", "medium-term")
            groups.setdefault(timeline, []).append(action)

        # Group by category
        categories: dict[str, list[dict]] = {}
        for action in actions:
            cat = action.get("category", "other")
            categories.setdefault(cat, []).append(action)

        # Quick wins: high impact + low effort
        quick_wins = [
            a
            for a in actions
            if a.get("impact_score", 0) >= QUICK_WIN_MIN_IMPACT
            and a.get("effort_score", 10) <= QUICK_WIN_MAX_EFFORT
        ]

        # Strategic investments: high impact + high effort
        strategic = [
            a
            for a in actions
            if a.get("impact_score", 0) >= STRATEGIC_MIN_IMPACT
            and a.get("effort_score", 0) >= STRATEGIC_MIN_EFFORT
        ]

        return {
            "total_actions": len(actions),
            "actions": actions,
            "by_timeline": {k: len(v) for k, v in groups.items()},
            "by_category": {k: len(v) for k, v in categories.items()},
            "quick_wins": quick_wins[:5],
            "strategic_investments": strategic[:5],
            "ai_enhanced": ai_enhanced,
        }
