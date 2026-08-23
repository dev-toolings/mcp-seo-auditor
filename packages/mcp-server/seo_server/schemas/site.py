"""Input model for seo_site tool."""

from typing import Literal

from seo_server.schemas.validators import (
    BoundedMaxPages,
    BoundedMaxUrls,
    MCPInput,
    SafeUrl,
    SafeUrlList,
)


class SeoSiteInput(MCPInput):
    action: Literal[
        "sitemap",
        "links",
        "cannibalization",
        "indexation_leaks",
        "topical_authority",
        "robots",
        "migration",
    ]
    sitemap_url: SafeUrl | None = None
    max_pages: BoundedMaxPages = 500
    quick: bool = False
    language: str = "en"
    max_urls: BoundedMaxUrls = 50
    urls: SafeUrlList | None = None
    check_targets: bool = True
    n_clusters: int | None = None
    url: SafeUrl | None = None
    old_sitemap_url: SafeUrl | None = None
    new_sitemap_url: SafeUrl | None = None
    site_url: SafeUrl | None = None
