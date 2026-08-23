"""Input model for seo_logs tool."""

from typing import Literal

from pydantic import Field

from seo_server.schemas.validators import MCPInput, SafeUrl


class SeoLogsInput(MCPInput):
    action: Literal["analyze", "bots", "waste", "ai_bots"]
    log_content: str = Field(
        ..., description="Raw server log content (Apache/Nginx combined format)"
    )
    sitemap_url: SafeUrl | None = None
