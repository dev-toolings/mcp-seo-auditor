"""Tests for EditorialContextService."""

from pathlib import Path

import pytest

from app.services.editorial.context import EditorialContextService


@pytest.fixture()
def populated_dir(tmp_path: Path) -> Path:
    """Create a temp directory with all editorial context files."""
    files = {
        "brand-voice.md": "# Brand Voice\nWe are bold and clear.",
        "style-guide.md": "# Style Guide\nMax 25 words per sentence.",
        "internal-links-map.md": "# Internal Links\n- /product -> product page",
        "target-keywords.md": "# Keywords\n- seo audit\n- site crawler",
        "competitor-analysis.md": "# Competitors\n## Rival Inc\nStrong backlinks.",
    }
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    return tmp_path


class TestLoadFiles:
    """Test reading individual context files."""

    def test_get_brand_voice(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        result = svc.get_brand_voice()
        assert "Brand Voice" in result
        assert "bold and clear" in result

    def test_get_style_guide(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        result = svc.get_style_guide()
        assert "25 words" in result

    def test_get_internal_links(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        result = svc.get_internal_links()
        assert "/product" in result

    def test_get_target_keywords(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        result = svc.get_target_keywords()
        assert "seo audit" in result
        assert "site crawler" in result

    def test_get_competitor_analysis(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        result = svc.get_competitor_analysis()
        assert "Rival Inc" in result


class TestMissingFiles:
    """Test graceful handling when files don't exist."""

    def test_missing_file_returns_empty(self, tmp_path: Path):
        svc = EditorialContextService(str(tmp_path))
        assert svc.get_brand_voice() == ""
        assert svc.get_style_guide() == ""
        assert svc.get_internal_links() == ""
        assert svc.get_target_keywords() == ""
        assert svc.get_competitor_analysis() == ""

    def test_partial_files(self, tmp_path: Path):
        (tmp_path / "brand-voice.md").write_text("# Brand", encoding="utf-8")
        svc = EditorialContextService(str(tmp_path))
        assert svc.get_brand_voice() == "# Brand"
        assert svc.get_style_guide() == ""


class TestEmptyContextDir:
    """Test behavior when context_dir is empty or unset."""

    def test_empty_string_returns_empty(self):
        svc = EditorialContextService("")
        assert svc.get_brand_voice() == ""
        assert svc.get_full_context() == {
            "brand_voice": "",
            "style_guide": "",
            "internal_links": "",
            "target_keywords": "",
            "competitor_analysis": "",
        }

    def test_default_constructor(self):
        svc = EditorialContextService()
        assert svc.get_brand_voice() == ""


class TestGetFullContext:
    """Test the get_full_context aggregation method."""

    def test_full_context_structure(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        ctx = svc.get_full_context()
        assert isinstance(ctx, dict)
        expected_keys = {
            "brand_voice",
            "style_guide",
            "internal_links",
            "target_keywords",
            "competitor_analysis",
        }
        assert set(ctx.keys()) == expected_keys

    def test_full_context_values(self, populated_dir: Path):
        svc = EditorialContextService(str(populated_dir))
        ctx = svc.get_full_context()
        assert "Brand Voice" in ctx["brand_voice"]
        assert "25 words" in ctx["style_guide"]
        assert "/product" in ctx["internal_links"]
        assert "seo audit" in ctx["target_keywords"]
        assert "Rival Inc" in ctx["competitor_analysis"]

    def test_full_context_all_empty_when_no_dir(self):
        svc = EditorialContextService("")
        ctx = svc.get_full_context()
        assert all(v == "" for v in ctx.values())

    def test_full_context_all_empty_when_missing_dir(self, tmp_path: Path):
        svc = EditorialContextService(str(tmp_path / "nonexistent"))
        ctx = svc.get_full_context()
        assert all(v == "" for v in ctx.values())


class TestFileContent:
    """Test that file content is read exactly as written."""

    def test_unicode_content(self, tmp_path: Path):
        content = "# Voix de Marque\nNotre ton est chaleureux et precis."
        (tmp_path / "brand-voice.md").write_text(content, encoding="utf-8")
        svc = EditorialContextService(str(tmp_path))
        assert svc.get_brand_voice() == content

    def test_multiline_content(self, tmp_path: Path):
        content = "# Keywords\n\n- keyword one\n- keyword two\n- keyword three\n"
        (tmp_path / "target-keywords.md").write_text(content, encoding="utf-8")
        svc = EditorialContextService(str(tmp_path))
        assert svc.get_target_keywords() == content
