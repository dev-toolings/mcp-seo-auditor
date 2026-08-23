"""Surface tests for the MCP tool + prompt registry.

Two guarantees, both derived from the live registry rather than a copy of the code:

1. The registered tools and their ``action`` enums are the ones we intend to ship
   (post-merge: no ``seo_rank``, no ``seo_report``).
2. Every prompt template calls the tools with arguments that actually validate
   against those tools' Pydantic schemas. Prompts are plain f-strings, so a
   renamed or mistyped argument is invisible until an agent runs the prompt and
   the tool call blows up with a ValidationError. This walks all prompts, parses
   the ``tool(...)`` calls out of the rendered text, and checks them against the
   schema the MCP client sees.
"""

import functools
import importlib
import re
import sys

import pytest


@functools.cache
def _mcp():
    """Load a pristine, fully-registered FastMCP server.

    ``tests/test_tool_content.py`` replaces ``seo_server.server.mcp`` with a MagicMock
    at import time so it can import tool handlers without fastmcp. Importing the module
    here would hand us that mock, so we re-import the package in a scratch namespace and
    put the original modules back for whoever else depends on them.
    """
    saved = {
        name: module
        for name, module in sys.modules.items()
        if name == "seo_server" or name.startswith("seo_server.")
    }
    for name in saved:
        del sys.modules[name]
    try:
        return importlib.import_module("seo_server.server").mcp
    finally:
        sys.modules.update(saved)


# ── Expected tool surface ────────────────────────────

EXPECTED_ACTIONS: dict[str, set[str]] = {
    "seo_agent": {
        "start",
        "status",
        "approve",
        "reject",
        "resume",
        "cancel",
        "cleanup",
        "runtime",
        "skills_plan",
        "skills_apply",
    },
    "gsc_analytics": {
        "query",
        "compare",
        "cannibalization",
        "sitemap_health",
        "ai_queries",
        "ai_traffic",
    },
    "gsc_manage": {"sites", "sitemaps", "inspect", "index"},
    "seo_analyze": {"content", "technical", "structured_data", "eeat", "cwv"},
    "seo_content": {"write", "optimize", "meta", "headlines", "humanize", "research"},
    "seo_crawl": {"list", "get", "compare", "trends", "alerts"},
    "seo_fix": {"schema", "meta", "robots_txt", "llms_txt"},
    "seo_logs": {"analyze", "bots", "waste", "ai_bots"},
    "seo_market": {
        "research",
        "trends",
        "competitors",
        "niches",
        "volumes",
        "insights",
        "viability",
    },
    "seo_monitor": {"anomalies", "detect", "verify"},
    "seo_serp": {"predict", "live", "track", "history", "dashboard"},
    "seo_site": {
        "sitemap",
        "links",
        "cannibalization",
        "indexation_leaks",
        "topical_authority",
        "robots",
        "migration",
    },
    "seo_strategy": {
        "action_plan",
        "roadmap",
        "competitor_gap",
        "content_plan",
        "quick_wins",
        "priorities",
    },
}

# Tools without an action router (single-purpose).
ACTIONLESS_TOOLS = {"seo_audit", "seo_geo"}

EXPECTED_TOOLS = set(EXPECTED_ACTIONS) | ACTIONLESS_TOOLS

# Merged away — must never come back as separate tools.
REMOVED_TOOLS = {"seo_rank", "seo_report"}

PROMPT_MODULES = 10
PROMPTS_PER_MODULE = 5


# ── Registry helpers ─────────────────────────────────


async def _tool_schemas() -> dict[str, dict]:
    """Map tool name -> the flattened JSON schema of its ``input`` model.

    This is the schema an MCP client validates against, so the prompt checks
    below test exactly what an agent would hit at runtime.
    """
    tools = await _mcp().list_tools()
    return {t.name: t.parameters["properties"]["input"] for t in tools}


def _render_args(prompt) -> dict[str, str]:
    """Placeholder values for a prompt's required arguments."""
    return {arg.name: f"<{arg.name}>" for arg in (prompt.arguments or []) if arg.required}


def _message_text(result) -> str:
    """Flatten a rendered PromptResult into plain text."""
    parts = []
    for message in result.messages:
        content = message.content
        parts.append(content if isinstance(content, str) else getattr(content, "text", ""))
    return "\n".join(parts)


# ── Tool-call parsing ────────────────────────────────

_KWARG_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _split_call(text: str, start: int) -> tuple[str, int] | None:
    """Return the argument string of the call whose ``(`` sits at ``start``.

    Walks forward tracking bracket depth and quotes so nested lists such as
    ``urls=["a", "b"]`` don't terminate the call early.
    """
    depth = 0
    quote = None
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i
    return None


def _top_level_kwargs(args: str) -> set[str]:
    """Argument names passed at the top level of a call."""
    names = set()
    depth = 0
    quote = None
    segment_start = 0
    segments = []
    for i, ch in enumerate(args):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            segments.append(args[segment_start:i])
            segment_start = i + 1
    segments.append(args[segment_start:])

    for segment in segments:
        match = _KWARG_RE.match(segment.strip())
        if match:
            names.add(match.group(1))
    return names


def _extract_tool_calls(text: str, tool_names: set[str]) -> list[tuple[str, set[str]]]:
    """Find every ``tool_name(...)`` call in ``text`` with its argument names."""
    calls = []
    for name in tool_names:
        for match in re.finditer(rf"\b{re.escape(name)}\s*\(", text):
            split = _split_call(text, match.end() - 1)
            if split is None:
                continue
            calls.append((name, _top_level_kwargs(split[0])))
    return calls


# ── Tool surface ─────────────────────────────────────


class TestToolSurface:
    async def test_registered_tools(self):
        tools = await _mcp().list_tools()
        assert {t.name for t in tools} == EXPECTED_TOOLS

    async def test_merged_tools_are_gone(self):
        tools = await _mcp().list_tools()
        names = {t.name for t in tools}
        assert names.isdisjoint(REMOVED_TOOLS)

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_ACTIONS))
    async def test_tool_exposes_expected_actions(self, tool_name):
        schemas = await _tool_schemas()
        action = schemas[tool_name]["properties"]["action"]
        assert set(action["enum"]) == EXPECTED_ACTIONS[tool_name]

    @pytest.mark.parametrize("tool_name", sorted(ACTIONLESS_TOOLS))
    async def test_actionless_tools_have_no_router(self, tool_name):
        schemas = await _tool_schemas()
        assert "action" not in schemas[tool_name]["properties"]

    async def test_tracking_moved_into_seo_serp(self):
        """seo_rank's persistence actions need site_url, which serp gained on merge."""
        schemas = await _tool_schemas()
        assert "site_url" in schemas["seo_serp"]["properties"]
        assert "days" in schemas["seo_serp"]["properties"]

    async def test_schema_generation_lives_only_in_seo_fix(self):
        """seo_analyze/structured_data is read-only; generation is seo_fix(action='schema')."""
        schemas = await _tool_schemas()
        assert "generate" not in schemas["seo_analyze"]["properties"]
        assert "schema" in schemas["seo_fix"]["properties"]["action"]["enum"]

    async def test_every_tool_has_a_description(self):
        tools = await _mcp().list_tools()
        for tool in tools:
            assert tool.description, f"{tool.name} has no description"


# ── Prompt surface ───────────────────────────────────


class TestPromptSurface:
    async def test_prompt_count(self):
        prompts = await _mcp().list_prompts()
        assert len(prompts) == PROMPT_MODULES * PROMPTS_PER_MODULE

    async def test_prompt_names_are_unique(self):
        prompts = await _mcp().list_prompts()
        names = [p.name for p in prompts]
        assert len(names) == len(set(names))

    async def test_every_prompt_renders(self):
        prompts = await _mcp().list_prompts()
        for prompt in prompts:
            text = _message_text(await prompt.render(_render_args(prompt)))
            assert text.strip(), f"prompt {prompt.name} rendered empty"

    async def test_prompts_reference_existing_tools(self):
        """A prompt must not point at a tool that no longer exists (e.g. seo_rank)."""
        prompts = await _mcp().list_prompts()
        offenders = []
        for prompt in prompts:
            text = _message_text(await prompt.render(_render_args(prompt)))
            for name in REMOVED_TOOLS:
                if re.search(rf"\b{re.escape(name)}\s*\(", text):
                    offenders.append(f"{prompt.name} -> {name}")
        assert not offenders, f"prompts calling removed tools: {offenders}"

    async def test_prompt_tool_calls_match_schemas(self):
        """Every ``tool(...)`` written in a prompt must validate against its schema.

        Catches both halves of the failure mode: unknown argument names (``url=``
        where the schema says ``urls=``) and missing required arguments.
        """
        schemas = await _tool_schemas()
        prompts = await _mcp().list_prompts()
        errors = []

        for prompt in prompts:
            text = _message_text(await prompt.render(_render_args(prompt)))
            for tool_name, kwargs in _extract_tool_calls(text, set(schemas)):
                schema = schemas[tool_name]
                allowed = set(schema.get("properties", {}))
                required = set(schema.get("required", []))

                unknown = kwargs - allowed
                if unknown:
                    errors.append(
                        f"{prompt.name}: {tool_name}() unknown arg(s) {sorted(unknown)} "
                        f"— valid: {sorted(allowed)}"
                    )
                missing = required - kwargs
                if missing:
                    errors.append(
                        f"{prompt.name}: {tool_name}() missing required arg(s) {sorted(missing)}"
                    )

        assert not errors, "prompt/schema mismatches:\n" + "\n".join(errors)

    async def test_prompt_calls_are_actually_found(self):
        """Guard the parser itself — a silent no-match would make the check vacuous."""
        schemas = await _tool_schemas()
        prompts = await _mcp().list_prompts()
        total = 0
        for prompt in prompts:
            text = _message_text(await prompt.render(_render_args(prompt)))
            total += len(_extract_tool_calls(text, set(schemas)))
        assert total > 50, f"only {total} tool calls parsed out of 50 prompts"

    async def test_prompt_actions_exist_on_their_tool(self):
        """``action="foo"`` in a prompt must be a real action of that tool."""
        prompts = await _mcp().list_prompts()
        errors = []
        for prompt in prompts:
            text = _message_text(await prompt.render(_render_args(prompt)))
            for tool_name, actions in EXPECTED_ACTIONS.items():
                for match in re.finditer(
                    rf"\b{re.escape(tool_name)}\s*\(\s*action\s*=\s*\"([^\"]+)\"", text
                ):
                    if match.group(1) not in actions:
                        errors.append(f"{prompt.name}: {tool_name}(action={match.group(1)!r})")
        assert not errors, f"prompts using unknown actions: {errors}"
