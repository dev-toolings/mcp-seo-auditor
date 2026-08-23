"""Input model for seo_strategy tool."""

from typing import Any, Literal

from seo_server.schemas.validators import (
    BoundedDays,
    BoundedMaxActions,
    MCPInput,
    SafeUrl,
    SafeUrlList,
)


class SeoStrategyInput(MCPInput):
    action: Literal[
        "action_plan",
        "roadmap",
        "competitor_gap",
        "content_plan",
        "quick_wins",
        "priorities",
    ]
    site_url: str | None = None  # Not SafeUrl because sc-domain: format
    sitemap_url: SafeUrl | None = None
    business_context: str = ""
    max_actions: BoundedMaxActions = 20
    aggregated_data: dict[str, Any] | None = None
    site_type: str | None = None
    language: str = "en"
    days: BoundedDays = 28
    competitor_urls: SafeUrlList = []
    keywords: list[str] = []
