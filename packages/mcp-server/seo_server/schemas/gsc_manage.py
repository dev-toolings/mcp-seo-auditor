"""Input model for gsc_manage tool."""

from typing import Literal

from pydantic import Field

from seo_server.schemas.validators import MCPInput, SafeUrl, SafeUrlList


class GscManageInput(MCPInput):
    action: Literal["sites", "sitemaps", "inspect", "index"]
    sub_action: str | None = None
    index_type: Literal["URL_UPDATED", "URL_DELETED"] = Field(
        default="URL_UPDATED",
        description="Google Indexing API notification type for action='index': URL_UPDATED (page created/changed) or URL_DELETED.",
    )
    site_url: str | None = Field(
        default=None,
        description="GSC property identifier. Use 'sc-domain:example.com' format (preferred) or 'https://example.com'. Auto-resolved to sc-domain: when possible. Use action='sites' first to list available properties.",
    )
    sitemap_url: SafeUrl | None = None
    sitemap_index: str | None = None
    page_url: SafeUrl | None = None
    urls: SafeUrlList | None = None
    force_refresh: bool = False
