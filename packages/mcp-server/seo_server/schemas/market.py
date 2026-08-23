"""Input model for seo_market tool."""

from typing import Literal

from seo_server.schemas.validators import BoundedDays, BoundedMaxResults, MCPInput, SafeUrl


class SeoMarketInput(MCPInput):
    action: Literal[
        "research", "trends", "competitors", "niches", "volumes", "insights", "viability"
    ]
    keywords: list[str]
    geo: str = "FR"
    language: str = "fr"
    site_url: SafeUrl | None = None
    days: BoundedDays = 28
    max_results: BoundedMaxResults = 20
    concept: str | None = None
    market_type: str = "B2B"
