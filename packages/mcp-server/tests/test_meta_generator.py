"""Tests for MetaGeneratorService — deterministic fallback and structure validation."""

import pytest

from app.services.ai.meta_generator import MetaGeneratorService

# ── Mocks ──────────────────────────────────────────────────────────────


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

    def get_full_context(self):
        return {
            "brand_voice": "",
            "style_guide": "",
            "internal_links": "",
            "target_keywords": "",
            "competitor_analysis": "",
        }


@pytest.fixture
def service():
    return MetaGeneratorService(MockAIAnalyzer(), MockEditorialContext())


# ── generate_meta: structure ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_meta_returns_expected_keys(service):
    result = await service.generate_meta("gestion de projet")
    assert "titles" in result
    assert "descriptions" in result
    assert "best_combination" in result
    assert "ai_enhanced" in result


@pytest.mark.asyncio
async def test_generate_meta_fallback_ai_enhanced_false(service):
    result = await service.generate_meta("gestion de projet")
    assert result["ai_enhanced"] is False


@pytest.mark.asyncio
async def test_generate_meta_returns_5_titles(service):
    result = await service.generate_meta("gestion de projet")
    assert len(result["titles"]) == 5


@pytest.mark.asyncio
async def test_generate_meta_returns_5_descriptions(service):
    result = await service.generate_meta("gestion de projet")
    assert len(result["descriptions"]) == 5


@pytest.mark.asyncio
async def test_generate_meta_titles_max_60_chars(service):
    kw = "gestion de projet et optimisation des performances digitales"
    result = await service.generate_meta(kw)
    for t in result["titles"]:
        assert len(t["title"]) <= 60, f"Title too long ({len(t['title'])}): {t['title']}"


@pytest.mark.asyncio
async def test_generate_meta_descriptions_max_155_chars(service):
    kw = "gestion de projet et optimisation des performances digitales"
    result = await service.generate_meta(kw)
    for d in result["descriptions"]:
        assert len(d["description"]) <= 155, (
            f"Description too long ({len(d['description'])}): {d['description']}"
        )


@pytest.mark.asyncio
async def test_generate_meta_title_structure(service):
    result = await service.generate_meta("SEO")
    for t in result["titles"]:
        assert "title" in t
        assert "length" in t
        assert "ctr_score" in t
        assert "strategy" in t
        assert t["length"] == len(t["title"])


@pytest.mark.asyncio
async def test_generate_meta_description_structure(service):
    result = await service.generate_meta("SEO")
    for d in result["descriptions"]:
        assert "description" in d
        assert "length" in d
        assert "ctr_score" in d
        assert "strategy" in d
        assert d["length"] == len(d["description"])


@pytest.mark.asyncio
async def test_generate_meta_best_combination_structure(service):
    result = await service.generate_meta("SEO")
    best = result["best_combination"]
    assert "title" in best
    assert "description" in best
    assert "rationale" in best
    assert best["title"]  # non-empty
    assert best["description"]  # non-empty


@pytest.mark.asyncio
async def test_generate_meta_with_minimal_inputs(service):
    """Just a keyword, no URL or page_data."""
    result = await service.generate_meta("python")
    assert result["ai_enhanced"] is False
    assert len(result["titles"]) == 5
    assert len(result["descriptions"]) == 5


@pytest.mark.asyncio
async def test_generate_meta_with_url_and_page_data(service):
    result = await service.generate_meta(
        target_keyword="Django",
        target_url="https://example.com/django",
        page_data={"h1": "Learn Django"},
    )
    assert result["ai_enhanced"] is False
    assert len(result["titles"]) == 5


# ── generate_headlines: structure ──────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_headlines_returns_expected_keys(service):
    result = await service.generate_headlines("améliorer son SEO")
    assert "headlines" in result
    assert "top_3_picks" in result
    assert "ai_enhanced" in result


@pytest.mark.asyncio
async def test_generate_headlines_fallback_ai_enhanced_false(service):
    result = await service.generate_headlines("améliorer son SEO")
    assert result["ai_enhanced"] is False


@pytest.mark.asyncio
async def test_generate_headlines_returns_10_headlines(service):
    result = await service.generate_headlines("améliorer son SEO")
    assert len(result["headlines"]) >= 10


@pytest.mark.asyncio
async def test_generate_headlines_returns_top_3(service):
    result = await service.generate_headlines("améliorer son SEO")
    assert len(result["top_3_picks"]) == 3


@pytest.mark.asyncio
async def test_generate_headlines_headline_structure(service):
    result = await service.generate_headlines("marketing digital")
    for h in result["headlines"]:
        assert "headline" in h
        assert "score" in h
        assert "emotional_trigger" in h
        assert "formula" in h
        assert "best_for" in h


@pytest.mark.asyncio
async def test_generate_headlines_top_pick_structure(service):
    result = await service.generate_headlines("marketing digital")
    for p in result["top_3_picks"]:
        assert "headline" in p
        assert "rationale" in p
        assert p["headline"]  # non-empty
        assert p["rationale"]  # non-empty


@pytest.mark.asyncio
async def test_generate_headlines_with_empty_keywords(service):
    result = await service.generate_headlines("refonte de site web", keywords=[])
    assert result["ai_enhanced"] is False
    assert len(result["headlines"]) >= 10


@pytest.mark.asyncio
async def test_generate_headlines_with_keywords(service):
    result = await service.generate_headlines(
        "refonte de site web", keywords=["migration SEO", "redesign"]
    )
    assert result["ai_enhanced"] is False
    assert len(result["headlines"]) >= 10
