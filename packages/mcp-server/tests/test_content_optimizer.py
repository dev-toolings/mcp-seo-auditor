"""Tests for ContentOptimizerService."""

import pytest

from app.services.ai.content_optimizer import ContentOptimizerService


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
def optimizer():
    return ContentOptimizerService(MockAIAnalyzer(), MockEditorialContext())


@pytest.mark.asyncio
async def test_optimize_without_llm_returns_deterministic(optimizer):
    """optimize() without LLM returns deterministic recommendations."""
    content = "<h1>SEO Guide</h1><p>This is a short page about SEO.</p>"
    result = await optimizer.optimize(content=content, keywords=["seo", "ranking"])

    assert result["ai_enhanced"] is False
    assert isinstance(result["changes"], list)
    assert result["optimized_content"] == content


@pytest.mark.asyncio
async def test_optimize_returns_expected_keys(optimizer):
    """optimize() returns all expected keys."""
    result = await optimizer.optimize(content="Some content.")

    expected_keys = {"optimized_content", "changes", "score_before", "score_after", "ai_enhanced"}
    assert expected_keys == set(result.keys())


@pytest.mark.asyncio
async def test_optimize_empty_content(optimizer):
    """optimize() with empty content returns appropriate result."""
    result = await optimizer.optimize(content="")

    assert result["ai_enhanced"] is False
    assert result["optimized_content"] == ""
    assert result["score_before"] == 0.0
    assert result["score_after"] == 0.0
    assert len(result["changes"]) > 0
    assert "empty" in result["changes"][0]["rationale"].lower()


@pytest.mark.asyncio
async def test_optimize_detects_missing_keywords(optimizer):
    """optimize() flags keywords absent from content."""
    content = "<h1>Guide complet</h1><p>Voici un article sur le marketing digital.</p>"
    result = await optimizer.optimize(content=content, keywords=["seo", "referencement"])

    keyword_changes = [c for c in result["changes"] if c["type"] == "keyword_added"]
    assert len(keyword_changes) == 2


@pytest.mark.asyncio
async def test_optimize_detects_missing_headings(optimizer):
    """optimize() flags missing H1/H2 when absent."""
    content = "Just plain text without any headings or structure at all."
    result = await optimizer.optimize(content=content)

    heading_changes = [c for c in result["changes"] if c["type"] == "heading_rewritten"]
    assert len(heading_changes) >= 1


@pytest.mark.asyncio
async def test_optimize_thin_content_warning(optimizer):
    """optimize() warns about thin content."""
    content = "Short page."
    result = await optimizer.optimize(content=content)

    thin_changes = [c for c in result["changes"] if "thin" in c["rationale"].lower()]
    assert len(thin_changes) >= 1


@pytest.mark.asyncio
async def test_optimize_scores_are_floats(optimizer):
    """optimize() scores are floats."""
    result = await optimizer.optimize(content="Some content here for testing.")

    assert isinstance(result["score_before"], float)
    assert isinstance(result["score_after"], float)
