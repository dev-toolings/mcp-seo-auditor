"""JSON-LD Schema Generator — auto-detect page type and generate optimal structured data.

Crawls a URL, detects the page type (article, product, FAQ, how-to, etc.),
and generates the optimal JSON-LD structured data markup.
"""

import json
import logging
import re
from typing import Any, cast

logger = logging.getLogger(__name__)

# Page type detection patterns
PAGE_TYPE_PATTERNS = {
    "faq": [
        re.compile(r"(?i)(faq|frequently asked|questions?.*(fr[ée]quentes|courantes))"),
        re.compile(r"(?i)(q\s*&\s*a|q:\s|question\s*:)"),
    ],
    "how_to": [
        re.compile(r"(?i)(how to|comment|tutoriel|tutorial|guide|étape|step)"),
        re.compile(r"(?i)(instructions|procédure|procedure|marche à suivre)"),
    ],
    "product": [
        re.compile(r"(?i)(prix|price|acheter|buy|ajouter au panier|add to cart)"),
        re.compile(r"(?i)(product|produit|article|référence|sku)"),
    ],
    "article": [
        re.compile(r"(?i)(published|publié|author|auteur|date|article)"),
        re.compile(r"(?i)(blog|news|actualité|post)"),
    ],
    "local_business": [
        re.compile(r"(?i)(adresse|address|téléphone|phone|horaires|hours)"),
        re.compile(r"(?i)(contact|location|emplacement|plan d'accès)"),
    ],
    "recipe": [
        re.compile(r"(?i)(recette|recipe|ingrédients|ingredients|préparation)"),
        re.compile(r"(?i)(cuisson|cooking|temps de|minutes|portions|servings)"),
    ],
    "event": [
        re.compile(
            r"(?i)(\bévénement\b|\bevent\b|\blieu\b|\bvenue\b|\binscription\b|\bregister\b)"
        ),
        re.compile(r"(?i)(conférence|conference|webinar|atelier|workshop)"),
    ],
}

# JSON-LD templates
SCHEMA_TEMPLATES = {
    "article": {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "",
        "description": "",
        "author": {"@type": "Person", "name": ""},
        "datePublished": "",
        "dateModified": "",
        "publisher": {
            "@type": "Organization",
            "name": "",
            "logo": {"@type": "ImageObject", "url": ""},
        },
        "image": "",
        "mainEntityOfPage": {"@type": "WebPage", "@id": ""},
    },
    "faq": {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [],
    },
    "how_to": {
        "@context": "https://schema.org",
        "@type": "HowTo",
        "name": "",
        "description": "",
        "step": [],
    },
    "product": {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "",
        "description": "",
        "image": "",
        "brand": {"@type": "Brand", "name": ""},
        "offers": {
            "@type": "Offer",
            "price": "",
            "priceCurrency": "EUR",
            "availability": "https://schema.org/InStock",
        },
    },
    "local_business": {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": "",
        "description": "",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "",
            "addressLocality": "",
            "postalCode": "",
            "addressCountry": "",
        },
        "telephone": "",
        "openingHoursSpecification": [],
    },
    "recipe": {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "",
        "description": "",
        "recipeIngredient": [],
        "recipeInstructions": [],
        "prepTime": "",
        "cookTime": "",
        "recipeYield": "",
    },
    "event": {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": "",
        "description": "",
        "startDate": "",
        "endDate": "",
        "location": {"@type": "Place", "name": "", "address": ""},
        "organizer": {"@type": "Organization", "name": ""},
    },
    "webpage": {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": "",
        "description": "",
        "url": "",
    },
}


class SchemaGeneratorService:
    """Generate optimal JSON-LD structured data for web pages."""

    def __init__(self, crawler=None, ai_analyzer=None):
        self.crawler = crawler
        self.ai = ai_analyzer

    async def generate(
        self,
        url: str,
        page_type: str = "auto",
        language: str = "en",
    ) -> dict[str, Any]:
        """Generate JSON-LD for a URL.

        1. Crawl page content
        2. Detect page type (or use provided)
        3. Extract relevant data from content
        4. Generate JSON-LD
        5. If LLM available: enrich with better descriptions
        """
        if not self.crawler:
            return {"error": "Crawler not available"}

        # 1. Crawl
        pages = await self.crawler.crawl_pages([url])
        if not pages or pages[0].status_code != 200:
            status = pages[0].status_code if pages else "no response"
            return {"error": f"Failed to crawl {url}: HTTP {status}"}

        page = pages[0]

        # 2. Detect page type
        if page_type == "auto":
            page_type = self._detect_page_type(page)

        # 3. Generate schema
        schema = self._generate_schema(page, page_type, url)

        # 4. Detect existing schemas
        existing = page.structured_data or []

        return {
            "url": url,
            "detected_page_type": page_type,
            "generated_schema": schema,
            "json_ld": json.dumps(schema, indent=2, ensure_ascii=False),
            "html_snippet": (
                f'<script type="application/ld+json">\n'
                f"{json.dumps(schema, indent=2, ensure_ascii=False)}\n"
                f"</script>"
            ),
            "existing_schemas": [s.get("@type", "Unknown") for s in existing],
            "recommendations": self._get_recommendations(page_type, existing),
        }

    def _detect_page_type(self, page) -> str:
        """Auto-detect page type from content."""
        content = f"{page.title or ''} {page.h1 or ''} {page.content or ''}"
        content_lower = content.lower()

        scores: dict[str, int] = {}
        for ptype, patterns in PAGE_TYPE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = pattern.findall(content_lower)
                score += len(matches)
            if score > 0:
                scores[ptype] = score

        if not scores:
            return "webpage"

        return max(scores, key=lambda k: scores[k])

    def _generate_schema(self, page, page_type: str, url: str) -> dict:
        """Generate JSON-LD schema for the detected page type."""
        template = SCHEMA_TEMPLATES.get(page_type, SCHEMA_TEMPLATES["webpage"])
        schema = json.loads(json.dumps(template))  # Deep copy

        # Fill common fields
        if "name" in schema:
            schema["name"] = page.title or page.h1 or ""
        if "headline" in schema:
            schema["headline"] = page.title or page.h1 or ""
        if "description" in schema:
            schema["description"] = page.meta_description or ""
        if "url" in schema:
            schema["url"] = url

        # Type-specific filling
        if page_type == "article":
            schema["mainEntityOfPage"]["@id"] = url
            if page.meta_description:
                schema["description"] = page.meta_description

        elif page_type == "faq":
            # Extract Q&A pairs from content
            qa_pairs = self._extract_qa_pairs(page.content or "")
            schema["mainEntity"] = [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": a,
                    },
                }
                for q, a in qa_pairs[:10]
            ]

        elif page_type == "how_to":
            # Extract steps from content
            steps = self._extract_steps(page.content or "")
            schema["step"] = [
                {
                    "@type": "HowToStep",
                    "position": i + 1,
                    "name": step,
                    "text": step,
                }
                for i, step in enumerate(steps[:20])
            ]

        return schema

    def _extract_qa_pairs(self, content: str) -> list[tuple[str, str]]:
        """Extract question-answer pairs from content."""
        pairs = []

        # Pattern 1: Lines starting with question words
        lines = content.split("\n")
        current_q = None
        current_a: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            is_question = bool(
                re.match(
                    r"^(?:Q\s*[:.]|question\s*[:.]|\d+[\.\)]\s*"
                    r"|comment|pourquoi|quel|how|what|why|which)\s",
                    line,
                    re.IGNORECASE,
                )
            )

            if is_question or line.endswith("?"):
                if current_q and current_a:
                    pairs.append((current_q, " ".join(current_a)))
                current_q = line.rstrip("?") + "?"
                current_a = []
            elif current_q:
                current_a.append(line)

        if current_q and current_a:
            pairs.append((current_q, " ".join(current_a)))

        return pairs

    def _extract_steps(self, content: str) -> list[str]:
        """Extract step-by-step instructions from content."""
        steps = []

        # Pattern: numbered items or bullet points
        for match in re.finditer(
            r"(?:^|\n)\s*(?:\d+[\.\)]\s*|[-•]\s*|étape\s*\d*\s*[:.]?\s*)"
            r"(.+?)(?=\n|$)",
            content,
            re.IGNORECASE,
        ):
            step_text = match.group(1).strip()
            if len(step_text) > 10:
                steps.append(step_text)

        return steps

    def _get_recommendations(self, page_type: str, existing_schemas: list) -> list[str]:
        """Get schema recommendations based on page type and existing markup."""
        recommendations = []
        existing_types = {s.get("@type", "") for s in existing_schemas}

        schema_type = cast(dict, SCHEMA_TEMPLATES.get(page_type, {})).get("@type", "")
        if schema_type and schema_type not in existing_types:
            recommendations.append(f"Add {schema_type} schema — not currently present on page")

        # Always recommend BreadcrumbList
        if "BreadcrumbList" not in existing_types:
            recommendations.append(
                "Add BreadcrumbList schema for better navigation display in SERPs"
            )

        # Recommend WebPage if missing
        if "WebPage" not in existing_types and page_type != "webpage":
            recommendations.append("Consider adding WebPage schema as a wrapper for better context")

        if not recommendations:
            recommendations.append(
                "Page already has appropriate schema markup. Consider adding "
                "speakable markup for voice search optimization."
            )

        return recommendations
