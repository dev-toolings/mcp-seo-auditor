"""Schema coverage checker for GEO analysis.

Extends StructuredDataValidatorService to evaluate schema completeness
for AI engine optimization. Score 0-100, weight 25%.
"""

import logging

from app.core.scoring import (
    AI_PRIORITY_SCHEMAS,
    AUTHORITATIVE_SAMEAS_HOSTS,
    SCHEMA_PRIORITY_POINTS,
    SCHEMA_SUB_WEIGHTS,
)
from app.services.structured_data_validator import StructuredDataValidatorService

logger = logging.getLogger(__name__)


class SchemaCoverageChecker:
    """Evaluate structured data coverage for AI engine readiness."""

    def __init__(self):
        self.base_validator = StructuredDataValidatorService()

    def check(self, url: str, structured_data: list[dict]) -> dict:
        """Analyze structured data coverage for GEO readiness.

        Args:
            url: Page URL
            structured_data: List of JSON-LD blocks extracted from the page

        Returns:
            dict with score (0-100), details (dict), issues (list[str])
        """
        if not structured_data:
            return {
                "score": 0,
                "details": {"schemas_found": [], "total_schemas": 0},
                "issues": [
                    "No structured data found. Add JSON-LD markup to improve AI discoverability."
                ],
            }

        # Use base validator for standard checks
        base_report = self.base_validator.validate_page(url, structured_data)

        # Extract all schema items for deeper analysis
        all_schemas = self._extract_all_schemas(structured_data)
        schema_types = {s.get("@type", "") for s in all_schemas}
        # Normalize list types
        normalized_types: set[str] = set()
        for t in schema_types:
            if isinstance(t, list):
                normalized_types.update(t)
            elif t:
                normalized_types.add(t)

        # Sub-score calculations
        presence_score = self._score_basic_presence(base_report)
        speakable_score = self._score_speakable(all_schemas)
        priority_score = self._score_ai_priority_schemas(normalized_types)
        nesting_score = self._score_nesting_quality(structured_data)
        author_score = self._score_author_completeness(all_schemas)
        entity_score, entity_details = self._score_entity_clarity(all_schemas)

        # Weighted overall score
        overall = int(
            presence_score * SCHEMA_SUB_WEIGHTS["presence"]
            + speakable_score * SCHEMA_SUB_WEIGHTS["speakable"]
            + priority_score * SCHEMA_SUB_WEIGHTS["priority"]
            + nesting_score * SCHEMA_SUB_WEIGHTS["nesting"]
            + author_score * SCHEMA_SUB_WEIGHTS["author"]
            + entity_score * SCHEMA_SUB_WEIGHTS["entity_clarity"]
        )
        overall = max(0, min(100, overall))

        details = {
            "schemas_found": list(normalized_types),
            "total_schemas": base_report.total_schemas,
            "valid_schemas": base_report.valid_schemas,
            "basic_presence": {"score": presence_score},
            "speakable": {"score": speakable_score},
            "ai_priority_schemas": {
                "score": priority_score,
                "found": list(normalized_types & AI_PRIORITY_SCHEMAS.keys()),
            },
            "nesting_quality": {"score": nesting_score},
            "author_completeness": {"score": author_score},
            "entity_clarity": {"score": entity_score, **entity_details},
        }

        issues = self._collect_issues(base_report, normalized_types, speakable_score, author_score)

        return {"score": overall, "details": details, "issues": issues}

    def _score_entity_clarity(self, all_schemas: list[dict]) -> tuple[int, dict]:
        """Reward `sameAs` links to authoritative identity graphs (Wikidata, LinkedIn…).

        Clear entity disambiguation helps AI engines resolve who/what a page is about,
        which is a strong citation and Knowledge-Graph signal.
        """
        same_as_values: list[str] = []

        def _walk(node):
            if isinstance(node, dict):
                sa = node.get("sameAs")
                if isinstance(sa, str):
                    same_as_values.append(sa)
                elif isinstance(sa, list):
                    same_as_values.extend(v for v in sa if isinstance(v, str))
                for v in node.values():
                    _walk(v)
            elif isinstance(node, list):
                for v in node:
                    _walk(v)

        for schema in all_schemas:
            _walk(schema)

        authoritative = sum(
            1
            for v in same_as_values
            if any(host in v.lower() for host in AUTHORITATIVE_SAMEAS_HOSTS)
        )
        if authoritative >= 2:
            score = 100
        elif authoritative == 1:
            score = 70
        elif same_as_values:
            score = 40  # has sameAs but not to an authoritative host
        else:
            score = 0
        return score, {
            "same_as_total": len(same_as_values),
            "authoritative_refs": authoritative,
        }

    def _extract_all_schemas(self, structured_data: list[dict]) -> list[dict]:
        """Flatten all schema items from JSON-LD blocks including @graph."""
        schemas = []
        for block in structured_data:
            if "@graph" in block:
                for item in block["@graph"]:
                    if isinstance(item, dict) and item.get("@type"):
                        schemas.append(item)
            elif block.get("@type"):
                schemas.append(block)
        return schemas

    def _score_basic_presence(self, base_report) -> int:
        """Score based on number and validity of schemas found."""
        if base_report.total_schemas == 0:
            return 0

        validity_ratio = base_report.valid_schemas / base_report.total_schemas
        count_score = min(100, base_report.total_schemas * 20)

        return int(validity_ratio * 50 + count_score * 0.5)

    def _score_speakable(self, schemas: list[dict]) -> int:
        """Check for speakable property on WebPage schemas.

        Scoring:
        - speakable with valid cssSelector or xpath → 100
        - speakable present but empty/invalid → 50 (partial)
        - No speakable but parent schema exists → 20
        - No parent schema → 0
        """
        has_parent_schema = False

        for schema in schemas:
            schema_type = schema.get("@type", "")
            if isinstance(schema_type, list):
                types = schema_type
            else:
                types = [schema_type]

            if not any(t in types for t in ("WebPage", "Article", "NewsArticle")):
                continue

            has_parent_schema = True

            if "speakable" not in schema:
                continue

            speakable = schema["speakable"]
            if not speakable:
                return 50  # Present but empty

            # Validate speakable has cssSelector or xpath with non-empty values
            if isinstance(speakable, dict):
                css = speakable.get("cssSelector", "")
                xpath = speakable.get("xpath", "")
                if (css and str(css).strip()) or (xpath and str(xpath).strip()):
                    return 100
                return 50  # Present but no valid selector
            elif isinstance(speakable, list):
                for item in speakable:
                    if isinstance(item, dict):
                        css = item.get("cssSelector", "")
                        xpath = item.get("xpath", "")
                        if (css and str(css).strip()) or (xpath and str(xpath).strip()):
                            return 100
                return 50  # Present but no valid selectors
            else:
                return 50  # Present but unexpected format

        return 20 if has_parent_schema else 0

    def _score_ai_priority_schemas(self, types: set[str]) -> int:
        """Score presence of AI-priority schema types."""
        if not types:
            return 0
        found = types & AI_PRIORITY_SCHEMAS.keys()
        if not found:
            return 10  # Some schema exists but none AI-priority

        # Each priority schema adds points
        score = 0
        if "FAQPage" in found:
            score += SCHEMA_PRIORITY_POINTS["FAQPage"]
        if "HowTo" in found:
            score += SCHEMA_PRIORITY_POINTS["HowTo"]
        if "Article" in found or "NewsArticle" in found or "BlogPosting" in found:
            score += SCHEMA_PRIORITY_POINTS["Article"]
        if "WebPage" in found:
            score += SCHEMA_PRIORITY_POINTS["WebPage"]

        return min(100, score)

    def _score_nesting_quality(self, structured_data: list[dict]) -> int:
        """Check for properly nested schemas vs flat."""
        if not structured_data:
            return 0

        has_graph = any("@graph" in block for block in structured_data)
        has_nested = False

        for block in structured_data:
            items = block.get("@graph", [block])
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key, value in item.items():
                    if key.startswith("@"):
                        continue
                    if isinstance(value, dict) and "@type" in value:
                        has_nested = True
                        break
                    if isinstance(value, list):
                        for v in value:
                            if isinstance(v, dict) and "@type" in v:
                                has_nested = True
                                break

        if has_graph and has_nested:
            return 100
        elif has_graph or has_nested:
            return 70
        else:
            return 40

    def _score_author_completeness(self, schemas: list[dict]) -> int:
        """For Article types, check author completeness."""
        article_types = {"Article", "NewsArticle", "BlogPosting"}
        article_schemas = []

        for schema in schemas:
            schema_type = schema.get("@type", "")
            if isinstance(schema_type, list):
                types = set(schema_type)
            else:
                types = {schema_type}

            if types & article_types:
                article_schemas.append(schema)

        if not article_schemas:
            return 50  # Neutral - no article to evaluate

        best_score = 0
        for article in article_schemas:
            author = article.get("author", {})
            if isinstance(author, list):
                author = author[0] if author else {}
            if isinstance(author, str):
                # Author as plain string
                best_score = max(best_score, 30)
                continue

            score = 0
            if author.get("name"):
                score += 40
            if author.get("url"):
                score += 30
            if author.get("sameAs"):
                score += 30
            best_score = max(best_score, score)

        return best_score

    def _collect_issues(
        self, base_report, types: set[str], speakable_score: int, author_score: int
    ) -> list[str]:
        """Collect GEO-specific schema issues."""
        issues = []

        if base_report.total_schemas == 0:
            issues.append("No structured data found.")
            return issues

        invalid = base_report.total_schemas - base_report.valid_schemas
        if invalid > 0:
            issues.append(f"{invalid} schema(s) have missing required fields.")

        if not types & AI_PRIORITY_SCHEMAS.keys():
            issues.append(
                "No AI-priority schemas found. Consider adding FAQPage, HowTo, or Article markup."
            )

        if speakable_score < 50:
            issues.append(
                "No 'speakable' property found on WebPage/Article schemas. "
                "Add speakable to improve voice search readiness."
            )

        if author_score < 50:
            issues.append(
                "Author information incomplete in Article schemas. "
                "Add author name, url, and sameAs properties."
            )

        return issues
