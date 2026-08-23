"""Integration tests for seo_content tool — action routing and service wiring.

Cannot import seo_server.tools.content directly (requires fastmcp).
We mock fastmcp + seo_server.server at module level before any tool import.
"""

import importlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seo_server.schemas.content import SeoContentInput

# ── Mock fastmcp + server BEFORE importing any tool ──────

# 1. fastmcp itself
_fake_fastmcp = types.ModuleType("fastmcp")
_fake_fastmcp.FastMCP = MagicMock()
sys.modules.setdefault("fastmcp", _fake_fastmcp)

# 2. seo_server.server — needs to expose mcp with a no-op @mcp.tool decorator
_fake_mcp = MagicMock()
_fake_mcp.tool = lambda **kw: lambda fn: fn

if "seo_server.server" in sys.modules:
    # Already imported (unlikely without fastmcp, but be safe)
    sys.modules["seo_server.server"].mcp = _fake_mcp
else:
    _fake_server = types.ModuleType("seo_server.server")
    _fake_server.mcp = _fake_mcp
    sys.modules["seo_server.server"] = _fake_server

# 3. Now we can import the tools package + content module
#    The __init__.py will import all tool modules, each using the fake mcp.tool
if "seo_server.tools" in sys.modules:
    importlib.reload(sys.modules["seo_server.tools"])

from seo_server.tools.content import seo_content  # noqa: E402

# ── Fixtures ─────────────────────────────────────────


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


class MockServiceContext:
    """Minimal mock of ServiceContext with content services."""

    def __init__(self):
        ai = MockAIAnalyzer()
        editorial = MockEditorialContext()

        from app.services.ai.content_optimizer import ContentOptimizerService
        from app.services.ai.content_writer import ContentWriterService
        from app.services.ai.meta_generator import MetaGeneratorService

        self.content_writer = ContentWriterService(ai, editorial)
        self.content_optimizer = ContentOptimizerService(ai, editorial)
        self.meta_generator = MetaGeneratorService(ai, editorial)

        # Mock crawler — returns empty list by default
        self.crawler = MagicMock()
        self.crawler.crawl_pages = AsyncMock(return_value=[])

        # Mock content_brief
        self.content_brief = MagicMock()
        self.content_brief.generate = AsyncMock(
            return_value={
                "brief": "test brief",
                "ai_enhanced": False,
            }
        )


@pytest.fixture(autouse=True)
def mock_ctx():
    """Patch svc.ctx with our mock service context for all tests."""
    ctx = MockServiceContext()
    with patch("seo_server.tools.content.svc") as mock_svc:
        mock_svc.ctx = ctx
        yield ctx


# ── Action routing ───────────────────────────────────


class TestActionRouting:
    @pytest.mark.asyncio
    async def test_route_write(self, mock_ctx):
        inp = SeoContentInput(action="write", target_keyword="test seo")
        result = await seo_content(inp)
        assert "error" not in result
        assert "article" in result

    @pytest.mark.asyncio
    async def test_route_optimize(self, mock_ctx):
        inp = SeoContentInput(action="optimize", content="Some text", target_keyword="seo")
        result = await seo_content(inp)
        assert "error" not in result
        assert "optimized_content" in result

    @pytest.mark.asyncio
    async def test_route_meta(self, mock_ctx):
        inp = SeoContentInput(action="meta", target_keyword="test keyword")
        result = await seo_content(inp)
        assert "error" not in result
        assert "titles" in result

    @pytest.mark.asyncio
    async def test_route_headlines(self, mock_ctx):
        inp = SeoContentInput(action="headlines", target_keyword="seo audit")
        result = await seo_content(inp)
        assert "error" not in result
        assert "headlines" in result

    @pytest.mark.asyncio
    async def test_route_humanize(self, mock_ctx):
        inp = SeoContentInput(action="humanize", content="AI generated text.")
        result = await seo_content(inp)
        assert "error" not in result
        assert "humanized_content" in result

    @pytest.mark.asyncio
    async def test_route_research(self, mock_ctx):
        inp = SeoContentInput(action="research", target_keyword="seo tools")
        result = await seo_content(inp)
        assert "error" not in result
        assert "brief" in result

    def test_unknown_action_rejected_by_schema(self):
        """Unknown action handled via schema validation (Literal type)."""
        with pytest.raises(Exception):
            SeoContentInput(action="bogus")


# ── Input validation ─────────────────────────────────


class TestInputValidation:
    @pytest.mark.asyncio
    async def test_write_requires_keyword(self, mock_ctx):
        inp = SeoContentInput(action="write")
        result = await seo_content(inp)
        assert "error" in result
        assert "target_keyword" in result["error"]

    @pytest.mark.asyncio
    async def test_optimize_requires_content(self, mock_ctx):
        inp = SeoContentInput(action="optimize", target_keyword="seo")
        result = await seo_content(inp)
        assert "error" in result
        assert "content" in result["error"]

    @pytest.mark.asyncio
    async def test_meta_requires_keyword_or_url(self, mock_ctx):
        inp = SeoContentInput(action="meta")
        result = await seo_content(inp)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_headlines_requires_keyword(self, mock_ctx):
        inp = SeoContentInput(action="headlines")
        result = await seo_content(inp)
        assert "error" in result
        assert "target_keyword" in result["error"]

    @pytest.mark.asyncio
    async def test_humanize_requires_content(self, mock_ctx):
        inp = SeoContentInput(action="humanize")
        result = await seo_content(inp)
        assert "error" in result
        assert "content" in result["error"]

    @pytest.mark.asyncio
    async def test_research_requires_keyword(self, mock_ctx):
        inp = SeoContentInput(action="research")
        result = await seo_content(inp)
        assert "error" in result
        assert "target_keyword" in result["error"]


# ── Service call correctness ─────────────────────────


class TestServiceWiring:
    @pytest.mark.asyncio
    async def test_write_returns_article_structure(self, mock_ctx):
        inp = SeoContentInput(
            action="write",
            target_keyword="audit seo",
            language="fr",
            word_count=2000,
        )
        result = await seo_content(inp)
        assert result["ai_enhanced"] is False  # No LLM in test
        assert result["language"] == "fr"
        assert "audit seo" in result["article"].lower()
        assert result["word_count"] == 2000

    @pytest.mark.asyncio
    async def test_optimize_returns_changes(self, mock_ctx):
        inp = SeoContentInput(
            action="optimize",
            content="Short text about nothing.",
            target_keyword="missing keyword",
        )
        result = await seo_content(inp)
        assert result["ai_enhanced"] is False
        assert isinstance(result["changes"], list)
        assert len(result["changes"]) > 0  # Thin content + missing keyword

    @pytest.mark.asyncio
    async def test_meta_returns_titles_and_descriptions(self, mock_ctx):
        inp = SeoContentInput(action="meta", target_keyword="seo tools")
        result = await seo_content(inp)
        assert result["ai_enhanced"] is False
        assert len(result["titles"]) == 5
        assert len(result["descriptions"]) == 5
        assert "best_combination" in result

    @pytest.mark.asyncio
    async def test_headlines_returns_scored_list(self, mock_ctx):
        inp = SeoContentInput(action="headlines", target_keyword="seo audit")
        result = await seo_content(inp)
        assert result["ai_enhanced"] is False
        assert len(result["headlines"]) >= 10
        assert "top_3_picks" in result
        for h in result["headlines"]:
            assert "headline" in h
            assert "score" in h

    @pytest.mark.asyncio
    async def test_humanize_returns_unchanged(self, mock_ctx):
        original = "Some content to humanize."
        inp = SeoContentInput(action="humanize", content=original)
        result = await seo_content(inp)
        assert result["ai_enhanced"] is False
        assert result["humanized_content"] == original
        assert result["changes_made"] == []

    @pytest.mark.asyncio
    async def test_research_calls_content_brief(self, mock_ctx):
        inp = SeoContentInput(
            action="research",
            target_keyword="seo tools",
            target_url="https://example.com",
            language="en",
        )
        result = await seo_content(inp)
        assert result["brief"] == "test brief"
        assert result["ai_enhanced"] is False
        assert result["_meta"]["tool"] == "seo_content"
        assert result["_meta"]["action"] == "research"
        mock_ctx.content_brief.generate.assert_awaited_once_with(
            target_url="https://example.com",
            target_keyword="seo tools",
            language="en",
        )


# ── Error handling ───────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_write_exception_returns_error(self, mock_ctx):
        mock_ctx.content_writer = MagicMock()
        mock_ctx.content_writer.write = AsyncMock(side_effect=RuntimeError("LLM boom"))
        inp = SeoContentInput(action="write", target_keyword="test")
        result = await seo_content(inp)
        assert "error" in result
        assert "LLM boom" in result["error"]

    @pytest.mark.asyncio
    async def test_optimize_exception_returns_error(self, mock_ctx):
        mock_ctx.content_optimizer = MagicMock()
        mock_ctx.content_optimizer.optimize = AsyncMock(side_effect=ValueError("bad"))
        inp = SeoContentInput(action="optimize", content="text", target_keyword="kw")
        result = await seo_content(inp)
        assert "error" in result
        assert "bad" in result["error"]

    @pytest.mark.asyncio
    async def test_meta_crawler_failure_still_generates(self, mock_ctx):
        """If crawler fails, meta should still generate from keyword alone."""
        mock_ctx.crawler.crawl_pages = AsyncMock(side_effect=RuntimeError("no browser"))
        inp = SeoContentInput(
            action="meta",
            target_keyword="seo audit",
            target_url="https://example.com",
        )
        result = await seo_content(inp)
        assert "error" not in result
        assert "titles" in result

    @pytest.mark.asyncio
    async def test_headlines_exception_returns_error(self, mock_ctx):
        mock_ctx.meta_generator = MagicMock()
        mock_ctx.meta_generator.generate_headlines = AsyncMock(side_effect=RuntimeError("fail"))
        inp = SeoContentInput(action="headlines", target_keyword="test")
        result = await seo_content(inp)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_humanize_exception_returns_error(self, mock_ctx):
        mock_ctx.content_writer = MagicMock()
        mock_ctx.content_writer.humanize = AsyncMock(side_effect=RuntimeError("fail"))
        inp = SeoContentInput(action="humanize", content="text")
        result = await seo_content(inp)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_research_exception_returns_error(self, mock_ctx):
        mock_ctx.content_brief = MagicMock()
        mock_ctx.content_brief.generate = AsyncMock(side_effect=RuntimeError("fail"))
        inp = SeoContentInput(action="research", target_keyword="kw")
        result = await seo_content(inp)
        assert "error" in result
