"""Tests for cross-tool correlator."""

from app.services.ai.cross_correlator import CrossToolCorrelator


class TestCrossToolCorrelator:
    def setup_method(self):
        self.correlator = CrossToolCorrelator()

    def test_empty_data(self):
        result = self.correlator.correlate({})
        assert result["urls_tracked"] == 0
        assert result["compound_issues"] == []
        assert result["compound_issues_count"] == 0

    def test_content_signals(self):
        data = {
            "content": {
                "pages": [
                    {
                        "url": "https://www.iautos.fr/thin",
                        "word_count": 30,
                        "issues": ["Missing meta description", "Missing H1 tag"],
                    },
                    {
                        "url": "https://www.iautos.fr/ok",
                        "word_count": 500,
                        "issues": [],
                    },
                ]
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 1  # Only thin page has issues

        matrix = result["url_matrix"]
        thin_entry = next((m for m in matrix if m["url"] == "https://www.iautos.fr/thin"), None)
        assert thin_entry is not None
        assert "thin_content" in thin_entry["signals"]

    def test_compound_issue_detection(self):
        """Page with 3+ issues should be flagged as compound."""
        data = {
            "content": {
                "pages": [
                    {
                        "url": "https://www.iautos.fr/bad",
                        "word_count": 20,
                        "issues": ["Missing meta description", "Missing H1 tag"],
                    }
                ]
            },
            "structured_data": {
                "results": [
                    {"url": "https://www.iautos.fr/bad", "valid_schemas": 0},
                ]
            },
            "internal_links": {
                "orphan_pages": ["https://www.iautos.fr/bad"],
            },
        }
        result = self.correlator.correlate(data)

        # Should have compound issue (thin + missing_meta + missing_h1 + missing_schema + orphan)
        assert result["compound_issues_count"] >= 1
        compound = result["compound_issues"][0]
        assert compound["url"] == "https://www.iautos.fr/bad"
        assert compound["signal_count"] >= 3

    def test_technical_signals(self):
        data = {
            "technical": {
                "canonical_issues": [
                    {"url": "https://www.iautos.fr/dup", "issue": "Canonical mismatch"}
                ],
                "meta_robots_issues": [
                    {"url": "https://www.iautos.fr/noindex", "issue": "noindex in sitemap"}
                ],
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 2

    def test_link_signals(self):
        data = {
            "internal_links": {
                "orphan_pages": ["https://www.iautos.fr/orphan1"],
                "broken_internal_links": [
                    {"target": "https://www.iautos.fr/404", "source": "https://www.iautos.fr/page"}
                ],
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 2

    def test_cwv_signals(self):
        data = {
            "cwv": {
                "results": [
                    {"url": "https://www.iautos.fr/slow", "performance_score": 30},
                    {"url": "https://www.iautos.fr/fast", "performance_score": 90},
                ]
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 1  # Only slow page

    def test_eeat_signals(self):
        data = {
            "eeat": {
                "page_results": [
                    {"url": "https://www.iautos.fr/weak", "eeat_score": 20},
                    {"url": "https://www.iautos.fr/strong", "eeat_score": 80},
                ]
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 1  # Only weak page

    def test_cannibalization_signals(self):
        data = {
            "cannibalization": {
                "groups": [
                    {"urls": ["https://www.iautos.fr/a", "https://www.iautos.fr/b"]},
                ]
            }
        }
        result = self.correlator.correlate(data)
        assert result["urls_tracked"] == 2

    def test_quick_wins(self):
        data = {
            "content": {
                "pages": [
                    {
                        "url": "https://www.iautos.fr/easy",
                        "word_count": 500,
                        "issues": ["Missing meta description"],
                    }
                ]
            }
        }
        result = self.correlator.correlate(data)
        assert len(result["quick_wins"]) >= 1
        assert result["quick_wins"][0]["effort"] == "low"

    def test_severity_summary(self):
        data = {
            "content": {
                "pages": [
                    {"url": "https://www.leboncoin.fr", "word_count": 10, "issues": []},
                    {"url": "https://www.lacentrale.fr", "word_count": 20, "issues": []},
                ]
            }
        }
        result = self.correlator.correlate(data)
        summary = result["severity_summary"]
        assert summary["total_urls_with_issues"] == 2
        assert "thin_content" in summary["signal_frequency"]
