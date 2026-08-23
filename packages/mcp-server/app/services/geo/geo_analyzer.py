"""GEO (Generative Engine Optimization) analyzer.

Orchestrates all GEO sub-services to produce a unified GEO readiness analysis.
"""

import asyncio
import logging
from typing import Optional, cast

from app.core.scoring import ENGINE_GEO_WEIGHTS
from app.models.geo_models import GEODimension, GEOPageResult, GEOReport
from app.services.geo.ai_readability import AIReadabilityChecker
from app.services.geo.citation_readiness import CitationReadinessChecker
from app.services.geo.eeat_detector import EEATDetector
from app.services.geo.faq_completeness import FAQCompletenessChecker
from app.services.geo.schema_coverage import SchemaCoverageChecker
from app.services.llm.base_provider import BaseLLMProvider
from app.services.llm.prompt_templates import build_geo_analysis_prompt

logger = logging.getLogger(__name__)


class GEOAnalyzer:
    """Unified GEO analysis combining all sub-services."""

    # Imported from centralized scoring config
    from app.core.scoring import GEO_WEIGHTS

    WEIGHTS = GEO_WEIGHTS

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider
        self.readability_checker = AIReadabilityChecker()
        self.schema_checker = SchemaCoverageChecker()
        self.eeat_detector = EEATDetector()
        self.faq_checker = FAQCompletenessChecker()
        self.citation_checker = CitationReadinessChecker()

    def _resolve_weights(self, target_engine: str) -> dict:
        """Return the dimension weight profile for the requested AI engine."""
        return ENGINE_GEO_WEIGHTS.get(target_engine, self.WEIGHTS)

    async def analyze_page(
        self,
        url: str,
        html_content: str,
        structured_data: list[dict],
        target_engine: str = "all",
    ) -> GEOPageResult:
        """Analyze a single page for GEO readiness.

        Args:
            url: Page URL
            html_content: Raw HTML content
            structured_data: List of JSON-LD blocks
            target_engine: Weight profile to apply (all / google_ai_overviews /
                perplexity / chatgpt_search / gemini)

        Returns:
            GEOPageResult with scores and issues
        """
        weights = self._resolve_weights(target_engine)

        # Run all 5 deterministic checks
        readability = self.readability_checker.check(html_content, url)
        schema = self.schema_checker.check(url, structured_data)
        eeat = self.eeat_detector.check(html_content, url)
        faq = self.faq_checker.check(html_content, structured_data)
        citation = self.citation_checker.check(html_content, url)

        # Compute weighted overall score
        geo_score = int(
            readability["score"] * weights["ai_readability"]
            + schema["score"] * weights["schema_coverage"]
            + eeat["score"] * weights["eeat"]
            + faq["score"] * weights["faq_completeness"]
            + citation["score"] * weights["citation_readiness"]
        )
        geo_score = max(0, min(100, geo_score))

        # Aggregate issues
        all_issues = (
            readability["issues"]
            + schema["issues"]
            + eeat["issues"]
            + faq["issues"]
            + citation["issues"]
        )

        # Build recommendations from issues
        recommendations = all_issues[:10]

        return GEOPageResult(
            url=url,
            geo_score=geo_score,
            ai_readability=readability["score"],
            schema_coverage=schema["score"],
            faq_completeness=faq["score"],
            eeat_score=eeat["score"],
            citation_readiness=citation["score"],
            issues=all_issues,
            recommendations=recommendations,
        )

    async def analyze_pages(self, pages: list[dict], target_engine: str = "all") -> GEOReport:
        """Analyze multiple pages for GEO readiness, concurrently.

        Args:
            pages: List of dicts with keys: url, html_content, structured_data
            target_engine: Weight profile applied to every page (see analyze_page)

        Returns:
            GEOReport with global score, dimensions, and page results
        """
        results = await asyncio.gather(
            *(
                self.analyze_page(
                    url=page.get("url", ""),
                    html_content=page.get("html_content", ""),
                    structured_data=page.get("structured_data", []),
                    target_engine=target_engine,
                )
                for page in pages
            ),
            return_exceptions=True,
        )

        page_results: list[GEOPageResult] = []
        for page, result in zip(pages, results):
            if isinstance(result, Exception):
                logger.error("GEO analysis failed for %s: %s", page.get("url", ""), result)
                page_results.append(
                    GEOPageResult(
                        url=page.get("url", ""),
                        geo_score=0,
                        ai_readability=0,
                        schema_coverage=0,
                        faq_completeness=0,
                        eeat_score=0,
                        issues=[f"Analysis failed: {result}"],
                    )
                )
            else:
                page_results.append(cast(GEOPageResult, result))

        # Compute global score (average of page scores)
        if page_results:
            global_score = int(sum(r.geo_score for r in page_results) / len(page_results))
        else:
            global_score = 0

        grade = self._compute_grade(global_score)

        # Aggregate dimensions across all pages
        dimensions = self._aggregate_dimensions(page_results)

        # Aggregate unique recommendations
        all_recommendations = []
        seen_recs = set()
        for result in page_results:
            for rec in result.recommendations:
                if rec not in seen_recs:
                    seen_recs.add(rec)
                    all_recommendations.append(rec)

        # Optional LLM enrichment
        if self.llm:
            try:
                enriched = await self._enrich_with_llm(
                    global_score, grade, dimensions, page_results
                )
                if enriched:
                    all_recommendations = enriched + all_recommendations
            except Exception as e:
                logger.warning("LLM enrichment failed: %s", e)

        return GEOReport(
            geo_score=global_score,
            grade=grade,
            dimensions=dimensions,
            page_results=page_results,
            recommendations=all_recommendations[:20],
        )

    def _compute_grade(self, score: int) -> str:
        """Convert numeric score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _aggregate_dimensions(self, page_results: list[GEOPageResult]) -> list[GEODimension]:
        """Aggregate dimension scores across all analyzed pages."""
        if not page_results:
            return []

        count = len(page_results)

        avg_readability = int(sum(r.ai_readability for r in page_results) / count)
        avg_schema = int(sum(r.schema_coverage for r in page_results) / count)
        avg_eeat = int(sum(r.eeat_score for r in page_results) / count)
        avg_faq = int(sum(r.faq_completeness for r in page_results) / count)
        avg_citation = int(sum(r.citation_readiness for r in page_results) / count)

        return [
            GEODimension(
                name="ai_readability",
                score=avg_readability,
                weight=self.WEIGHTS["ai_readability"],
                details={"pages_analyzed": count},
                issues=[
                    issue
                    for r in page_results
                    for issue in r.issues
                    if "readab" in issue.lower()
                    or "sentence" in issue.lower()
                    or "factual" in issue.lower()
                    or "direct answer" in issue.lower()
                ][:5],
            ),
            GEODimension(
                name="schema_coverage",
                score=avg_schema,
                weight=self.WEIGHTS["schema_coverage"],
                details={"pages_analyzed": count},
                issues=[
                    issue
                    for r in page_results
                    for issue in r.issues
                    if "schema" in issue.lower()
                    or "structured data" in issue.lower()
                    or "speakable" in issue.lower()
                    or "markup" in issue.lower()
                ][:5],
            ),
            GEODimension(
                name="eeat",
                score=avg_eeat,
                weight=self.WEIGHTS["eeat"],
                details={"pages_analyzed": count},
                issues=[
                    issue
                    for r in page_results
                    for issue in r.issues
                    if "author" in issue.lower()
                    or "trust" in issue.lower()
                    or "citation" in issue.lower()
                    or "experience" in issue.lower()
                    or "e-e-a-t" in issue.lower()
                ][:5],
            ),
            GEODimension(
                name="faq_completeness",
                score=avg_faq,
                weight=self.WEIGHTS["faq_completeness"],
                details={"pages_analyzed": count},
                issues=[
                    issue
                    for r in page_results
                    for issue in r.issues
                    if "faq" in issue.lower()
                    or "question" in issue.lower()
                    or "answer" in issue.lower()
                ][:5],
            ),
            GEODimension(
                name="citation_readiness",
                score=avg_citation,
                weight=self.WEIGHTS["citation_readiness"],
                details={"pages_analyzed": count},
                issues=[
                    issue
                    for r in page_results
                    for issue in r.issues
                    if "citation" in issue.lower()
                    or "quotable" in issue.lower()
                    or "statistic" in issue.lower()
                    or "answer-first" in issue.lower()
                    or "sourcing" in issue.lower()
                ][:5],
            ),
        ]

    async def _enrich_with_llm(
        self,
        global_score: int,
        grade: str,
        dimensions: list[GEODimension],
        page_results: list[GEOPageResult],
    ) -> list[str]:
        """Use LLM to generate enriched recommendations."""
        assert self.llm is not None  # only called inside an `if self.llm:` guard
        geo_data = {
            "geo_score": global_score,
            "grade": grade,
            "dimensions": [
                {"name": d.name, "score": d.score, "issues": d.issues} for d in dimensions
            ],
            "page_scores": [
                {"url": r.url, "geo_score": r.geo_score, "issues": r.issues[:3]}
                for r in page_results[:5]
            ],
        }

        prompt = build_geo_analysis_prompt(geo_data)
        response = await self.llm.complete_json(
            system_prompt=(
                "You are a GEO expert. Provide actionable recommendations "
                "to improve AI search engine visibility."
            ),
            user_prompt=prompt,
        )

        if isinstance(response, dict):
            raw_recs = response.get("recommendations", [])
            # Normalize: LLM may return list of dicts or list of strings
            result = []
            for rec in raw_recs:
                if isinstance(rec, str):
                    result.append(rec)
                elif isinstance(rec, dict):
                    # Extract readable text from various LLM response formats
                    text = (
                        rec.get("recommendation")
                        or rec.get("description")
                        or rec.get("text")
                        or rec.get("action")
                    )
                    if not text:
                        # Handle {"area": "...", "actions": [...]} format
                        actions = rec.get("actions", [])
                        area = rec.get("area", "")
                        priority = rec.get("priority", "")
                        if actions:
                            prefix = f"[{priority}] " if priority else ""
                            area_prefix = f"({area}) " if area else ""
                            text = f"{prefix}{area_prefix}{actions[0]}"
                        else:
                            text = str(rec)
                    result.append(text)
            return result

        return []
