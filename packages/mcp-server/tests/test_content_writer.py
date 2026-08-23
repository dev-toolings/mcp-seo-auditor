"""Tests for ContentWriterService."""

import pytest

from app.services.ai.content_writer import ContentWriterService


class MockLLM:
    def is_available(self):
        return False


class MockAIAnalyzer:
    ai_available = False
    llm = MockLLM()


class MockEditorialContext:
    def get_brand_voice(self):
        return ""

    def get_style_guide(self):
        return ""

    def get_internal_links(self):
        return ""

    def get_target_keywords(self):
        return ""

    def get_full_context(self):
        return {
            "brand_voice": "",
            "style_guide": "",
            "internal_links": "",
            "target_keywords": "",
            "competitor_analysis": "",
        }


@pytest.fixture
def writer():
    return ContentWriterService(MockAIAnalyzer(), MockEditorialContext())


@pytest.mark.asyncio
async def test_write_without_llm_returns_fallback(writer):
    """write() without LLM returns deterministic fallback with correct structure."""
    result = await writer.write(target_keyword="audit seo", language="fr")

    assert result["ai_enhanced"] is False
    assert result["language"] == "fr"
    assert isinstance(result["article"], str)
    assert len(result["article"]) > 0
    assert "audit seo" in result["article"].lower()


@pytest.mark.asyncio
async def test_write_returns_expected_keys(writer):
    """write() returns all expected keys."""
    result = await writer.write(target_keyword="test keyword")

    expected_keys = {"article", "meta", "word_count", "ai_enhanced", "language"}
    assert expected_keys == set(result.keys())


@pytest.mark.asyncio
async def test_write_english_fallback(writer):
    """write() with language='en' returns English outline."""
    result = await writer.write(target_keyword="seo audit", language="en")

    assert result["language"] == "en"
    assert "What is" in result["article"] or "what is" in result["article"].lower()


@pytest.mark.asyncio
async def test_humanize_without_llm_returns_unchanged(writer):
    """humanize() without LLM returns content unchanged with ai_enhanced=False."""
    original = "<p>This is some AI-generated content about SEO.</p>"
    result = await writer.humanize(content=original)

    assert result["ai_enhanced"] is False
    assert result["humanized_content"] == original
    assert result["changes_made"] == []


@pytest.mark.asyncio
async def test_humanize_returns_expected_keys(writer):
    """humanize() returns all expected keys."""
    result = await writer.humanize(content="Some content here.")

    expected_keys = {
        "humanized_content",
        "changes_made",
        "ai_detection_score_before",
        "ai_detection_score_after",
        "ai_enhanced",
    }
    assert expected_keys == set(result.keys())


@pytest.mark.asyncio
async def test_write_respects_word_count_param(writer):
    """write() passes word_count to the brief (visible in fallback)."""
    result = await writer.write(target_keyword="test", word_count=3000)

    assert result["word_count"] == 3000


@pytest.mark.asyncio
async def test_humanize_with_style_override(writer):
    """humanize() accepts style_guide_override without error."""
    result = await writer.humanize(
        content="Content to humanize.",
        style_guide_override="Use short sentences. Be direct.",
    )

    assert result["ai_enhanced"] is False
    assert result["humanized_content"] == "Content to humanize."
