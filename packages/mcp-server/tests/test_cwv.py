"""Tests for Core Web Vitals service."""

from app.services.core_web_vitals import CoreWebVitalsService


class TestCoreWebVitals:
    """Test Core Web Vitals service."""

    def test_parse_response_full(self):
        """Test parsing of a full PageSpeed Insights response."""
        service = CoreWebVitalsService()

        mock_data = {
            "lighthouseResult": {
                "categories": {
                    "performance": {"score": 0.85},
                },
                "audits": {
                    "largest-contentful-paint": {
                        "numericValue": 2500,
                        "displayValue": "2.5 s",
                        "score": 0.7,
                    },
                    "cumulative-layout-shift": {
                        "numericValue": 0.05,
                        "displayValue": "0.05",
                        "score": 0.95,
                    },
                    "first-contentful-paint": {
                        "numericValue": 1200,
                        "displayValue": "1.2 s",
                        "score": 0.9,
                    },
                    "server-response-time": {
                        "numericValue": 200,
                        "displayValue": "200 ms",
                        "score": 0.95,
                    },
                    "speed-index": {
                        "numericValue": 3000,
                        "displayValue": "3.0 s",
                        "score": 0.8,
                    },
                    "render-blocking-resources": {
                        "title": "Eliminate render-blocking resources",
                        "description": "Resources blocking paint.",
                        "score": 0.5,
                        "details": {
                            "type": "opportunity",
                            "overallSavingsMs": 500,
                        },
                    },
                },
            },
            "loadingExperience": {
                "metrics": {
                    "LARGEST_CONTENTFUL_PAINT_MS": {
                        "percentile": 2500,
                        "category": "AVERAGE",
                    },
                },
            },
        }

        result = service._parse_response("https://www.iautos.fr", "mobile", mock_data)

        assert result["url"] == "https://www.iautos.fr"
        assert result["strategy"] == "mobile"
        assert result["performance_score"] == 85
        assert "LCP" in result["metrics"]
        assert "CLS" in result["metrics"]
        assert "FCP" in result["metrics"]
        assert "TTFB" in result["metrics"]
        assert result["metrics"]["LCP"]["value"] == 2500
        assert len(result["opportunities"]) >= 1
        assert result["opportunities"][0]["savings_ms"] == 500

    def test_parse_response_empty(self):
        """Test parsing of an empty response."""
        service = CoreWebVitalsService()

        mock_data = {
            "lighthouseResult": {
                "categories": {},
                "audits": {},
            },
        }

        result = service._parse_response("https://www.iautos.fr", "desktop", mock_data)

        assert result["url"] == "https://www.iautos.fr"
        assert result["performance_score"] is None
        assert result["metrics"] == {}
        assert result["opportunities"] == []

    def test_parse_response_no_field_data(self):
        """Test parsing when no CrUX field data is available."""
        service = CoreWebVitalsService()

        mock_data = {
            "lighthouseResult": {
                "categories": {"performance": {"score": 0.5}},
                "audits": {},
            },
        }

        result = service._parse_response("https://www.iautos.fr", "mobile", mock_data)

        assert result["field_data"] is None

    def test_opportunities_sorted(self):
        """Test that opportunities are sorted by savings_ms descending."""
        service = CoreWebVitalsService()

        mock_data = {
            "lighthouseResult": {
                "categories": {"performance": {"score": 0.5}},
                "audits": {
                    "opp1": {
                        "title": "Small saving",
                        "description": "Small",
                        "score": 0.5,
                        "details": {"type": "opportunity", "overallSavingsMs": 100},
                    },
                    "opp2": {
                        "title": "Large saving",
                        "description": "Large",
                        "score": 0.3,
                        "details": {"type": "opportunity", "overallSavingsMs": 1000},
                    },
                },
            },
        }

        result = service._parse_response("https://www.iautos.fr", "mobile", mock_data)

        assert len(result["opportunities"]) == 2
        assert result["opportunities"][0]["savings_ms"] > result["opportunities"][1]["savings_ms"]

    def test_service_init_default(self):
        """Test default service initialization."""
        service = CoreWebVitalsService()
        assert service.timeout == 60

    def test_service_init_custom(self):
        """Test custom service initialization."""
        service = CoreWebVitalsService(api_key="test-key", timeout=30)
        assert service.api_key == "test-key"
        assert service.timeout == 30
