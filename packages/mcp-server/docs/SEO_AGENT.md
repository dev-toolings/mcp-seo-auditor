# Autonomous SEO agent

The `seo_agent` MCP tool runs a durable audit-to-pull-request workflow. It is disabled by
default and never changes the caller's checkout. Every run uses a detached Git worktree,
waits for approval of an exact plan hash, validates the resulting diff, re-audits a local
preview, then lets the supervisor—not the external agent—commit, push, and open a ready PR.

## Runtime requirements

- Linux, `git`, GitHub CLI (`gh`), and Bubblewrap (`bwrap`)
- FastMCP task dependencies (`fastmcp[tasks]`)
- Codex, Claude Code, or Grok installed for automatic non-interactive selection; alternatively,
  an operator-owned runtime TOML outside every audited repository
- a versioned `.seo-agent.toml` at the root of every audited repository
- an authenticated `gh` session with access to the GitHub remote

Enable the feature only after both configurations exist:

```dotenv
SEO_AGENT_ENABLED=true
SEO_AGENT_PROVIDER=auto
SEO_AGENT_PROVIDER_ORDER=codex,claude,grok
SEO_AGENT_MODEL=
SEO_AGENT_ALLOWED_ROOTS=/srv/sites:/home/operator/projects
SEO_AGENT_RUNTIME_CONFIG=
SEO_AGENT_WORKTREE_ROOT=/var/lib/seo-agent/worktrees
SEO_AGENT_ARTIFACT_ROOT=/var/lib/seo-agent/runs
SEO_AGENT_SKILL_ROOTS=/home/operator/.codex/skills
```

For HTTP transport, `MCP_AUTH_TOKEN` is mandatory unless the operator explicitly enables
the unsafe development override. Stdio inherits the authority of the local process.

## Non-interactive runtime

With `SEO_AGENT_RUNTIME_CONFIG` empty, the supervisor detects `codex`, then `claude`, then
`grok`. It invokes their supported non-interactive forms (`codex exec --ephemeral`, `claude
-p --no-session-persistence`, or `grok -p`) and uses `SEO_AGENT_MODEL` when set. Pin a provider
with `SEO_AGENT_PROVIDER=codex|claude|grok`.

According to the official OpenAI documentation, `codex exec` is intended for scripts and CI,
prints the final message to stdout, and supports explicit read-only/workspace-write sandboxes.

## Custom operator runtime

For another CLI, create `/etc/seo-agent/runtime.toml` and point
`SEO_AGENT_RUNTIME_CONFIG` to it:

```toml
version = 1
argv = ["seo-phase-agent", "--prompt", "{prompt_file}", "--output", "{result_file}"]
prompt_mode = "file" # argument, stdin, or file
result_mode = "file" # stdout_json or file
timeout_seconds = 1800
env_allowlist = ["OPENAI_API_KEY"]
runtime_read_paths = ["/opt/agent-runtime"]
sandbox = true
```

The CLI must return one JSON object for each phase. The placeholders available in `argv`
are `{prompt}`, `{prompt_file}`, `{result_file}`, and `{workspace}`. Bubblewrap mounts the
worktree read-only for analyst, planner, and reviewer phases, and writable only for the
implementer and bounded repair phases. `git` write/network commands and `gh` are blocked
inside the sandbox.

## Project policy

Commit this `.seo-agent.toml` in the audited repository:

```toml
version = 1

[site]
base_url = "https://example.com"
sitemap_url = "https://example.com/sitemap.xml"
gsc_property = "sc-domain:example.com"
language = "fr"

[workspace]
allow = ["app/**", "src/**", "public/**"]
deny = [".env*", "**/.env*", "**/credentials/**", ".git/**"]

[validation]
commands = [
  ["bun", "run", "lint"],
  ["bun", "test"],
  ["bun", "run", "build"],
]

[preview]
command = ["bun", "run", "start", "--", "--port", "{port}"]
url_template = "http://127.0.0.1:{port}"
readiness_path = "/"
sitemap_path = "/sitemap.xml"
timeout_seconds = 120

[git]
base_branch = "main"
branch_prefix = "seo-agent"

[limits]
max_files = 40
max_diff_lines = 4000
max_minutes = 45
max_repair_cycles = 2
```

Commands are argv arrays and are never executed through a shell. `npm`, `npx`, and shell
interpreters are rejected. Operator environment limits are hard ceilings: a project policy
can lower them but cannot raise them.

## MCP workflow

1. Call `seo_agent(action="start", workspace_path="/absolute/repo")`.
2. Poll `seo_agent(action="status", run_id="...")` until `awaiting_approval`.
3. Review `findings`, `plan`, and `plan_hash` from the status result.
4. Call `seo_agent(action="approve", run_id="...", plan_hash="...")`.
5. Poll status through validation, local re-audit, review, commit, push, and PR creation.
6. After reviewing the pushed result, call `seo_agent(action="cleanup", run_id="...")`.

`reject`, `cancel`, and `resume` are also available. A recoverable external failure—such as
an unavailable GitHub CLI—keeps the durable run and worktree so it can be resumed. Cleanup
refuses active or dirty worktrees and never merges a PR.

## Declarative skill lifecycle

`seo_agent(action="runtime")` reports the selected CLI and model.

`seo_agent(action="skills_plan", objective="...", workspace_path="...")` asks that CLI for a
versioned `SkillManifest`, then returns exact create/update/delete/unchanged operations and a
`plan_hash`. Pass the returned manifest and hash to `skills_apply`. An explicit manifest can
also be planned without calling a model.

Only directories containing `.mcp-seo-auditor-managed.json` may be updated or deleted.
Unmanaged skills, symlink targets, path traversal, stale plan hashes, and roots outside
`SEO_AGENT_SKILL_ROOTS` are refused. Deletion requires `manifest.prune=true`; omitting a skill
from a non-pruning manifest never removes it.

## Durable artifacts

SQLite is the authority for runs, phase transitions, approvals, plan hashes, and command
logs. The per-run artifact directory contains the before/after audits, normalized findings,
approved plan, diff summary, actual patch, validation results, reviewer decision, prompt and
result files, preview log, audit comparison, and PR body. GSC is the only external keyword
source in v1; missing data must remain explicitly marked `missing`.
