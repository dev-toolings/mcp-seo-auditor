"""Tests for structured data validator service."""

from app.services.structured_data_validator import StructuredDataValidatorService


class TestStructuredDataValidator:
    """Test structured data validation."""

    def test_valid_product_schema(self):
        """Test validation of a valid Product schema."""
        validator = StructuredDataValidatorService()

        data = [{"@type": "Product", "name": "Widget", "image": "https://www.iautos.fr/img.jpg"}]
        report = validator.validate_page("https://www.iautos.fr/product", data)

        assert report.total_schemas == 1
        assert report.valid_schemas == 1
        assert report.schemas_found[0].is_valid is True
        assert len(report.schemas_found[0].missing_required) == 0

    def test_invalid_product_schema_missing_fields(self):
        """Test validation of Product schema with missing required fields."""
        validator = StructuredDataValidatorService()

        data = [{"@type": "Product", "description": "A widget"}]
        report = validator.validate_page("https://www.iautos.fr/product", data)

        assert report.total_schemas == 1
        assert report.valid_schemas == 0
        assert "name" in report.schemas_found[0].missing_required
        assert "image" in report.schemas_found[0].missing_required

    def test_article_schema(self):
        """Test validation of Article schema."""
        validator = StructuredDataValidatorService()

        data = [
            {
                "@type": "Article",
                "headline": "Test Article",
                "author": {"@type": "Person", "name": "John"},
                "datePublished": "2024-01-01",
            }
        ]
        report = validator.validate_page("https://www.iautos.fr/article", data)

        assert report.valid_schemas == 1

    def test_no_structured_data(self):
        """Test page with no structured data."""
        validator = StructuredDataValidatorService()

        report = validator.validate_page("https://www.iautos.fr/page", [])

        assert report.total_schemas == 0
        assert len(report.recommendations) > 0
        assert "No structured data found" in report.recommendations[0]

    def test_graph_parsing(self):
        """Test parsing of @graph structured data."""
        validator = StructuredDataValidatorService()

        data = [
            {
                "@graph": [
                    {"@type": "WebSite", "name": "Example", "url": "https://www.iautos.fr"},
                    {"@type": "Organization", "name": "Example Corp"},
                ]
            }
        ]
        report = validator.validate_page("https://www.iautos.fr", data)

        assert report.total_schemas == 2

    def test_unknown_schema_type(self):
        """Test handling of unknown schema type."""
        validator = StructuredDataValidatorService()

        data = [{"@type": "CustomType", "field1": "value1"}]
        report = validator.validate_page("https://www.iautos.fr", data)

        assert report.total_schemas == 1
        assert report.schemas_found[0].is_valid is True  # Unknown types pass

    def test_to_dict(self):
        """Test dictionary serialization."""
        validator = StructuredDataValidatorService()

        data = [{"@type": "Product", "name": "Widget", "image": "img.jpg"}]
        report = validator.validate_page("https://www.iautos.fr", data)
        result = validator.to_dict(report)

        assert "url" in result
        assert "total_schemas" in result
        assert "schemas" in result
        assert "recommendations" in result

    def test_faq_schema(self):
        """Test FAQPage schema validation."""
        validator = StructuredDataValidatorService()

        data = [{"@type": "FAQPage", "mainEntity": [{"@type": "Question"}]}]
        report = validator.validate_page("https://www.iautos.fr/faq", data)

        assert report.valid_schemas == 1

    def test_list_type(self):
        """Test handling of list @type."""
        validator = StructuredDataValidatorService()

        data = [{"@type": ["Product", "IndividualProduct"], "name": "Widget", "image": "img.jpg"}]
        report = validator.validate_page("https://www.iautos.fr", data)

        assert report.total_schemas == 1
        assert report.schemas_found[0].schema_type == "Product"
