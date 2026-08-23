# MCP SEO Auditor

A production-oriented [Model Context Protocol](https://modelcontextprotocol.io/) server for
SEO, GEO, content, market, SERP, crawl, and Google Search Console workflows.

The server exposes a deliberately compact surface of **15 action-routed tools** and **50 reusable
prompts** over stdio or Streamable HTTP. It also includes an opt-in agentic workflow that can audit
an authorized repository, propose a hash-locked plan, implement it in an isolated Git worktree,
validate the result, and open a pull request.

## What you get

- Site and page audits: technical SEO, content, E-E-A-T, structured data, CWV, internal links,
  cannibalization, robots.txt, and indexation leaks.
- Content and strategy: research, briefs, writing, optimization, metadata, roadmaps, quick wins,
  competitor gaps, and prioritization.
- Search intelligence: live SERPs, rank tracking, keyword research, trends, niches, and market
  viability.
- Google Search Console: properties, sitemaps, inspection, indexing, performance comparisons, and
  AI-search analytics.
- GEO analysis: entity coverage, AI citation readiness, `llms.txt`, and AI-bot visibility.
- Durable crawl and monitoring data backed by SQLite.
- Secure-by-default remote transport and SSRF-safe HTTP crawling.
- Optional autonomous audit-to-PR and managed skill lifecycle powered by Codex, Claude, or Grok.

## Quick start

### Requirements

- Python 3.11 or newer
- Git
- One virtual-environment backend: `uv`, `virtualenv`, or the OS `python3-venv` package

The autonomous agent has additional opt-in requirements: Linux, `gh`, Bubblewrap (`bwrap`), and at
least one supported agent CLI.

### Install from the repository

```bash
git clone https://github.com/dev-toolings/mcp-seo-auditor.git
cd mcp-seo-auditor
make install
make doctor
```

`make install` reuses a healthy local environment or creates one using `uv`, `virtualenv`, then
`python -m venv`. `make doctor` verifies the installed console command, registered tools and
prompts, required executables, and selected agent runtime.

Expected registry totals:

```text
15 tools
50 prompts
```

For an isolated global command:

```bash
pipx install ./packages/mcp-server
mcp-seo-auditor --doctor
```

## Connect an MCP client

The checked-in [`.mcp.json`](.mcp.json) is portable when the client opens this repository. It uses
the repository wrapper and its local virtual environment.

For any other project, point the MCP client at the installed console command:

```json
{
  "mcpServers": {
    "seo-auditor": {
      "command": "mcp-seo-auditor",
      "args": []
    }
  }
}
```

The default transport is stdio. Confirm the exact surface at any time:

```bash
mcp-seo-auditor --test
```

When the repository wrapper is called from another project, it parses that project's `.env.seo`
as dotenv data. It never sources the file as shell code.

## Tool surface

Every routed tool uses `tool_name(action="...", ...)`. `seo_audit` and `seo_geo` are
single-purpose and do not take an action.

| Tool | Actions / responsibility |
| --- | --- |
| `seo_audit` | Full evidence-based SEO audit |
| `seo_analyze` | `content`, `technical`, `structured_data`, `eeat`, `cwv` |
| `seo_site` | `sitemap`, `links`, `cannibalization`, `indexation_leaks`, `topical_authority`, `robots`, `migration` |
| `seo_content` | `write`, `optimize`, `meta`, `headlines`, `humanize`, `research` |
| `seo_market` | `research`, `trends`, `competitors`, `niches`, `volumes`, `insights`, `viability` |
| `seo_serp` | `predict`, `live`, `track`, `history`, `dashboard` |
| `seo_fix` | Generate reviewable `schema`, `meta`, `robots_txt`, or `llms_txt` artifacts and diffs |
| `seo_logs` | `analyze`, `bots`, `waste`, `ai_bots` |
| `gsc_manage` | `sites`, `sitemaps`, `inspect`, `index` |
| `gsc_analytics` | `query`, `compare`, `cannibalization`, `sitemap_health`, `ai_queries`, `ai_traffic` |
| `seo_strategy` | `action_plan`, `roadmap`, `competitor_gap`, `content_plan`, `quick_wins`, `priorities` |
| `seo_geo` | GEO and AI-search readiness audit |
| `seo_monitor` | `anomalies`, `detect`, `verify` |
| `seo_crawl` | `list`, `get`, `compare`, `trends`, `alerts` |
| `seo_agent` | Audit-to-PR orchestration, runtime diagnostics, and managed skills |

The 50 prompts cover keywords, analytics, competitors, content, technical SEO, linking, GEO, local
SEO, ecommerce, and reporting. Their embedded tool calls are validated against the live schemas by
the test suite.

## Configuration

Create a local runtime file:

```bash
cp packages/mcp-server/.env.example packages/mcp-server/.env
```

Important settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEFAULT_BASE_URL` | `http://localhost:3000` | Default crawl target |
| `DEFAULT_SITEMAP_URL` | `http://localhost:3000/sitemap.xml` | Default sitemap target |
| `GOOGLE_CREDENTIALS_PATH` | `credentials/google-credentials.json` | GSC service-account file |
| `LLM_PROVIDER` | empty | `anthropic`, `openai`, `ollama`, or disabled |
| `LLM_MODEL` | empty | Model used by AI-powered SEO tools |
| `LLM_API_KEY` | empty | Provider credential |
| `MCP_AUTH_TOKEN` | empty | Bearer token required by remote HTTP transport |
| `ALLOW_UNAUTHENTICATED_HTTP` | `false` | Development-only HTTP override |
| `ALLOW_LOCAL_URLS` | `false` | Permit private/loopback audit targets in isolated development |
| `SQLITE_DB_PATH` | `data/seo_auditor.db` | Durable local database |

See [`packages/mcp-server/.env.example`](packages/mcp-server/.env.example) for every setting.

### Optional integrations

Install the provider SDKs before enabling remote LLM-backed tools:

```bash
packages/mcp-server/.venv/bin/python -m pip install -e "packages/mcp-server[llm]"
```

- [Google Search Console setup](packages/mcp-server/docs/GOOGLE_SEARCH_CONSOLE_SETUP.md)
- [GSC quotas](packages/mcp-server/docs/GSC_QUOTAS.md)
- [Google Indexing API](packages/mcp-server/docs/INDEXING_API_SETUP.md)
- [Google Analytics 4](packages/mcp-server/docs/GA4_SETUP.md)

Market features use `pytrends`, an unofficial Google Trends client that can break when Google
changes its private endpoints. AI tools degrade explicitly when their optional provider or model is
unavailable.

## Autonomous agent

The `seo_agent` tool is disabled by default. Enable it only for explicitly authorized workspace and
skill roots:

```dotenv
SEO_AGENT_ENABLED=true
SEO_AGENT_PROVIDER=auto
SEO_AGENT_PROVIDER_ORDER=codex,claude,grok
SEO_AGENT_MODEL=
SEO_AGENT_ALLOWED_ROOTS=/home/operator/projects
SEO_AGENT_SKILL_ROOTS=/home/operator/.codex/skills
SEO_AGENT_WORKTREE_ROOT=/var/lib/seo-agent/worktrees
SEO_AGENT_ARTIFACT_ROOT=/var/lib/seo-agent/runs
```

With `SEO_AGENT_PROVIDER=auto`, the runtime chooses the first installed CLI in this order:

1. `codex exec --ephemeral`
2. `claude -p --no-session-persistence`
3. `grok -p`

Set `SEO_AGENT_MODEL` to select a model, pin `SEO_AGENT_PROVIDER`, or provide an operator-owned
runtime TOML through `SEO_AGENT_RUNTIME_CONFIG`.

### Audit-to-PR flow

```text
start → read-only audit → proposed plan → operator approval
      → isolated worktree changes → validation → local re-audit
      → independent review → exact commit → push → ready pull request
```

The approval must contain the exact current `plan_hash`. The external model cannot commit, push, or
open a PR; the supervisor owns those operations after validating the final diff.

Typical calls:

```text
seo_agent(action="start", workspace_path="/absolute/repository")
seo_agent(action="status", run_id="...")
seo_agent(action="approve", run_id="...", plan_hash="...")
seo_agent(action="cleanup", run_id="...")
```

Each audited repository must contain a versioned `.seo-agent.toml`. See the
[complete autonomous-agent guide](packages/mcp-server/docs/SEO_AGENT.md) for its schema, sandbox
rules, validation commands, checkpoints, recovery behavior, and artifacts.

### Managed skill lifecycle

The same tool can create, update, and prune model-designed Codex skills:

```text
seo_agent(action="runtime")
seo_agent(action="skills_plan", objective="...", workspace_path="...")
seo_agent(action="skills_apply", manifest={...}, plan_hash="...")
```

Planning is separate from mutation. Applying requires the exact manifest and plan hash previously
reviewed by the operator. Only directories containing `.mcp-seo-auditor-managed.json` may be
updated or deleted; unmanaged skills, stale hashes, symlinks, path traversal, and unauthorized roots
are rejected. Deletion additionally requires `manifest.prune=true`.

## Transports and deployment

### Local stdio

```bash
mcp-seo-auditor
```

### Local HTTP

Remote HTTP refuses to start without authentication:

```bash
export MCP_AUTH_TOKEN="replace-with-a-long-random-token"
mcp-seo-auditor --check-http-config
mcp-seo-auditor --transport http --host 127.0.0.1 --port 8020
```

Endpoints:

- MCP: `http://127.0.0.1:8020/mcp`
- Health: `http://127.0.0.1:8020/health`

Install the authenticated HTTP server as a user service with `make install-service`. The target
runs the HTTP preflight before creating or enabling the systemd unit.

### Docker development

```bash
cd packages/mcp-server
cp .env.example .env
docker compose up --build
```

The development compose file explicitly enables unauthenticated HTTP and must not be exposed to an
untrusted network.

### Docker production

```bash
cd deploy-prod
cp .env.production.example .env.production
# Set MCP_AUTH_TOKEN and the deployment-specific values.
docker compose up --build -d
```

Production exposes the MCP container only to Caddy's internal network.

## Architecture

```text
MCP client
   │ stdio / Streamable HTTP
   ▼
seo_server/
   ├── server.py          transport, auth, lifespan, registry diagnostics
   ├── schemas/           validated MCP input/output contracts
   ├── tools/             15 action-routed tool adapters
   ├── prompts/           50 reusable workflows
   └── service_context.py lazy dependency container
             │
             ▼
app/
   ├── services/          crawling, SEO, GEO, market, GSC, LLM, agent runtime
   ├── models/            Pydantic domain and persistence contracts
   ├── repositories/      SQLite-backed reports, crawls, and agent runs
   └── core/              configuration, security, scoring, HTTP safeguards
```

The MCP layer validates and routes requests. Business logic remains in `app/`, which keeps tool
schemas independent from provider and persistence implementations.

## Development

From the repository root:

```bash
make install              # Install package + test dependencies
make doctor               # Verify registry and runtime
make test                 # Run the non-integration suite
```

Additional gates:

```bash
cd packages/mcp-server
.venv/bin/python -m pytest -m integration tests/integration/test_mcp_protocol.py
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pip check
```

## License

MIT, as declared by the Python package metadata.
