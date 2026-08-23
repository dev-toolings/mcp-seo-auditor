"""MCP protocol integration tests using fastmcp.Client."""

import pytest
from fastmcp import Client

from seo_server.server import mcp


@pytest.fixture
def client():
    """Create an in-memory MCP client."""
    return Client(mcp)


@pytest.mark.integration
class TestMCPProtocol:
    # Single source of truth for this file — the count is derived from the set so
    # the two assertions can never drift apart again (the previous version expected
    # 15 tools while listing 15 names that omitted seo_fix).
    EXPECTED_TOOLS = {
        "seo_audit",
        "seo_analyze",
        "seo_site",
        "seo_crawl",
        "seo_geo",
        "seo_monitor",
        "seo_serp",
        "seo_strategy",
        "seo_content",
        "seo_market",
        "seo_fix",
        "seo_logs",
        "gsc_manage",
        "gsc_analytics",
        "seo_agent",
    }

    async def test_list_tools_count_matches_expected(self, client):
        async with client:
            tools = await client.list_tools()
            assert len(tools) == len(self.EXPECTED_TOOLS)

    async def test_tool_names(self, client):
        async with client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            assert names == self.EXPECTED_TOOLS

    async def test_tools_have_descriptions(self, client):
        async with client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description, f"Tool {tool.name} has no description"

    async def test_tools_have_input_schema(self, client):
        async with client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.inputSchema, f"Tool {tool.name} has no inputSchema"
