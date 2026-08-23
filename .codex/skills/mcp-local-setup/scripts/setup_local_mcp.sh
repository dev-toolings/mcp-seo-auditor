#!/usr/bin/env bash
set -euo pipefail

repo_arg="${1:-$PWD}"
if [[ ! -d "$repo_arg" ]]; then
  printf 'Repository directory does not exist: %s\n' "$repo_arg" >&2
  exit 2
fi

repo_dir="$(cd -- "$repo_arg" && pwd -P)"
pyproject="$repo_dir/packages/mcp-server/pyproject.toml"
root_makefile="$repo_dir/Makefile"
mcp_config="$repo_dir/.mcp.json"
wrapper="$repo_dir/packages/mcp-server/run_server.sh"

for required in "$pyproject" "$root_makefile" "$mcp_config" "$wrapper"; do
  if [[ ! -f "$required" ]]; then
    printf 'Expected mcp-seo-auditor file is missing: %s\n' "$required" >&2
    exit 2
  fi
done

if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required but was not found in PATH.\n' >&2
  exit 127
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
  printf 'Python 3.11 or newer is required.\n' >&2
  python3 --version >&2
  exit 2
fi

if ! python3 - "$pyproject" "$mcp_config" <<'PY'
import json
import sys
import tomllib
from pathlib import Path

pyproject = Path(sys.argv[1])
mcp_config = Path(sys.argv[2])

with pyproject.open("rb") as stream:
    project_name = tomllib.load(stream).get("project", {}).get("name")
if project_name != "mcp-seo-auditor":
    print(f"Unexpected Python project name: {project_name!r}", file=sys.stderr)
    raise SystemExit(1)

with mcp_config.open(encoding="utf-8") as stream:
    config = json.load(stream)
server = config.get("mcpServers", {}).get("seo-auditor")
expected_command = "./packages/mcp-server/run_server.sh"
if not isinstance(server, dict) or server.get("command") != expected_command:
    actual = server.get("command") if isinstance(server, dict) else None
    print(
        f".mcp.json seo-auditor command is {actual!r}; expected {expected_command!r}",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY
then
  printf 'Repository markers are not the expected local mcp-seo-auditor setup.\n' >&2
  exit 2
fi

if [[ ! -x "$wrapper" ]]; then
  printf 'MCP wrapper is not executable: %s\n' "$wrapper" >&2
  exit 2
fi

printf 'Installing mcp-seo-auditor in %s\n' "$repo_dir"
make -C "$repo_dir" install
make -C "$repo_dir" doctor

binary="$repo_dir/packages/mcp-server/.venv/bin/mcp-seo-auditor"
if [[ ! -x "$binary" ]]; then
  printf 'Installation completed without the expected executable: %s\n' "$binary" >&2
  exit 1
fi

printf 'Testing the stdio registry\n'
"$binary" --test
printf 'Local MCP setup verified: %s\n' "$binary"
