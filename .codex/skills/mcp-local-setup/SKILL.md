---
name: mcp-local-setup
description: Set up and verify the mcp-seo-auditor repository as a local stdio MCP server, including its virtual environment and portable client configuration. Use for local installation or repair; do not use for production deployment.
---

# MCP SEO Auditor — local setup

Make the checked-out `mcp-seo-auditor` repository usable by a local MCP client and leave
evidence that the installed registry works. The normal target is stdio; Docker, systemd, and
remote HTTP are separate operations and must not be enabled implicitly.

## Locate and guard the target

1. Resolve the repository root from the user's path or the current directory. It must contain
   `packages/mcp-server/pyproject.toml`, whose project name is `mcp-seo-auditor`, plus the root
   `Makefile` and `.mcp.json`. If these markers are missing, stop and report that this is not the
   expected checkout instead of installing into an arbitrary project.
2. Check `python3 --version`; this package requires Python 3.11 or newer. Keep the repository's
   existing `.venv` when it is healthy; do not replace it or use the system interpreter's pip.
3. Inspect the existing `.mcp.json` before editing it. Preserve unrelated servers and settings.

## Install and verify

Run the bundled helper from the repository root (resolve `scripts/setup_local_mcp.sh` relative to
this `SKILL.md`):

```bash
bash /path/to/mcp-local-setup/scripts/setup_local_mcp.sh /absolute/path/to/mcp-seo-auditor
```

The helper runs the repository's idempotent `make install`, then `make doctor` and the stdio
registry test. It does not create, overwrite, or print `.env` files or credentials. If the helper
cannot be used, run the same commands manually from the root:

```bash
make install
make doctor
packages/mcp-server/.venv/bin/mcp-seo-auditor --test
```

`make install` creates or reuses `packages/mcp-server/.venv` and installs the package with its dev
extras. `make doctor` must report the registered tool/prompt surface; retain its exact output in
the hand-off. Do not claim success from a successful dependency install alone.

## Environment and secrets

- Runtime defaults are sufficient for a basic local stdio setup. Create
  `packages/mcp-server/.env` only when the user needs custom targets or integrations, and only if
  it does not already exist (`cp .../.env.example .../.env`). Never overwrite it.
- Keep Google service-account JSON, OAuth tokens, LLM keys, and `.env` files outside Git. Never
  echo secret values; if a credential file is present, check its path and permissions without
  displaying its contents.
- Optional integrations (GSC, LLM, spaCy, browser, market extras) are installed only when the
  user asks for that capability. Basic setup must remain usable with those integrations disabled.

## MCP client registration

For this checkout, prefer the tracked `.mcp.json` entry, which calls
`./packages/mcp-server/run_server.sh`. Verify that the wrapper is executable and that it resolves
the local `.venv`; do not replace it with a machine-specific absolute path.

When registering the server in another client or another project, use an absolute path to the
wrapper or the installed `mcp-seo-auditor` executable. Merge into an existing configuration rather
than overwriting it. If a client config is absent, create it only as part of the user's explicit
registration request.

## Optional transports

Do not start HTTP or install a systemd service during local stdio setup. If the user explicitly asks
for HTTP, require a non-empty `MCP_AUTH_TOKEN`, run `mcp-seo-auditor --check-http-config`, and bind
to the requested host/port. `ALLOW_UNAUTHENTICATED_HTTP=true` is an isolated development escape
hatch only; never enable it silently.

## Failure handling and hand-off

Stop on the first failed command, preserve the full error (including status and offending path),
and state what remains unverified. At completion report the repository path, Python/venv used,
doctor and test results, any client config changed, and optional integrations left disabled.
