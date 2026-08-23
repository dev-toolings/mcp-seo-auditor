"""Editorial context service — reads brand/style/SEO context from markdown files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapping of context keys to their markdown filenames
_FILE_MAP = {
    "brand_voice": "brand-voice.md",
    "style_guide": "style-guide.md",
    "internal_links": "internal-links-map.md",
    "target_keywords": "target-keywords.md",
    "competitor_analysis": "competitor-analysis.md",
}


class EditorialContextService:
    """Loads editorial context from markdown files in a configured directory.

    Each method reads a specific .md file. If the file or directory doesn't
    exist, the method returns an empty string (never raises).
    """

    def __init__(self, context_dir: str = ""):
        self.context_dir = context_dir

    def _read_file(self, filename: str) -> str:
        """Read a markdown file from the context directory. Returns '' on any failure."""
        if not self.context_dir:
            return ""
        path = Path(self.context_dir) / filename
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError) as exc:
            logger.debug("Editorial context file not found: %s (%s)", path, exc)
            return ""

    def get_brand_voice(self) -> str:
        """Load brand-voice.md content."""
        return self._read_file(_FILE_MAP["brand_voice"])

    def get_style_guide(self) -> str:
        """Load style-guide.md content."""
        return self._read_file(_FILE_MAP["style_guide"])

    def get_internal_links(self) -> str:
        """Load internal-links-map.md content."""
        return self._read_file(_FILE_MAP["internal_links"])

    def get_target_keywords(self) -> str:
        """Load target-keywords.md content."""
        return self._read_file(_FILE_MAP["target_keywords"])

    def get_competitor_analysis(self) -> str:
        """Load competitor-analysis.md content."""
        return self._read_file(_FILE_MAP["competitor_analysis"])

    def get_full_context(self) -> dict[str, str]:
        """Return all editorial context as a dict.

        Keys: brand_voice, style_guide, internal_links, target_keywords, competitor_analysis.
        Values are the raw markdown content (or '' if unavailable).
        """
        return {key: self._read_file(filename) for key, filename in _FILE_MAP.items()}
