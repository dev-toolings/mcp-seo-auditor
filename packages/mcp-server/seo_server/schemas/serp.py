"""Input model for seo_serp tool."""

from typing import Literal

from seo_server.schemas.validators import BoundedDays, MCPInput, SafeUrl


class SeoSerpInput(MCPInput):
    action: Literal["predict", "live", "track", "history", "dashboard"]
    keywords: list[str] = []
    site_domain: str | None = None
    engine: str = "google"
    # Required by the persistence actions (track/history/dashboard): the site the
    # positions are stored against.
    site_url: SafeUrl | None = None
    days: BoundedDays = 90
