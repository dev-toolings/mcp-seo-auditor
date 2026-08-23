"""MCP Server for SEO Auditor — FastMCP 3.0 implementation."""

import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from app.core.config import settings
from app.core.logging import setup_logging
from seo_server import service_context

# Must run before any other logging call. Writes to stderr so it never corrupts
# the stdio transport, and is idempotent. Level/format come from
# settings.LOG_LEVEL and settings.LOG_JSON.
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(server):
    """Initialize ServiceContext on startup, shutdown on exit."""
    ctx = service_context.initialize()
    if settings.SEO_AGENT_ENABLED:
        await ctx.agent_supervisor.resume_pending()
    logger.info("SEO Auditor MCP server started")
    yield
    await ctx.shutdown()
    logger.info("SEO Auditor MCP server stopped")


def _http_auth():
    token = settings.MCP_AUTH_TOKEN.get_secret_value()
    if not token:
        return None
    from fastmcp.server.auth import StaticTokenVerifier

    return StaticTokenVerifier(
        tokens={token: {"sub": "seo-agent-operator", "client_id": "seo-auditor"}}
    )


mcp = FastMCP("seo-auditor", lifespan=lifespan, auth=_http_auth(), mask_error_details=True)


def _register_tools():
    """Import tool modules to trigger @mcp.tool registration."""
    import seo_server.tools  # noqa: F401


def _register_prompts():
    """Import prompt modules to trigger @mcp.prompt registration."""
    import seo_server.prompts  # noqa: F401


_register_tools()
_register_prompts()


def _parse_args():
    """Parse CLI arguments for transport selection."""
    import argparse

    parser = argparse.ArgumentParser(description="SEO Auditor MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (default: stdio for Claude Code, http for remote clients)",
    )
    parser.add_argument("--port", type=int, default=8020, help="HTTP port (default: 8020)")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--test", action="store_true", help="Test mode: list tools and prompts")
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Print installation, registry, and agent-runtime diagnostics as JSON",
    )
    parser.add_argument(
        "--check-http-config",
        action="store_true",
        help="Fail unless HTTP authentication or the development override is configured",
    )
    return parser.parse_args()


def _http_app_with_health(mcp_server: FastMCP):
    """Build the HTTP application and preserve the FastMCP lifespan."""
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    async def health(request: Request) -> JSONResponse:
        tool_count = len(await mcp_server.list_tools())
        prompt_count = len(await mcp_server.list_prompts())
        return JSONResponse({"status": "ok", "tools": tool_count, "prompts": prompt_count})

    mcp_app = mcp_server.http_app(transport="streamable-http")
    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=mcp_app.lifespan,
    )


def _require_http_configuration() -> dict[str, bool]:
    """Validate the remote transport before starting or installing it."""
    authenticated = bool(settings.MCP_AUTH_TOKEN.get_secret_value())
    development_override = settings.ALLOW_UNAUTHENTICATED_HTTP
    if not authenticated and not development_override:
        raise RuntimeError(
            "HTTP transport requires MCP_AUTH_TOKEN. Set "
            "ALLOW_UNAUTHENTICATED_HTTP=true only for isolated development."
        )
    return {
        "authenticated": authenticated,
        "development_override": development_override,
    }


def _run_http_with_health(mcp_server: FastMCP, host: str, port: int):
    """Run MCP server with an additional /health endpoint."""
    _require_http_configuration()
    import uvicorn

    uvicorn.run(_http_app_with_health(mcp_server), host=host, port=port)


def main() -> None:
    """Console entry point for stdio, HTTP, and registry smoke tests."""
    args = _parse_args()

    if args.check_http_config:
        import json

        try:
            status = _require_http_configuration()
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        print(json.dumps(status, sort_keys=True))
    elif args.doctor:
        import asyncio
        import json
        import shutil
        import sys

        async def doctor() -> dict:
            ctx = service_context.initialize()
            try:
                return {
                    "ok": True,
                    "python": sys.executable,
                    "tools": len(await mcp.list_tools()),
                    "prompts": len(await mcp.list_prompts()),
                    "agent_runtime": ctx.skill_lifecycle.runtime_status(),
                    "executables": {name: shutil.which(name) for name in ("git", "gh", "bwrap")},
                }
            finally:
                await ctx.shutdown()

        print(json.dumps(asyncio.run(doctor()), indent=2, sort_keys=True))
    elif args.test:
        import asyncio

        from seo_server.server import mcp as _mcp

        service_context.initialize()
        tools = asyncio.run(_mcp.list_tools())
        prompts = asyncio.run(_mcp.list_prompts())
        print(f"MCP Server test mode — {len(tools)} tools, {len(prompts)} prompts available.")
        for t in sorted(tools, key=lambda x: x.name):
            print(f"  [tool] {t.name}")
        for p in sorted(prompts, key=lambda x: x.name):
            print(f"  [prompt] {p.name}")
    else:
        from seo_server.server import mcp as _mcp

        if args.transport == "http":
            logger.info("Starting MCP server (streamable-http on %s:%d)", args.host, args.port)
            _run_http_with_health(_mcp, args.host, args.port)
        else:
            _mcp.run()


if __name__ == "__main__":
    main()
