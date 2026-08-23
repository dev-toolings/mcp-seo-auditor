"""Structured JSON logging with a request-scoped correlation ID.

Stdlib only — no extra dependency. Call :func:`setup_logging` once at process
start (server entry point); every module keeps using ``logging.getLogger(__name__)``
as before.

A correlation ID lives in a :mod:`contextvars` variable, so it propagates across
``await`` boundaries and concurrent tasks without being threaded through call
signatures. Wrap a unit of work with :func:`correlation_scope` to make every log
line emitted underneath it — including from deep inside services — carry the
same ``correlation_id``, which is what makes a full audit traceable end to end.
"""

import contextvars
import json
import logging
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Optional

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")

# LogRecord attributes that are part of the stdlib and must not be re-emitted as
# custom "extra" fields.
_RESERVED_ATTRS = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


def new_correlation_id() -> str:
    """Return a short, unique correlation ID."""
    return uuid.uuid4().hex[:16]


def get_correlation_id() -> str:
    """Return the correlation ID bound to the current context ("" if unset)."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> contextvars.Token:
    """Bind a correlation ID to the current context.

    Returns the token needed to restore the previous value via
    :func:`reset_correlation_id`. Prefer :func:`correlation_scope`.
    """
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: contextvars.Token) -> None:
    """Restore the correlation ID replaced by :func:`set_correlation_id`."""
    _correlation_id.reset(token)


@contextmanager
def correlation_scope(correlation_id: Optional[str] = None) -> Iterator[str]:
    """Bind a correlation ID for the duration of the block.

    Generates one when not supplied, and always restores the previous value.

    Example:
        with correlation_scope() as cid:
            logger.info("audit started", extra={"url": url})
    """
    cid = correlation_id or new_correlation_id()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)


class CorrelationIdFilter(logging.Filter):
    """Attach the context-local correlation ID to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", ""):
            record.correlation_id = _correlation_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        correlation_id = getattr(record, "correlation_id", "")
        if correlation_id:
            payload["correlation_id"] = correlation_id

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Anything passed via logger.info(..., extra={...}) lands on the record
        # as a custom attribute; surface it as a top-level JSON field.
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key in payload or key.startswith("_"):
                continue
            if key == "correlation_id":
                continue  # already handled above; skip when empty
            payload[key] = value if _is_json_safe(value) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=repr)


def _is_json_safe(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict, tuple))


def setup_logging(
    level: Optional[str] = None,
    json_output: Optional[bool] = None,
) -> None:
    """Configure root logging for the process. Idempotent.

    Args:
        level: Log level name (e.g. "DEBUG"). Defaults to ``settings.LOG_LEVEL``.
        json_output: Emit JSON when True, human-readable text when False.
            Defaults to ``settings.LOG_JSON``.

    Logs go to stderr, keeping stdout free for the MCP stdio transport.
    """
    from app.core.config import settings

    resolved_level = (level or settings.LOG_LEVEL).upper()
    use_json = settings.LOG_JSON if json_output is None else json_output

    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(CorrelationIdFilter())
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s: %(message)s"
            )
        )

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved_level, logging.INFO))
