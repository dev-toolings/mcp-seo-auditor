"""Content brief generation service."""

import logging
import re

from app.services.ai.ai_analyzer import AIAnalyzer
from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_SEO_ANALYST,
    build_content_brief_prompt,
)

logger = logging.getLogger(__name__)


class ContentBriefService:
    """Generates SEO content briefs for target pages and keywords."""

    def __init__(self, crawler, structured_data_validator, ai_analyzer: AIAnalyzer):
        self.crawler = crawler
        self.sd_validator = structured_data_validator
        self.ai = ai_analyzer

    async def generate(
        self,
        target_url: str,
        target_keyword: str,
        language: str = "en",
    ) -> dict:
        """Generate an SEO content brief.

        1. Crawl the target URL for current content analysis
        2. Analyze current content (word count, headings, keywords)
        3. Check structured data
        4. If LLM available: generate comprehensive brief
        5. If no LLM: template-based brief with data
        """
        # 1. Crawl the target URL
        pages = await self.crawler.crawl_pages([target_url])
        page = pages[0] if pages else None

        page_data = {}
        if page and page.status_code == 200:
            page_data = {
                "url": page.url,
                "title": page.title,
                "meta_description": page.meta_description,
                "h1": page.h1,
                "word_count": page.word_count,
                "structured_data": page.structured_data,
                "internal_links_count": len(page.internal_links),
            }

            # Extract heading structure from content
            page_data["headings"] = self._extract_headings(page.content)
        else:
            page_data = {
                "url": target_url,
                "title": None,
                "word_count": 0,
                "note": "Page could not be crawled",
            }

        # 2. Check structured data
        sd_result = {}
        if page and page.status_code == 200:
            try:
                report = self.sd_validator.validate_page(page.url, page.structured_data)
                sd_result = self.sd_validator.to_dict(report)
            except Exception as e:
                logger.warning("Structured data check failed: %s", e)

        # 3. Build keyword data for the brief
        keyword_data = {
            "target_keyword": target_keyword,
            "language": language,
            "current_page": page_data,
            "structured_data_status": sd_result,
        }

        # 4. Try LLM-enhanced brief
        if self.ai.ai_available:
            assert self.ai.llm is not None  # ai_available guarantees a provider
            try:
                prompt = build_content_brief_prompt(keyword_data)
                brief = await self.ai.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
                if isinstance(brief, dict):
                    brief["ai_enhanced"] = True
                    brief["current_page_analysis"] = page_data
                    return brief
            except Exception as e:
                logger.warning("LLM content brief failed: %s", e)

        # 5. Deterministic fallback
        return self._deterministic_brief(target_url, target_keyword, page_data, sd_result, language)

    def _extract_headings(self, html_content: str) -> list[dict]:
        """Extract heading structure from HTML content."""
        headings: list[dict] = []
        if not html_content:
            return headings

        pattern = re.compile(r"<(h[1-6])[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(html_content):
            tag = match.group(1).lower()
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if text:
                headings.append({"level": tag, "text": text})

        return headings

    def _deterministic_brief(
        self,
        target_url: str,
        target_keyword: str,
        page_data: dict,
        sd_result: dict,
        language: str,
    ) -> dict:
        """Generate a template-based content brief without LLM."""
        current_word_count = page_data.get("word_count", 0)
        has_h1 = bool(page_data.get("h1"))
        has_meta = bool(page_data.get("meta_description"))
        headings = page_data.get("headings", [])
        h2_count = sum(1 for h in headings if h.get("level") == "h2")

        # Target word count recommendation
        if current_word_count < 300:
            target_length = [1200, 2000]
            content_gap = "Page has very thin content. Significant expansion needed."
        elif current_word_count < 800:
            target_length = [1500, 2500]
            content_gap = "Page content is below average length. Consider expanding key sections."
        else:
            target_length = [current_word_count, int(current_word_count * 1.3)]
            content_gap = "Content length is adequate. Focus on depth and quality."

        # Schema recommendations
        schema_recs = ["Article or WebPage schema"]
        sd_results = sd_result.get("results", [])
        if sd_results:
            existing = sd_results[0].get("schemas", [])
            if not any("FAQ" in str(s) for s in existing):
                schema_recs.append("FAQPage schema for question-answer sections")
            if not any("Breadcrumb" in str(s) for s in existing):
                schema_recs.append("BreadcrumbList schema for navigation")
        else:
            schema_recs.extend(
                [
                    "FAQPage schema for question-answer sections",
                    "BreadcrumbList schema for navigation",
                ]
            )

        # Build outline suggestions
        outline = [
            {
                "heading": f"What is {target_keyword}?",
                "level": "h2",
                "notes": "Define the topic clearly for both users and AI.",
            },
            {
                "heading": f"Key Benefits of {target_keyword}",
                "level": "h2",
                "notes": "List primary advantages with supporting data.",
            },
            {
                "heading": f"How to {target_keyword}",
                "level": "h2",
                "notes": "Step-by-step guide or methodology.",
            },
            {
                "heading": "Frequently Asked Questions",
                "level": "h2",
                "notes": "Address common questions for FAQ schema eligibility.",
            },
        ]

        # Title suggestions
        title_suggestions = [
            f"{target_keyword.title()}: Complete Guide ({_current_year()})",
            f"How to {target_keyword.title()}: Expert Tips & Best Practices",
            f"{target_keyword.title()} - Everything You Need to Know",
        ]

        return {
            "target_keyword": target_keyword,
            "secondary_keywords": [],
            "search_intent": "informational",
            "content_type": "comprehensive guide",
            "title_suggestions": title_suggestions,
            "meta_description": f"Learn everything about {target_keyword}. Our comprehensive guide covers key strategies, best practices, and expert tips.",
            "word_count_range": target_length,
            "outline": outline,
            "faq_questions": [
                f"What is {target_keyword}?",
                f"Why is {target_keyword} important?",
                f"How do you implement {target_keyword}?",
                f"What are common {target_keyword} mistakes?",
            ],
            "schema_recommendations": schema_recs,
            "internal_linking_opportunities": [],
            "content_gap_analysis": content_gap,
            "current_page_analysis": page_data,
            "improvement_suggestions": self._page_improvements(
                page_data, has_h1, has_meta, h2_count
            ),
            "ai_enhanced": False,
        }

    def _page_improvements(
        self, page_data: dict, has_h1: bool, has_meta: bool, h2_count: int
    ) -> list[str]:
        """Identify specific improvements for the current page."""
        improvements = []

        if not has_h1:
            improvements.append("Add an H1 heading that includes the target keyword.")

        if not has_meta:
            improvements.append("Write a compelling meta description (150-160 characters).")

        if h2_count < 3:
            improvements.append(
                "Add more H2 subheadings to improve content structure and scannability."
            )

        word_count = page_data.get("word_count", 0)
        if word_count < 300:
            improvements.append("Significantly expand page content (target 1500+ words).")

        if not page_data.get("structured_data"):
            improvements.append("Add JSON-LD structured data markup.")

        if page_data.get("internal_links_count", 0) < 3:
            improvements.append("Add more internal links to related content.")

        if not improvements:
            improvements.append(
                "Page fundamentals are solid. Focus on content depth and freshness."
            )

        return improvements


def _current_year() -> str:
    """Return current year as string."""
    from datetime import datetime

    return str(datetime.now().year)
