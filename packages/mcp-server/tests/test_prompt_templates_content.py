"""Tests for content creation prompt builders in prompt_templates.py."""

from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_CONTENT_WRITER,
    build_content_humanize_prompt,
    build_content_optimize_prompt,
    build_content_write_prompt,
    build_headline_generation_prompt,
    build_meta_generation_prompt,
)

# ── SYSTEM_PROMPT_CONTENT_WRITER ─────────────────────────────────────


class TestSystemPromptContentWriter:
    def test_is_non_empty_string(self):
        assert isinstance(SYSTEM_PROMPT_CONTENT_WRITER, str)
        assert len(SYSTEM_PROMPT_CONTENT_WRITER) > 100

    def test_distinct_from_analyst(self):
        from app.services.llm.prompt_templates import SYSTEM_PROMPT_SEO_ANALYST

        assert SYSTEM_PROMPT_CONTENT_WRITER != SYSTEM_PROMPT_SEO_ANALYST

    def test_contains_writer_persona_keywords(self):
        prompt = SYSTEM_PROMPT_CONTENT_WRITER.lower()
        assert "content writer" in prompt or "copywriting" in prompt
        assert "french" in prompt and "english" in prompt

    def test_contains_writing_principles(self):
        assert "Writing Principles" in SYSTEM_PROMPT_CONTENT_WRITER
        assert "Output Rules" in SYSTEM_PROMPT_CONTENT_WRITER


# ── build_meta_generation_prompt ─────────────────────────────────────


class TestBuildMetaGenerationPrompt:
    def test_returns_non_empty_string(self):
        result = build_meta_generation_prompt({"url": "https://example.com", "title": "Test"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_expected_sections(self):
        result = build_meta_generation_prompt({"url": "https://example.com"})
        assert "PAGE DATA:" in result
        assert "title_tags" in result
        assert "meta_descriptions" in result
        assert "best_combination" in result
        assert "60 characters" in result or "60 char" in result or "≤60" in result
        assert "155 characters" in result or "155 char" in result or "≤155" in result

    def test_contains_few_shot_example(self):
        result = build_meta_generation_prompt({"url": "https://example.com"})
        assert "EXAMPLE OUTPUT:" in result
        assert "ctr_score" in result

    def test_brand_context_injected(self):
        result = build_meta_generation_prompt(
            {"url": "https://example.com"}, brand_context="We are a SaaS company."
        )
        assert "BRAND CONTEXT:" in result
        assert "We are a SaaS company." in result

    def test_brand_context_absent_when_empty(self):
        result = build_meta_generation_prompt({"url": "https://example.com"}, brand_context="")
        assert "BRAND CONTEXT:" not in result

    def test_with_minimal_inputs(self):
        result = build_meta_generation_prompt({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_page_data_serialized(self):
        result = build_meta_generation_prompt({"url": "https://test.io", "h1": "Hello World"})
        assert "https://test.io" in result
        assert "Hello World" in result


# ── build_headline_generation_prompt ─────────────────────────────────


class TestBuildHeadlineGenerationPrompt:
    def test_returns_non_empty_string(self):
        result = build_headline_generation_prompt("SEO tips", ["seo", "tips"])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_expected_sections(self):
        result = build_headline_generation_prompt("SEO tips", ["seo"])
        assert "TOPIC:" in result
        assert "TARGET KEYWORDS:" in result
        assert "headlines" in result
        assert "conversion_score" in result
        assert "emotional_trigger" in result
        assert "power_words" in result

    def test_contains_headline_strategies(self):
        result = build_headline_generation_prompt("SEO tips", ["seo"])
        assert "HEADLINE STRATEGIES" in result
        assert "POWER WORDS" in result
        assert "listicle" in result or "Number" in result

    def test_brand_context_injected(self):
        result = build_headline_generation_prompt(
            "SEO tips", ["seo"], brand_context="B2B SaaS brand"
        )
        assert "BRAND CONTEXT:" in result
        assert "B2B SaaS brand" in result

    def test_brand_context_absent_when_empty(self):
        result = build_headline_generation_prompt("SEO tips", ["seo"], brand_context="")
        assert "BRAND CONTEXT:" not in result

    def test_with_minimal_inputs(self):
        result = build_headline_generation_prompt("", [])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_keywords_serialized(self):
        result = build_headline_generation_prompt("topic", ["keyword1", "keyword2"])
        assert "keyword1" in result
        assert "keyword2" in result

    def test_topic_in_prompt(self):
        result = build_headline_generation_prompt("Advanced Python Techniques", ["python"])
        assert "Advanced Python Techniques" in result


# ── build_content_humanize_prompt ────────────────────────────────────


class TestBuildContentHumanizePrompt:
    def test_returns_non_empty_string(self):
        result = build_content_humanize_prompt("Some AI-generated text here.")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_ai_patterns_section(self):
        result = build_content_humanize_prompt("Text to humanize.")
        assert "AI PATTERNS TO DETECT AND FIX" in result
        assert "Filler phrases" in result or "filler" in result.lower()
        assert "Robotic transitions" in result or "transitions" in result.lower()

    def test_contains_specific_filler_phrases(self):
        result = build_content_humanize_prompt("Text.")
        assert "It's important to note" in result
        assert "In today's digital landscape" in result
        assert "Let's dive in" in result

    def test_contains_humanization_rules(self):
        result = build_content_humanize_prompt("Text.")
        assert "HUMANIZATION RULES" in result
        assert "humanized_content" in result
        assert "changes_made" in result
        assert "ai_score_before" in result

    def test_style_guide_injected(self):
        result = build_content_humanize_prompt("Text.", style_guide="Tone: casual, use humor.")
        assert "STYLE GUIDE" in result
        assert "Tone: casual, use humor." in result

    def test_style_guide_absent_when_empty(self):
        result = build_content_humanize_prompt("Text.", style_guide="")
        assert "STYLE GUIDE" not in result

    def test_with_minimal_inputs(self):
        result = build_content_humanize_prompt("")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_content_included_in_prompt(self):
        content = "This is a unique test paragraph about machine learning optimization."
        result = build_content_humanize_prompt(content)
        assert content in result


# ── build_content_write_prompt ───────────────────────────────────────


class TestBuildContentWritePrompt:
    def test_returns_non_empty_string(self):
        result = build_content_write_prompt({"target_keyword": "seo audit"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_expected_sections(self):
        result = build_content_write_prompt({"target_keyword": "seo audit"})
        assert "CONTENT BRIEF:" in result
        assert "ARTICLE REQUIREMENTS" in result
        assert "Structure" in result
        assert "SEO Integration" in result
        assert "Content Quality" in result
        assert "Meta Tags" in result

    def test_contains_output_structure(self):
        result = build_content_write_prompt({"target_keyword": "seo"})
        assert "title_tag" in result
        assert "meta_description" in result
        assert "article_html" in result
        assert "word_count" in result
        assert "faq_schema" in result

    def test_specifies_word_count_range(self):
        result = build_content_write_prompt({})
        assert "2000" in result
        assert "3000" in result

    def test_brand_context_injected(self):
        result = build_content_write_prompt({}, brand_context="E-commerce fashion brand")
        assert "BRAND CONTEXT:" in result
        assert "E-commerce fashion brand" in result

    def test_style_guide_injected(self):
        result = build_content_write_prompt({}, style_guide="Professional tone, no slang.")
        assert "STYLE GUIDE:" in result
        assert "Professional tone, no slang." in result

    def test_internal_links_injected(self):
        result = build_content_write_prompt(
            {}, internal_links="/blog/seo-guide -> 'SEO guide'\n/tools -> 'our tools'"
        )
        assert "INTERNAL LINKS TO INTEGRATE:" in result
        assert "/blog/seo-guide" in result

    def test_all_optional_params_absent_when_empty(self):
        result = build_content_write_prompt({})
        assert "BRAND CONTEXT:" not in result
        assert "STYLE GUIDE:" not in result
        assert "INTERNAL LINKS TO INTEGRATE:" not in result

    def test_with_minimal_inputs(self):
        result = build_content_write_prompt({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_brief_data_serialized(self):
        brief = {"target_keyword": "python tutorial", "word_count": [2000, 3000]}
        result = build_content_write_prompt(brief)
        assert "python tutorial" in result


# ── build_content_optimize_prompt ────────────────────────────────────


class TestBuildContentOptimizePrompt:
    def test_returns_non_empty_string(self):
        result = build_content_optimize_prompt("Content here.", {}, ["seo"])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_expected_sections(self):
        result = build_content_optimize_prompt("Content.", {"score": 60}, ["seo"])
        assert "CURRENT CONTENT:" in result
        assert "SEO ANALYSIS:" in result
        assert "TARGET KEYWORDS:" in result
        assert "OPTIMIZATION AREAS" in result

    def test_contains_optimization_areas(self):
        result = build_content_optimize_prompt("Content.", {}, ["seo"])
        assert "Keyword Integration" in result
        assert "Heading Structure" in result
        assert "Content Gaps" in result
        assert "Internal Linking" in result
        assert "Readability" in result

    def test_contains_output_structure(self):
        result = build_content_optimize_prompt("Content.", {}, ["seo"])
        assert "optimization_score" in result
        assert "optimized_content" in result
        assert "changes" in result
        assert "keyword_analysis" in result
        assert "readability_before" in result
        assert "readability_after" in result

    def test_contains_few_shot_example(self):
        result = build_content_optimize_prompt("Content.", {}, ["seo"])
        assert "EXAMPLE CHANGE:" in result

    def test_content_included(self):
        content = "Unique paragraph about technical SEO optimization strategies."
        result = build_content_optimize_prompt(content, {}, ["seo"])
        assert content in result

    def test_seo_analysis_serialized(self):
        analysis = {"overall_score": 65, "issues": ["thin content", "missing h2"]}
        result = build_content_optimize_prompt("Content.", analysis, ["seo"])
        assert "thin content" in result
        assert "missing h2" in result

    def test_keywords_serialized(self):
        result = build_content_optimize_prompt("Content.", {}, ["seo", "audit", "technical"])
        assert "seo" in result
        assert "audit" in result
        assert "technical" in result

    def test_with_minimal_inputs(self):
        result = build_content_optimize_prompt("", {}, [])
        assert isinstance(result, str)
        assert len(result) > 0
