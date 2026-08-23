"""Tool domain modules — importing registers all tools with @mcp.tool."""

# Import order doesn't matter; each module registers its tools at import time.
from seo_server.tools import (
    agent,  # noqa: F401
    analyze,  # noqa: F401
    audit,  # noqa: F401
    content,  # noqa: F401
    crawl,  # noqa: F401
    fix,  # noqa: F401
    geo,  # noqa: F401
    gsc_analytics,  # noqa: F401
    gsc_manage,  # noqa: F401
    logs,  # noqa: F401
    market,  # noqa: F401
    monitor,  # noqa: F401
    serp,  # noqa: F401
    site,  # noqa: F401
    strategy,  # noqa: F401
)
