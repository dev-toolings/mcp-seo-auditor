"""Prompt domain modules — importing registers all prompts with @mcp.prompt."""

# Import order doesn't matter; each module registers its prompts at import time.
from seo_server.prompts import (
    analytics,  # noqa: F401
    competitors,  # noqa: F401
    content,  # noqa: F401
    ecommerce,  # noqa: F401
    geo,  # noqa: F401
    keywords,  # noqa: F401
    linking,  # noqa: F401
    local_seo,  # noqa: F401
    reporting,  # noqa: F401
    technical,  # noqa: F401
)
