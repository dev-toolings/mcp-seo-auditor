"""Tests for SeoContentInput schema."""

import json

import pytest
from pydantic import ValidationError

from seo_server.schemas.content import SeoContentInput


class TestSeoContentInput:
    def test_valid_minimal(self):
        m = SeoContentInput(action="write")
        assert m.action == "write"
        assert m.target_url is None
        assert m.target_keyword == ""
        assert m.content == ""
        assert m.language == "fr"
        assert m.tone == ""
        assert m.word_count == 2500

    def test_all_valid_actions(self):
        for action in ("write", "optimize", "meta", "headlines", "humanize", "research"):
            m = SeoContentInput(action=action)
            assert m.action == action

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            SeoContentInput(action="invalid")

    def test_json_string_coercion(self):
        """MCPInput should accept a JSON string and parse it."""
        data = json.dumps({"action": "write", "target_keyword": "seo tools"})
        m = SeoContentInput.model_validate(data)
        assert m.action == "write"
        assert m.target_keyword == "seo tools"

    def test_safe_url_validation(self):
        m = SeoContentInput(action="meta", target_url="https://example.com/page")
        assert m.target_url == "https://example.com/page"

    def test_safe_url_ssrf_rejected(self):
        with pytest.raises((ValidationError, Exception)):
            SeoContentInput(action="meta", target_url="http://127.0.0.1/admin")

    def test_defaults(self):
        m = SeoContentInput(action="humanize", content="Some AI text to humanize.")
        assert m.language == "fr"
        assert m.word_count == 2500
        assert m.tone == ""
        assert m.target_keyword == ""
        assert m.target_url is None

    def test_custom_values(self):
        m = SeoContentInput(
            action="write",
            target_keyword="best seo tools 2026",
            language="en",
            tone="professional",
            word_count=3000,
        )
        assert m.target_keyword == "best seo tools 2026"
        assert m.language == "en"
        assert m.tone == "professional"
        assert m.word_count == 3000

    def test_optimize_with_content(self):
        m = SeoContentInput(
            action="optimize",
            content="Existing article text here.",
            target_keyword="seo audit",
        )
        assert m.content == "Existing article text here."
        assert m.target_keyword == "seo audit"
