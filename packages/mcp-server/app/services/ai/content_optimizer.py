"""Content optimization service — improves existing content for SEO."""

import logging

from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_CONTENT_WRITER,
    build_content_optimize_prompt,
)
from app.services.llm.token_budget import TokenBudget

logger = logging.getLogger(__name__)


class ContentOptimizerService:
    """Optimizes existing content for better SEO performance."""

    def __init__(self, ai_analyzer, editorial_context):
        self.ai = ai_analyzer
        self.editorial = editorial_context

    async def optimize(
        self,
        content: str,
        keywords: list | None = None,
        seo_analysis: dict | None = None,
    ) -> dict:
        """Optimize content for SEO.

        Flow: prepare data -> call LLM with build_content_optimize_prompt
        -> return optimized content + changes.
        If LLM unavailable, return basic deterministic recommendations.
        """
        keywords = keywords or []
        seo_analysis = seo_analysis or {}

        if not content:
            return self._empty_content_result()

        if not self.ai.ai_available:
            return self._deterministic_optimize(content, keywords)

        try:
            compressed_analysis = (
                TokenBudget.prepare_audit_data(seo_analysis) if seo_analysis else {}
            )
            prompt = build_content_optimize_prompt(content, compressed_analysis, keywords)
            result = await self.ai.llm.complete_json(SYSTEM_PROMPT_CONTENT_WRITER, prompt)
            if not isinstance(result, dict):
                logger.warning("LLM returned non-dict for optimize: %s", type(result))
                return self._deterministic_optimize(content, keywords)

            return {
                "optimized_content": result.get("optimized_content", content),
                "changes": result.get("changes", []),
                "score_before": result.get("optimization_score", 0.0)
                if "readability_before" not in result
                else result.get("readability_before", 0.0),
                "score_after": result.get("readability_after", 0.0),
                "ai_enhanced": True,
            }
        except Exception as e:
            logger.warning("LLM content optimize failed, using fallback: %s", e)
            return self._deterministic_optimize(content, keywords)

    # ── Deterministic fallbacks ──────────────────────

    def _deterministic_optimize(self, content: str, keywords: list) -> dict:
        """Analyze content for basic issues without rewriting."""
        changes = []
        word_count = len(content.split())

        # Check word count
        if word_count < 300:
            changes.append(
                {
                    "type": "section_added",
                    "location": "overall",
                    "original": None,
                    "optimized": None,
                    "rationale": f"Content is thin ({word_count} words). Target 1500+ words for competitive queries.",
                }
            )

        # Check keyword presence
        content_lower = content.lower()
        missing_keywords = [kw for kw in keywords if kw.lower() not in content_lower]
        for kw in missing_keywords:
            changes.append(
                {
                    "type": "keyword_added",
                    "location": "content body",
                    "original": None,
                    "optimized": None,
                    "rationale": f"Keyword '{kw}' is missing from the content. Add it naturally.",
                }
            )

        # Check heading presence
        has_h1 = "<h1" in content_lower or "# " in content
        has_h2 = "<h2" in content_lower or "## " in content
        if not has_h1:
            changes.append(
                {
                    "type": "heading_rewritten",
                    "location": "top of page",
                    "original": None,
                    "optimized": None,
                    "rationale": "Missing H1 heading. Add one containing the primary keyword.",
                }
            )
        if not has_h2:
            changes.append(
                {
                    "type": "heading_rewritten",
                    "location": "content sections",
                    "original": None,
                    "optimized": None,
                    "rationale": "No H2 subheadings found. Add section headings for structure and SEO.",
                }
            )

        # Basic scoring heuristic
        score_before = min(100, max(0, int(word_count / 30)))
        keyword_bonus = max(0, len(keywords) - len(missing_keywords)) * 10
        score_after = min(100, score_before + keyword_bonus)

        return {
            "optimized_content": content,
            "changes": changes,
            "score_before": float(score_before),
            "score_after": float(score_after),
            "ai_enhanced": False,
        }

    def _empty_content_result(self) -> dict:
        """Return result for empty content input."""
        return {
            "optimized_content": "",
            "changes": [
                {
                    "type": "section_added",
                    "location": "overall",
                    "original": None,
                    "optimized": None,
                    "rationale": "Content is empty. Provide content to optimize.",
                }
            ],
            "score_before": 0.0,
            "score_after": 0.0,
            "ai_enhanced": False,
        }
