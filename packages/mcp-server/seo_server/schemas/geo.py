"""Input model for seo_geo tool."""

from typing import Literal

from pydantic import Field

from seo_server.schemas.validators import MCPInput, SafeUrlList

TargetEngine = Literal[
    "all",
    "google_ai_overviews",
    "perplexity",
    "chatgpt_search",
    "gemini",
]


class SeoGeoInput(MCPInput):
    urls: SafeUrlList
    include_ai_recommendations: bool = True
    language: str = "en"
    max_urls: int = Field(default=10, ge=1, le=50)
    target_engine: TargetEngine = Field(
        default="all",
        description=(
            "AI engine to weight the GEO score for. 'all' uses the balanced default; "
            "each engine re-weights the five dimensions to match how it sources answers."
        ),
    )
