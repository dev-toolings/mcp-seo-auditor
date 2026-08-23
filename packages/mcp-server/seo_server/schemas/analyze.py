"""Input model for seo_analyze tool."""

from typing import Literal

from pydantic import BaseModel, Field

from seo_server.schemas.validators import MCPInput, SafeUrl, SafeUrlList


class ListingConfig(BaseModel):
    css_selectors: list[str] = Field(default_factory=lambda: [".product-list", ".listing"])
    count_css_selector: str | None = None
    text_patterns: list[str] = Field(default_factory=lambda: ["no results", "aucun résultat"])
    url_patterns: list[str] = Field(default_factory=list)


class SeoAnalyzeInput(MCPInput):
    action: Literal["content", "technical", "structured_data", "eeat", "cwv"]
    urls: SafeUrlList
    language: str = "en"
    depth: Literal["quick", "deep"] = "quick"
    check_thin_content: bool = True
    check_empty_listings: bool = False
    listing_config: ListingConfig | None = None
    check_canonicals: bool = True
    check_meta_robots: bool = True
    check_redirects: bool = False
    check_hreflang: bool = True
    # Off by default: the raw-vs-rendered diff needs the browser crawler, which is
    # an optional runtime dep. It degrades to status "unavailable" rather than failing.
    check_render_diff: bool = False
    sitemap_url: SafeUrl | None = None
    strategy: Literal["mobile", "desktop"] = "mobile"
