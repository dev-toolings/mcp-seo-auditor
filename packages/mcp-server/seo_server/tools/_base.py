"""Shared helpers for MCP tool handlers."""

import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.logging import correlation_scope

logger = logging.getLogger(__name__)


def _extract_action(args: tuple, kwargs: dict) -> str | None:
    """Best-effort read of the ``action`` field from the handler's input model."""
    inp = kwargs.get("input")
    if inp is None and args:
        inp = args[0]
    return getattr(inp, "action", None)


def tool_handler(func: Callable[..., Awaitable[dict]]) -> Callable[..., Awaitable[dict]]:
    """Wrap an async MCP tool handler with error guarding and a ``_meta`` contract.

    Two responsibilities:

    1. Uncaught exceptions are logged and converted to the canonical error shape
       ``{error, error_type, recoverable}`` instead of surfacing as an MCP protocol
       crash.
    2. Successful ``dict`` results are augmented with a ``_meta`` block
       ``{tool, action, ai_enhanced, duration_ms}`` so every response carries a
       uniform, machine-readable envelope. Existing keys are never overwritten.

    Apply it BELOW ``@mcp.tool`` so the registered callable is the guarded one::

        @mcp.tool(name="seo_geo", description="...")
        @tool_handler
        async def seo_geo(input: SeoGeoInput) -> dict:
            ...

    ``functools.wraps`` preserves the original signature so FastMCP still builds the
    correct input schema from the handler's type hints.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict:
        start = time.perf_counter()
        # One correlation id per tool call, propagated by contextvar so every log
        # line emitted deep inside the async services carries the same id.
        with correlation_scope() as correlation_id:
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                logger.exception("Tool handler %s failed", func.__name__)
                return {
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "recoverable": False,
                    "correlation_id": correlation_id,
                }

            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            if isinstance(result, dict) and "_meta" not in result:
                result["_meta"] = {
                    "tool": func.__name__,
                    "action": _extract_action(args, kwargs),
                    "ai_enhanced": result.get("ai_enhanced"),
                    "duration_ms": duration_ms,
                    "correlation_id": correlation_id,
                }
            return result

    return wrapper
