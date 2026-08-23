"""Input model for seo_crawl tool."""

from typing import Literal

from seo_server.schemas.validators import BoundedDays, BoundedLimit, MCPInput, SafeUrl


class SeoCrawlInput(MCPInput):
    action: Literal["list", "get", "compare", "trends", "alerts"]
    site_url: SafeUrl | None = None
    limit: BoundedLimit = 20
    crawl_id: str | None = None
    audit_id: str | None = None
    crawl_id_1: str | None = None
    crawl_id_2: str | None = None
    days: BoundedDays = 90
