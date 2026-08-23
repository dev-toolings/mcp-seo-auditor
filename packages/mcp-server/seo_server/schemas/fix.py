"""Input model for the seo_fix tool."""

from typing import Literal

from pydantic import Field

from seo_server.schemas.validators import MCPInput, SafeUrl


class SeoFixInput(MCPInput):
    action: Literal["schema", "meta", "robots_txt", "llms_txt"]
    url: SafeUrl | None = None
    target_keyword: str | None = None
    sitemap_url: SafeUrl | None = None
    page_type: str = "auto"
    language: str = "en"
    max_urls: int = Field(default=50, ge=1, le=500)
    dry_run: bool = Field(
        default=True,
        description=(
            "When true (default) the tool only returns generated artifacts and unified "
            "diffs to apply yourself. The server never writes to remote sites; dry_run "
            "is a safety affordance for client-side apply flows."
        ),
    )
