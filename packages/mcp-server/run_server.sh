#!/usr/bin/env bash
# Dynamic MCP seo-auditor server wrapper
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CALLER_ENV="$PWD/.env.seo"

# Let pydantic-settings parse project configuration as dotenv data. Never
# source a caller-controlled file: dotenv values are configuration, not shell.
if [ -f "$CALLER_ENV" ]; then
  export SEO_AUDITOR_ENV_FILE="$CALLER_ENV"
fi

# Default GSC credentials to the local checked-out file when not already set.
if [ -z "${GOOGLE_CREDENTIALS_PATH:-}" ] && [ -f "$SCRIPT_DIR/credentials/google-credentials.json" ]; then
  export GOOGLE_CREDENTIALS_PATH="$SCRIPT_DIR/credentials/google-credentials.json"
fi

cd "$SCRIPT_DIR"
if [ -x "$SCRIPT_DIR/.venv/bin/mcp-seo-auditor" ]; then
  exec "$SCRIPT_DIR/.venv/bin/mcp-seo-auditor" "$@"
fi
if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  exec "$SCRIPT_DIR/.venv/bin/python" -m seo_server.server "$@"
fi
if command -v mcp-seo-auditor >/dev/null 2>&1; then
  exec mcp-seo-auditor "$@"
fi

echo "mcp-seo-auditor is not installed. Run 'make install' from the repository root." >&2
exit 127
