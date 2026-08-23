"""Input and output models for seo_audit tool."""

from pydantic import BaseModel, ConfigDict, Field

from seo_server.schemas.validators import BoundedMaxPages, MCPInput, SafeUrl


class SeoAuditInput(MCPInput):
    sitemap_url: SafeUrl
    max_pages: BoundedMaxPages = 500
    include_cwv: bool = False
    language: str = "en"


class SeoAuditOutput(BaseModel):
    """Documented output envelope for seo_audit.

    Permissive (``extra='allow'``): the real payload is large and partially compacted to
    fit the MCP payload limit, so undocumented keys (and the ``_meta`` envelope added by
    ``tool_handler``) pass through untouched. This model exists to advertise the main
    keys via the tool's ``outputSchema``, not to constrain the response.
    """

    model_config = ConfigDict(extra="allow")

    overall_score: float | None = Field(None, description="Overall SEO score (0-100).")
    grade: str | None = Field(None, description="Letter grade derived from the overall score.")
    dimension_scores: dict | None = Field(None, description="Per-dimension scores.")
    content: dict | None = Field(None, description="Content quality analysis.")
    structured_data: dict | None = Field(None, description="Schema.org / JSON-LD analysis.")
    internal_links: dict | None = Field(None, description="Internal linking analysis.")
    technical: dict | None = Field(None, description="Technical SEO checks.")
    cwv: dict | None = Field(None, description="Core Web Vitals (when include_cwv=true).")
    geo: dict | None = Field(None, description="GEO (AI-search) readiness analysis.")
    gsc_performance: dict | None = Field(None, description="GSC performance data when available.")
    recommendations: list | None = Field(None, description="Prioritized recommendations.")
    ai_enhanced: bool | None = Field(None, description="True when LLM enrichment was applied.")
    crawl_session_id: str | None = Field(None, description="Stored crawl session id, if any.")
    error: str | None = Field(None, description="Error message when the audit failed.")
