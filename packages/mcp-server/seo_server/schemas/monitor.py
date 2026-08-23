"""Input model for seo_monitor tool."""

from typing import Literal

from seo_server.schemas.validators import BoundedDays, MCPInput, SafeUrl


class SeoMonitorInput(MCPInput):
    action: Literal["anomalies", "detect", "verify"]
    keywords: list[str] | None = None
    days_back: BoundedDays = 28
    site_url: str | None = None  # Not SafeUrl because sc-domain: format
    url: SafeUrl | None = None
    issue_type: Literal[
        "indexation_leak",
        "canonical",
        "redirect_chain",
        "thin_content",
    ] = "indexation_leak"
