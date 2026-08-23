"""Input model for seo_content tool."""

from typing import Literal

from seo_server.schemas.validators import MCPInput, SafeUrl


class SeoContentInput(MCPInput):
    action: Literal["write", "optimize", "meta", "headlines", "humanize", "research"]
    target_url: SafeUrl | None = None
    target_keyword: str = ""
    content: str = ""  # For optimize/humanize — text to process
    language: str = "fr"
    tone: str = ""  # Override brand voice tone
    word_count: int = 2500
