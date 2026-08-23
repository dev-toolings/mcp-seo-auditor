# mcp-seo-auditor Python package

FastMCP server for the repository-level SEO Auditor project. Install from the repository root:

```bash
python3 -m venv packages/mcp-server/.venv
packages/mcp-server/.venv/bin/python -m pip install -e "packages/mcp-server[dev]"
packages/mcp-server/.venv/bin/mcp-seo-auditor --test
```

The console command starts the stdio transport by default. Pass `--transport http` for the
authenticated Streamable HTTP transport.
