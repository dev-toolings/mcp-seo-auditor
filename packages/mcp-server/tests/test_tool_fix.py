"""Tests for the seo_fix WRITE/FIX tool (routing + artifact generation)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from seo_server.schemas.fix import SeoFixInput
from seo_server.tools.fix import seo_fix


class _Ctx:
    def __init__(self):
        self.schema_generator = SimpleNamespace(
            generate=AsyncMock(
                return_value={
                    "detected_page_type": "article",
                    "json_ld": '{"@type": "Article"}',
                    "html_snippet": '<script type="application/ld+json">{}</script>',
                }
            )
        )
        self.crawler = SimpleNamespace(
            crawl_pages=AsyncMock(
                return_value=[
                    SimpleNamespace(
                        url="https://x.com",
                        title="Old Title",
                        meta_description="old desc",
                        status_code=200,
                    )
                ]
            )
        )
        self.meta_generator = SimpleNamespace(
            generate_meta=AsyncMock(
                return_value={
                    "best_combination": {"title": "New Title", "description": "New description"},
                    "ai_enhanced": True,
                }
            )
        )
        self.llms_txt_checker = SimpleNamespace(
            analyze=lambda *a, **k: {
                "score": 60,
                "blocked_citation_bots": ["PerplexityBot"],
                "classification": {"training": [], "search": [], "user": []},
                "llms_txt_present": False,
                "recommended_robots_txt": "User-agent: *\nAllow: /\n",
                "issues": ["PerplexityBot blocked"],
            }
        )
        self.sitemap_parser = SimpleNamespace(
            fetch_all_urls=AsyncMock(
                return_value=[
                    SimpleNamespace(loc="https://x.com/a"),
                    SimpleNamespace(loc="https://x.com/b"),
                ]
            )
        )


@pytest.fixture(autouse=True)
def mock_ctx():
    ctx = _Ctx()
    with patch("seo_server.tools.fix.svc") as mock_svc:
        mock_svc.ctx = ctx
        yield ctx


@pytest.mark.asyncio
async def test_unknown_action():
    # action is validated by the schema Literal, so call the handler with a bad value directly
    inp = SeoFixInput(action="schema", url="https://x.com")
    inp.action = "bogus"
    result = await seo_fix(inp)
    assert "Unknown action" in result["error"]


@pytest.mark.asyncio
async def test_schema_action():
    result = await seo_fix(SeoFixInput(action="schema", url="https://x.com"))
    assert result["action"] == "schema"
    assert "ld+json" in result["injection_snippet"]
    assert result["_meta"]["tool"] == "seo_fix"


@pytest.mark.asyncio
async def test_meta_action_returns_diff():
    result = await seo_fix(SeoFixInput(action="meta", url="https://x.com"))
    assert result["new_title"] == "New Title"
    assert "New description" in result["diff"]
    assert "Old Title" in result["diff"]


@pytest.mark.asyncio
async def test_robots_action_flags_citation_bot():
    with patch("seo_server.tools.fix._fetch_text", new=AsyncMock(return_value="")):
        result = await seo_fix(SeoFixInput(action="robots_txt", url="https://x.com"))
    assert "PerplexityBot" in result["blocked_citation_bots"]
    assert result["action"] == "robots_txt"


@pytest.mark.asyncio
async def test_llms_action_lists_pages():
    result = await seo_fix(SeoFixInput(action="llms_txt", sitemap_url="https://x.com/sitemap.xml"))
    assert result["url_count"] == 2
    assert "https://x.com/a" in result["llms_txt"]
