"""Input model for gsc_analytics tool."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from seo_server.schemas.validators import (
    BoundedDays,
    BoundedLimit,
    BoundedPeriodDays,
    BoundedPeriods,
    BoundedSampleSize,
    MCPInput,
    SafeUrl,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class GscAnalyticsInput(MCPInput):
    action: Literal[
        "query", "compare", "cannibalization", "sitemap_health", "ai_queries", "ai_traffic"
    ]
    site_url: str = Field(
        description="GSC property identifier. Use 'sc-domain:example.com' format (preferred) or 'https://example.com'. Auto-resolved to sc-domain: when possible.",
    )
    days: BoundedDays = 28
    limit: BoundedLimit = 50
    dimensions: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None
    search_type: str = "WEB"
    row_limit: Annotated[int, Field(ge=1, le=25000)] = 1000
    start_row: Annotated[int, Field(ge=0, le=25000)] = 0
    sort_by: str = "clicks"
    sort_direction: str = "descending"
    filter_dimension: str | None = None
    filter_operator: str = "contains"
    filter_expression: str | None = None
    page_url: SafeUrl | None = None
    period1_start: str | None = None
    period1_end: str | None = None
    period2_start: str | None = None
    period2_end: str | None = None
    min_impressions: int = 100
    sitemap_url: SafeUrl | None = None
    sample_size: BoundedSampleSize = 100
    use_cache: bool = True
    periods: BoundedPeriods = 6
    period_days: BoundedPeriodDays = 14
    language: str = "fr"

    @field_validator("period1_start", "period1_end", "period2_start", "period2_end")
    @classmethod
    def _validate_date_format(cls, v: str | None) -> str | None:
        if v is not None and not _DATE_RE.match(v):
            raise ValueError(f"Date must be YYYY-MM-DD format, got: {v}")
        return v


class GscAnalyticsOutput(BaseModel):
    """Documented output envelope for gsc_analytics.

    Permissive (``extra='allow'``): each action returns a different shape (overview,
    top pages/queries, cannibalization, sitemap health, AI queries/traffic), so this
    model only advertises the most common keys via ``outputSchema`` and lets every
    action-specific key (and the ``_meta`` envelope) pass through.
    """

    model_config = ConfigDict(extra="allow")

    count: int | None = Field(None, description="Number of rows returned by list-style actions.")
    pages: list | None = Field(None, description="Top pages (dimensions=['page']).")
    queries: list | None = Field(None, description="Top queries (dimensions=['query']).")
    total_urls: int | None = Field(None, description="Total URLs evaluated (sitemap_health).")
    cannibalization_groups: int | None = Field(
        None, description="Number of cannibalization groups detected."
    )
    ai_enhanced: bool | None = Field(None, description="True when LLM enrichment was applied.")
    error: str | None = Field(None, description="Error message when the query failed.")
