# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SEO Auditor is a Python MCP server exposing 15 tools and 50 prompts for SEO/GEO analysis, packaged as a monorepo with a single package.

## Repository Structure

```
seo-auditor/
├── packages/
│   └── mcp-server/           # Python 3.11 MCP server (FastMCP 3.0)
│       ├── app/              # Business logic (~35 services)
│       ├── seo_server/       # MCP layer (tools, prompts, schemas)
│       ├── tests/            # pytest test suite
│       ├── Makefile          # Dev commands
│       └── pyproject.toml    # Python package config
├── CLAUDE.md
└── .gitignore
```

## Commands

```bash
# All commands run from packages/mcp-server/
cd packages/mcp-server
make install              # Install Python deps
make test                 # Run pytest
make mcp-test             # List tools + prompts
make run-local            # Start stdio server (for Claude Code)
python -m seo_server.server --transport http  # Start HTTP server

# Linting
ruff check .              # Lint (rules: E, F, I, N, W; line-length 100)
ruff format .             # Format
```

## MCP Server Architecture

All code under `packages/mcp-server/`:

```
seo_server/               # MCP layer (entry point: python -m seo_server.server)
├── server.py             # FastMCP 3.0 server (stdio + streamable-http)
├── service_context.py    # Lazy DI container for all services
├── tools/                # 15 tools, action-routed
└── prompts/              # 50 prompt templates, 10 thematic modules

app/                      # Business logic
├── core/                 # Settings, scoring, exceptions
├── models/               # Pydantic data models
├── services/             # ~35 services (AI, GSC, crawler, market, etc.)
└── repositories/         # SQLite crawl storage
```

## MCP Tools (15)

| Tool            | Description                                             |
| --------------- | ------------------------------------------------------- |
| `seo_audit`     | AI-enhanced full site audit                             |
| `seo_analyze`   | Per-page analysis (content/technical/eeat/cwv)          |
| `seo_site`      | Site-wide analysis from sitemap                         |
| `seo_content`   | Content writing, optimization, meta, brief (`research`) |
| `seo_market`    | Market intelligence + keyword research                  |
| `seo_serp`      | SERP features, live positions, rank tracking            |
| `seo_fix`       | Applyable fixes: JSON-LD, meta, robots.txt, llms.txt    |
| `seo_logs`      | Log file analysis                                       |
| `gsc_manage`    | GSC admin (sites/sitemaps/inspect/index)                |
| `gsc_analytics` | GSC performance analytics                               |
| `seo_strategy`  | AI-powered SEO strategy                                 |
| `seo_geo`       | GEO readiness for AI search                             |
| `seo_monitor`   | Anomaly detection + fix verification                    |
| `seo_crawl`     | Crawl session data access                               |
| `seo_agent`     | Audit-to-PR, runtime diagnostics, managed skill lifecycle |

All action-routed tools use the pattern `tool_name(action="...", ...)`. `seo_audit` and
`seo_geo` are single-purpose and take no `action`.

### Boundaries between overlapping tools

The surface was deliberately deduplicated — keep it that way:

- **Rank tracking lives in `seo_serp`** (`live` / `track` / `history` / `dashboard`). There is
  no separate `seo_rank`: `check` and `live` were the same `serp_analyzer.analyze` call.
- **Content briefs live in `seo_content(action="research")`**, not in `seo_strategy`.
- **Schema *generation* lives in `seo_fix(action="schema")`**, which returns an injectable
  snippet. `seo_analyze(action="structured_data")` only *validates*.
- **There is no `seo_report` tool.** It required passing an audit payload (up to 95k chars)
  back through the model, which is not viable over MCP. Have the client format the
  `seo_audit` result instead.
- **No backlink/netlinking analysis exists**, and none is planned (out of scope + recurring
  API cost). Do not write prompts or tool descriptions that promise it.

## MCP Prompts (50)

10 thematic modules, 5 prompts each: keywords, analytics, competitors, content, technical,
linking, geo, local_seo, ecommerce, reporting.

Prompts are plain f-strings naming the tool calls an agent should make, so a wrong argument
name only fails at runtime. `tests/test_tools_surface.py` parses every rendered prompt and
validates each `tool(...)` call against the live Pydantic schema — run it after touching a
prompt or a tool schema.

## Key Technical Details

- MCP transport: **stdio** (Claude Code) or **streamable-http**
- All services are **async** (httpx — `aiohttp` was removed, it had zero imports)
- Config via `.env` and `app/core/config.py` (Pydantic BaseSettings)
- GSC requires credentials in `credentials/google-credentials.json`
- LLM provider: `LLM_PROVIDER=anthropic|openai|ollama` (auto-detection)
- Browser backend is chosen by `BROWSER_BACKEND=auto|ghostchrome|agent-browser` (`auto`:
  ghostchrome if found, else agent-browser). The agent-browser crawler
  (`app/services/agent_browser_crawler.py`) needs only the `agent-browser` CLI plus its
  Chromium (`agent-browser install`): `read --raw` fast path, then a named `--session`
  (`open` + `eval`, status from the network log), closed in `close()`. It strips secrets
  from the subprocess env and adds `--no-sandbox` under root, Docker or AppArmor userns.
- Ghostchrome crawler (`app/services/browser_crawler.py`) needs two **optional** runtime deps:
  the `ghostchrome` binary in `$PATH` (CLI `fastfetch` fast path) and the `ghostchrome`
  Python SDK (Chrome fallback via `navigate`+`eval`). Both are absent in CI — the tests
  mock the crawler, so they are not required to run the suite. Install the SDK from the
  ghostchrome repo: `pip install <ghostchrome>/sdk/python` (or add its `sdk/python` dir to
  a `.pth`). When either is missing, only the affected pass degrades; the import never fails.
- Autonomous runtime selection is `codex exec` -> `claude -p` -> `grok -p` unless
  `SEO_AGENT_PROVIDER` or `SEO_AGENT_RUNTIME_CONFIG` overrides it. Managed skills use a
  versioned manifest and plan hash; only directories carrying the manager marker may be
  updated or pruned.
