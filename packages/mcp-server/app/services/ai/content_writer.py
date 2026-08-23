"""Content writing service — generates and humanizes SEO articles."""

import logging

from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_CONTENT_WRITER,
    build_content_humanize_prompt,
    build_content_write_prompt,
)
from app.services.llm.token_budget import TokenBudget

logger = logging.getLogger(__name__)


class ContentWriterService:
    """Generates SEO articles from briefs and humanizes AI content."""

    def __init__(self, ai_analyzer, editorial_context):
        self.ai = ai_analyzer
        self.editorial = editorial_context

    async def write(
        self,
        target_keyword: str,
        target_url: str = "",
        language: str = "fr",
        tone: str = "",
        word_count: int = 2500,
    ) -> dict:
        """Generate a full SEO article from a keyword.

        Flow: build brief data -> inject editorial context -> call LLM
        with build_content_write_prompt -> return article.
        If LLM unavailable, return a deterministic structured brief outline.
        """
        brief = {
            "target_keyword": target_keyword,
            "target_url": target_url,
            "language": language,
            "tone": tone,
            "word_count": word_count,
        }

        brand_context = self.editorial.get_brand_voice()
        style_guide = self.editorial.get_style_guide()
        internal_links = self.editorial.get_internal_links()

        if not self.ai.ai_available:
            return self._deterministic_write(brief)

        try:
            # Compress brief data for token budget
            compressed_brief = TokenBudget.prepare_audit_data(brief)
            prompt = build_content_write_prompt(
                compressed_brief,
                brand_context=brand_context,
                style_guide=style_guide,
                internal_links=internal_links,
            )
            # Long-form content needs a larger budget — passed per call so it never
            # mutates the shared config (which races across concurrent completions).
            long_form_max_tokens = max(self.ai.llm.config.max_tokens, 16000)
            result = await self.ai.llm.complete_json(
                SYSTEM_PROMPT_CONTENT_WRITER, prompt, max_tokens=long_form_max_tokens
            )
            if not isinstance(result, dict):
                logger.warning("LLM returned non-dict for write: %s", type(result))
                return self._deterministic_write(brief)

            return {
                "article": result.get("article_html", ""),
                "meta": {
                    "title_tag": result.get("title_tag", ""),
                    "meta_description": result.get("meta_description", ""),
                    "keywords_used": result.get("keywords_used", {}),
                    "faq_schema": result.get("faq_schema"),
                    "readability_score": result.get("readability_score"),
                    "internal_links_placed": result.get("internal_links_placed", []),
                },
                "word_count": result.get("word_count", 0),
                "ai_enhanced": True,
                "language": language,
            }
        except Exception as e:
            logger.warning("LLM content write failed, using fallback: %s", e)
            return self._deterministic_write(brief)

    async def humanize(self, content: str, style_guide_override: str = "") -> dict:
        """Remove AI patterns from content.

        Flow: get style guide from editorial context (or use override)
        -> call LLM with build_content_humanize_prompt -> return humanized content.
        If LLM unavailable, return content unchanged with ai_enhanced=False.
        """
        if not self.ai.ai_available:
            return self._deterministic_humanize(content)

        style_guide = style_guide_override or self.editorial.get_style_guide()

        try:
            prompt = build_content_humanize_prompt(content, style_guide=style_guide)
            result = await self.ai.llm.complete_json(SYSTEM_PROMPT_CONTENT_WRITER, prompt)
            if not isinstance(result, dict):
                logger.warning("LLM returned non-dict for humanize: %s", type(result))
                return self._deterministic_humanize(content)

            return {
                "humanized_content": result.get("humanized_content", content),
                "changes_made": result.get("changes_made", []),
                "ai_detection_score_before": result.get("ai_score_before", 0.0),
                "ai_detection_score_after": result.get("ai_score_after", 0.0),
                "ai_enhanced": True,
            }
        except Exception as e:
            logger.warning("LLM humanize failed, returning unchanged: %s", e)
            return self._deterministic_humanize(content)

    # ── Deterministic fallbacks ──────────────────────

    def _deterministic_write(self, brief: dict) -> dict:
        """Return a structured outline when LLM is unavailable."""
        keyword = brief.get("target_keyword", "")
        language = brief.get("language", "fr")
        target_wc = brief.get("word_count", 2500)

        if language == "fr":
            article = (
                f"<h1>{keyword.title()}</h1>\n"
                f"<h2>Qu'est-ce que {keyword} ?</h2>\n"
                f"<p>[Section a developper — definition et contexte]</p>\n"
                f"<h2>Pourquoi {keyword} est important</h2>\n"
                f"<p>[Section a developper — benefices et enjeux]</p>\n"
                f"<h2>Comment mettre en place {keyword}</h2>\n"
                f"<p>[Section a developper — guide etape par etape]</p>\n"
                f"<h2>Questions frequentes</h2>\n"
                f"<p>[Section a developper — FAQ pour PAA]</p>\n"
            )
        else:
            article = (
                f"<h1>{keyword.title()}</h1>\n"
                f"<h2>What is {keyword}?</h2>\n"
                f"<p>[Section to develop — definition and context]</p>\n"
                f"<h2>Why {keyword} matters</h2>\n"
                f"<p>[Section to develop — benefits and stakes]</p>\n"
                f"<h2>How to implement {keyword}</h2>\n"
                f"<p>[Section to develop — step-by-step guide]</p>\n"
                f"<h2>Frequently Asked Questions</h2>\n"
                f"<p>[Section to develop — FAQ for PAA]</p>\n"
            )

        return {
            "article": article,
            "meta": {
                "title_tag": f"{keyword.title()} — Guide complet"[:60],
                "meta_description": f"Decouvrez tout sur {keyword}. Guide complet avec strategies, bonnes pratiques et conseils d'experts."[
                    :155
                ],
            },
            "word_count": target_wc,
            "ai_enhanced": False,
            "language": language,
        }

    def _deterministic_humanize(self, content: str) -> dict:
        """Return content unchanged when LLM is unavailable."""
        return {
            "humanized_content": content,
            "changes_made": [],
            "ai_detection_score_before": 0.0,
            "ai_detection_score_after": 0.0,
            "ai_enhanced": False,
        }
