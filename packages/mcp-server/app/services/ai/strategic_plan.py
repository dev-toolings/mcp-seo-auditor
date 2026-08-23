"""Strategic plan generation service.

Generates 30/60/90 day SEO roadmaps with dependency graphs,
KPI targets, and milestone tracking.
"""

import logging
from typing import Any, cast

from app.services.ai.cross_correlator import CrossToolCorrelator

logger = logging.getLogger(__name__)

# Action templates for deterministic fallback
PHASE_TEMPLATES: dict[str, dict[str, Any]] = {
    "30_days": {
        "name": "Quick Wins & Critical Fixes",
        "actions": [
            {
                "id": "fix_critical_technical",
                "action": "Fix critical technical issues",
                "category": "technical",
                "effort": "medium",
                "kpi": "Zero critical issues in next crawl",
                "depends_on": [],
            },
            {
                "id": "fix_broken_links",
                "action": "Fix broken internal links",
                "category": "links",
                "effort": "low",
                "kpi": "100% link resolution rate",
                "depends_on": [],
            },
            {
                "id": "add_meta_descriptions",
                "action": "Add missing meta descriptions",
                "category": "content",
                "effort": "low",
                "kpi": "100% meta description coverage",
                "depends_on": [],
            },
            {
                "id": "fix_canonicals",
                "action": "Fix canonical tag issues",
                "category": "technical",
                "effort": "low",
                "kpi": "Zero canonical conflicts",
                "depends_on": [],
            },
            {
                "id": "add_basic_schema",
                "action": "Add Organization/Person schema to homepage",
                "category": "schema",
                "effort": "low",
                "kpi": "Homepage has valid Organization schema",
                "depends_on": [],
            },
        ],
    },
    "60_days": {
        "name": "Content & Authority Building",
        "actions": [
            {
                "id": "improve_thin_content",
                "action": "Improve thin content pages",
                "category": "content",
                "effort": "high",
                "kpi": "All pages above 300 words threshold",
                "depends_on": ["fix_critical_technical"],
            },
            {
                "id": "add_structured_data",
                "action": "Add structured data to key pages",
                "category": "schema",
                "effort": "medium",
                "kpi": "80% pages with valid schema",
                "depends_on": ["add_basic_schema"],
            },
            {
                "id": "fix_orphan_pages",
                "action": "Link orphan pages into site structure",
                "category": "links",
                "effort": "medium",
                "kpi": "Zero orphan pages",
                "depends_on": ["fix_broken_links"],
            },
            {
                "id": "author_eeat",
                "action": "Create author pages and add E-E-A-T signals",
                "category": "eeat",
                "effort": "medium",
                "kpi": "All content pages have author attribution",
                "depends_on": ["add_basic_schema"],
            },
            {
                "id": "optimize_cwv",
                "action": "Optimize Core Web Vitals for slow pages",
                "category": "performance",
                "effort": "high",
                "kpi": "All pages pass CWV thresholds",
                "depends_on": [],
            },
        ],
    },
    "90_days": {
        "name": "Strategic Growth & GEO",
        "actions": [
            {
                "id": "geo_optimization",
                "action": "Optimize content for AI search engines (GEO)",
                "category": "geo",
                "effort": "high",
                "kpi": "GEO score above 70",
                "depends_on": ["add_structured_data", "author_eeat"],
            },
            {
                "id": "content_strategy",
                "action": "Execute content gap strategy",
                "category": "content",
                "effort": "high",
                "kpi": "Publish 10+ new optimized pages",
                "depends_on": ["improve_thin_content"],
            },
            {
                "id": "serp_features",
                "action": "Target SERP features (featured snippets, FAQ)",
                "category": "content",
                "effort": "medium",
                "kpi": "Capture 3+ featured snippets",
                "depends_on": ["add_structured_data"],
            },
            {
                "id": "resolve_cannibalization",
                "action": "Resolve keyword cannibalization",
                "category": "content",
                "effort": "high",
                "kpi": "Zero cannibalization groups",
                "depends_on": ["content_strategy"],
            },
            {
                "id": "monitor_setup",
                "action": "Set up ongoing SEO monitoring",
                "category": "technical",
                "effort": "low",
                "kpi": "Weekly automated audits running",
                "depends_on": [],
            },
        ],
    },
}


class StrategicPlanService:
    """Generate strategic SEO roadmaps."""

    def __init__(self, ai_analyzer=None):
        self.ai = ai_analyzer
        self.correlator = CrossToolCorrelator()

    async def generate(
        self,
        aggregated_data: dict,
        business_context: str = "",
        site_type: str | None = None,
    ) -> dict[str, Any]:
        """Generate a strategic 30/60/90 day roadmap.

        Args:
            aggregated_data: Results from all SEO tools
            business_context: Business description for tailoring
            site_type: Site type (ecommerce, saas, blog, etc.)

        Returns:
            Dict with roadmap phases, compound issues, milestones
        """
        # Step 1: Cross-correlate signals
        correlation = self.correlator.correlate(aggregated_data)

        # Step 2: Try LLM-enhanced plan
        if self.ai and self.ai.ai_available:
            try:
                return await self._llm_plan(
                    aggregated_data, correlation, business_context, site_type
                )
            except Exception as e:
                logger.warning("LLM strategic plan failed, using deterministic: %s", e)

        # Step 3: Deterministic fallback
        return self._deterministic_plan(aggregated_data, correlation, business_context)

    async def _llm_plan(
        self,
        aggregated_data: dict,
        correlation: dict,
        business_context: str,
        site_type: str | None,
    ) -> dict[str, Any]:
        """Generate plan with LLM assistance via AIAnalyzer."""
        from app.services.llm.prompt_templates import (
            SYSTEM_PROMPT_SEO_ANALYST,
            build_strategic_plan_prompt,
        )
        from app.services.llm.token_budget import TokenBudget

        compressed = TokenBudget.prepare_audit_data(aggregated_data, max_tokens=4000)
        compressed["cross_correlation"] = {
            "compound_issues": correlation.get("compound_issues", [])[:10],
            "quick_wins": correlation.get("quick_wins", [])[:5],
            "severity_summary": correlation.get("severity_summary", {}),
        }

        prompt = build_strategic_plan_prompt(compressed, business_context, site_type)
        response = await self.ai.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)

        if isinstance(response, dict) and response.get("roadmap"):
            result = response
            result["cross_correlation"] = correlation
            result["ai_enhanced"] = True
            return result

        # Fallback if LLM response doesn't have expected structure
        return self._deterministic_plan(aggregated_data, correlation, business_context)

    def _deterministic_plan(
        self,
        aggregated_data: dict,
        correlation: dict,
        business_context: str,
    ) -> dict[str, Any]:
        """Generate rule-based strategic plan."""
        roadmap = {}

        for phase_key, template in PHASE_TEMPLATES.items():
            phase_actions = []
            for action_template in template["actions"]:
                # Check if this action is relevant based on data
                relevance = self._check_action_relevance(action_template, aggregated_data)
                if relevance["relevant"]:
                    action = dict(action_template)
                    action["relevance_reason"] = relevance["reason"]
                    action["priority"] = relevance["priority"]
                    phase_actions.append(action)

            roadmap[phase_key] = {
                "phase_name": template["name"],
                "actions": phase_actions,
                "action_count": len(phase_actions),
            }

        # Build dependency graph
        all_actions: list[dict] = []
        for phase in roadmap.values():
            all_actions.extend(cast(list, phase["actions"]))
        dependency_map = self._build_dependency_map(all_actions)

        # Calculate milestones
        milestones = self._calculate_milestones(aggregated_data, roadmap)

        return {
            "roadmap": roadmap,
            "dependency_map": dependency_map,
            "milestones": milestones,
            "cross_correlation": correlation,
            "business_context": business_context or "Not specified",
            "ai_enhanced": False,
        }

    def _check_action_relevance(self, action: dict, data: dict) -> dict:
        """Check if an action is relevant based on audit data."""
        action_id = action["id"]

        # Technical issues
        if action_id == "fix_critical_technical":
            sitemap = data.get("sitemap", {})
            critical = sitemap.get("issues_critical", 0)
            if critical > 0:
                return {
                    "relevant": True,
                    "reason": f"{critical} critical issues detected",
                    "priority": "critical",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "fix_broken_links":
            links = data.get("internal_links", {})
            broken = links.get("broken_internal_links", [])
            if broken:
                return {
                    "relevant": True,
                    "reason": f"{len(broken)} broken links found",
                    "priority": "critical",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "fix_canonicals":
            tech = data.get("technical", {})
            canonicals = tech.get("canonical_issues", [])
            if canonicals:
                return {
                    "relevant": True,
                    "reason": f"{len(canonicals)} canonical issues",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "add_meta_descriptions":
            content = data.get("content", {})
            pages = content.get("pages", [])
            missing = sum(
                1
                for p in pages
                if isinstance(p, dict)
                and "meta description" in " ".join(p.get("issues", [])).lower()
            )
            if missing > 0:
                return {
                    "relevant": True,
                    "reason": f"{missing} pages missing meta description",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "improve_thin_content":
            content = data.get("content", {})
            pages = content.get("pages", [])
            thin = sum(1 for p in pages if isinstance(p, dict) and p.get("word_count", 300) < 100)
            if thin > 0:
                return {
                    "relevant": True,
                    "reason": f"{thin} thin content pages",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "add_basic_schema" or action_id == "add_structured_data":
            sd = data.get("structured_data", {})
            results = sd.get("results", [])
            no_schema = sum(
                1 for r in results if isinstance(r, dict) and r.get("valid_schemas", 0) == 0
            )
            if no_schema > 0 or not results:
                return {
                    "relevant": True,
                    "reason": f"{no_schema} pages without schema",
                    "priority": "medium",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "fix_orphan_pages":
            links = data.get("internal_links", {})
            orphans = links.get("orphan_pages", [])
            if orphans:
                return {
                    "relevant": True,
                    "reason": f"{len(orphans)} orphan pages",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "author_eeat":
            eeat = data.get("eeat", {})
            score = eeat.get("eeat_score", 100)
            if score < 60:
                return {
                    "relevant": True,
                    "reason": f"E-E-A-T score {score}/100",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "optimize_cwv":
            cwv = data.get("cwv", {})
            results = cwv.get("results", [])
            slow = sum(
                1 for r in results if isinstance(r, dict) and r.get("performance_score", 100) < 50
            )
            if slow > 0:
                return {
                    "relevant": True,
                    "reason": f"{slow} pages with poor CWV",
                    "priority": "high",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "geo_optimization":
            geo = data.get("geo", {})
            score = geo.get("geo_score", 100)
            if score < 60:
                return {
                    "relevant": True,
                    "reason": f"GEO score {score}/100",
                    "priority": "medium",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        if action_id == "resolve_cannibalization":
            cannibal = data.get("cannibalization", {})
            groups = cannibal.get("cannibalization_groups", 0)
            if groups > 0:
                return {
                    "relevant": True,
                    "reason": f"{groups} cannibalization groups",
                    "priority": "medium",
                }
            return {"relevant": False, "reason": "", "priority": ""}

        # Default: always relevant for strategic actions
        return {
            "relevant": True,
            "reason": "Strategic improvement opportunity",
            "priority": "medium",
        }

    def _build_dependency_map(self, actions: list[dict]) -> list[dict]:
        """Build a dependency graph from action dependencies."""
        deps = []
        action_ids = {a["id"] for a in actions}

        for action in actions:
            for dep_id in action.get("depends_on", []):
                if dep_id in action_ids:
                    deps.append(
                        {
                            "from": dep_id,
                            "to": action["id"],
                            "type": "blocks",
                        }
                    )

        return deps

    def _calculate_milestones(self, data: dict, roadmap: dict) -> list[dict]:
        """Calculate expected milestones per phase."""
        milestones = []

        # 30-day milestone
        phase_30 = roadmap.get("30_days", {})
        if phase_30.get("action_count", 0) > 0:
            milestones.append(
                {
                    "phase": "30 days",
                    "name": "Foundation Solid",
                    "targets": [
                        "Zero critical technical issues",
                        "All meta descriptions in place",
                        "No broken internal links",
                    ],
                    "expected_score_lift": "+10-15 points",
                }
            )

        # 60-day milestone
        phase_60 = roadmap.get("60_days", {})
        if phase_60.get("action_count", 0) > 0:
            milestones.append(
                {
                    "phase": "60 days",
                    "name": "Content & Authority",
                    "targets": [
                        "No thin content pages",
                        "80%+ schema coverage",
                        "Author pages live",
                        "CWV passing on all pages",
                    ],
                    "expected_score_lift": "+15-25 points",
                }
            )

        # 90-day milestone
        phase_90 = roadmap.get("90_days", {})
        if phase_90.get("action_count", 0) > 0:
            milestones.append(
                {
                    "phase": "90 days",
                    "name": "Growth & Visibility",
                    "targets": [
                        "GEO score above 70",
                        "Featured snippet captures",
                        "Cannibalization resolved",
                        "Monitoring in place",
                    ],
                    "expected_score_lift": "+10-20 points",
                }
            )

        return milestones
