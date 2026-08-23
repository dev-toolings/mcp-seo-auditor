"""Structured data (JSON-LD / Schema.org) validation service."""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Required and recommended fields per Schema.org type
SCHEMA_REQUIREMENTS: dict[str, dict[str, list[str]]] = {
    "Product": {
        "required": ["name", "image"],
        "recommended": ["description", "sku", "brand", "offers", "review", "aggregateRating"],
    },
    "Article": {
        "required": ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher", "description"],
    },
    "NewsArticle": {
        "required": ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher"],
    },
    "BlogPosting": {
        "required": ["headline", "author", "datePublished"],
        "recommended": ["image", "dateModified", "publisher"],
    },
    "FAQPage": {
        "required": ["mainEntity"],
        "recommended": [],
    },
    "BreadcrumbList": {
        "required": ["itemListElement"],
        "recommended": [],
    },
    "Organization": {
        "required": ["name"],
        "recommended": ["url", "logo", "contactPoint", "sameAs"],
    },
    "LocalBusiness": {
        "required": ["name", "address"],
        "recommended": ["telephone", "openingHours", "geo", "image", "url"],
    },
    "WebSite": {
        "required": ["name", "url"],
        "recommended": ["potentialAction"],
    },
    "Event": {
        "required": ["name", "startDate", "location"],
        "recommended": ["description", "endDate", "image", "offers", "performer", "organizer"],
    },
    "Recipe": {
        "required": ["name", "image"],
        "recommended": [
            "author",
            "prepTime",
            "cookTime",
            "recipeIngredient",
            "recipeInstructions",
            "nutrition",
        ],
    },
    "Review": {
        "required": ["itemReviewed", "author"],
        "recommended": ["reviewRating", "datePublished", "reviewBody"],
    },
    "HowTo": {
        "required": ["name", "step"],
        "recommended": ["description", "image", "totalTime", "supply", "tool"],
    },
    "VideoObject": {
        "required": ["name", "description", "thumbnailUrl", "uploadDate"],
        "recommended": ["contentUrl", "duration", "embedUrl"],
    },
}


@dataclass
class SchemaValidationResult:
    """Result of validating a single structured data block."""

    schema_type: str
    is_valid: bool
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    fields_present: list[str] = field(default_factory=list)


@dataclass
class StructuredDataReport:
    """Report for structured data validation of a URL."""

    url: str
    schemas_found: list[SchemaValidationResult] = field(default_factory=list)
    total_schemas: int = 0
    valid_schemas: int = 0
    recommendations: list[str] = field(default_factory=list)


class StructuredDataValidatorService:
    """Validate JSON-LD structured data against Schema.org requirements."""

    def validate_page(self, url: str, structured_data: list[dict]) -> StructuredDataReport:
        """Validate all structured data blocks from a page."""
        report = StructuredDataReport(url=url)

        for data in structured_data:
            results = self._validate_block(data)
            report.schemas_found.extend(results)

        report.total_schemas = len(report.schemas_found)
        report.valid_schemas = sum(1 for s in report.schemas_found if s.is_valid)
        report.recommendations = self._generate_recommendations(report)

        return report

    def _validate_block(self, data: dict) -> list[SchemaValidationResult]:
        """Validate a single JSON-LD block (may contain @graph)."""
        results = []

        if "@graph" in data:
            for item in data["@graph"]:
                if isinstance(item, dict):
                    result = self._validate_schema(item)
                    if result:
                        results.append(result)
        else:
            result = self._validate_schema(data)
            if result:
                results.append(result)

        return results

    def _validate_schema(self, data: dict) -> SchemaValidationResult | None:
        """Validate a single schema object against requirements."""
        schema_type = data.get("@type", "")

        # Handle list types (e.g., ["Product", "IndividualProduct"])
        if isinstance(schema_type, list):
            schema_type = schema_type[0] if schema_type else ""

        if not schema_type:
            return None

        requirements = SCHEMA_REQUIREMENTS.get(schema_type)
        if not requirements:
            # Unknown type - still report it
            return SchemaValidationResult(
                schema_type=schema_type,
                is_valid=True,
                fields_present=[k for k in data.keys() if not k.startswith("@")],
            )

        # Check required fields
        missing_required = [
            f for f in requirements["required"] if f not in data or data[f] is None or data[f] == ""
        ]

        # Check recommended fields
        missing_recommended = [
            f
            for f in requirements["recommended"]
            if f not in data or data[f] is None or data[f] == ""
        ]

        fields_present = [k for k in data.keys() if not k.startswith("@")]

        return SchemaValidationResult(
            schema_type=schema_type,
            is_valid=len(missing_required) == 0,
            missing_required=missing_required,
            missing_recommended=missing_recommended,
            fields_present=fields_present,
        )

    def _generate_recommendations(self, report: StructuredDataReport) -> list[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        if report.total_schemas == 0:
            recommendations.append(
                "No structured data found. Consider adding JSON-LD markup for better search appearance."
            )
            return recommendations

        for schema in report.schemas_found:
            if schema.missing_required:
                recommendations.append(
                    f"{schema.schema_type}: Add required fields: {', '.join(schema.missing_required)}"
                )
            if schema.missing_recommended:
                recommendations.append(
                    f"{schema.schema_type}: Consider adding: {', '.join(schema.missing_recommended[:3])}"
                )

        if report.valid_schemas == report.total_schemas:
            recommendations.append("All structured data schemas are valid.")

        return recommendations

    def to_dict(self, report: StructuredDataReport) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "url": report.url,
            "total_schemas": report.total_schemas,
            "valid_schemas": report.valid_schemas,
            "schemas": [
                {
                    "type": s.schema_type,
                    "is_valid": s.is_valid,
                    "missing_required": s.missing_required,
                    "missing_recommended": s.missing_recommended,
                    "fields_present": s.fields_present,
                }
                for s in report.schemas_found
            ],
            "recommendations": report.recommendations,
        }
