"""Keyword cannibalization detector service."""

import logging
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.models.cannibalization import CannibalizationGroup
from app.services.keyword_extractor import KeywordExtractorService

logger = logging.getLogger(__name__)


class CannibalizationDetectorService:
    """Detect pages that cannibalize each other for keywords."""

    def __init__(
        self,
        similarity_threshold: float | None = None,
        semantic_params: dict[str, list[str]] | None = None,
    ):
        self.similarity_threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD
        self.keyword_extractor = KeywordExtractorService()
        self.semantic_params = semantic_params or {}

    def detect(self, page_keywords: dict[str, list[str]]) -> list[CannibalizationGroup]:
        """
        Detect cannibalization between pages based on keywords.

        Args:
            page_keywords: Dict mapping URL -> list of keywords

        Returns:
            List of cannibalization groups
        """
        groups = []
        urls = list(page_keywords.keys())
        processed = set()

        for i, url1 in enumerate(urls):
            if url1 in processed:
                continue

            keywords1 = page_keywords[url1]
            if not keywords1:
                continue

            similar_urls = [url1]
            shared_keywords = set(keywords1)
            max_similarity = 0.0

            for url2 in urls[i + 1 :]:
                if url2 in processed:
                    continue

                keywords2 = page_keywords.get(url2, [])
                if not keywords2:
                    continue

                similarity = self.keyword_extractor.calculate_similarity(keywords1, keywords2)

                if similarity >= self.similarity_threshold:
                    similar_urls.append(url2)
                    shared_keywords &= set(keywords2)
                    max_similarity = max(max_similarity, similarity)

            if len(similar_urls) > 1:
                processed.update(similar_urls)

                best_url = min(similar_urls, key=lambda u: (u.count("?"), len(u)))

                groups.append(
                    CannibalizationGroup(
                        urls=similar_urls,
                        shared_keywords=list(shared_keywords)[:10],
                        similarity_score=max_similarity,
                        recommendation=f"Consolidate content to {best_url} and redirect others",
                    )
                )

        return groups

    def detect_url_cannibalization(self, urls: list[str]) -> list[CannibalizationGroup]:
        """
        Detect URL pattern cannibalization (query params vs clean routes).

        Generic detection: extracts query parameter values and searches for
        equivalent clean route URLs containing those values.
        """
        groups: list[CannibalizationGroup] = []

        # Separate URLs with and without query params
        query_urls = [u for u in urls if "?" in u]
        clean_urls = [u for u in urls if "?" not in u]

        if not query_urls or not clean_urls:
            return groups

        # Index clean URL path segments for fast lookup
        clean_segments: dict[str, list[str]] = defaultdict(list)
        for url in clean_urls:
            parsed = urlparse(url)
            parts = [p.lower() for p in parsed.path.split("/") if p]
            for part in parts:
                clean_segments[part].append(url)

        for url in query_urls:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)

            # Extract all param values
            param_values: list[str] = []
            for key, values in params.items():
                # Use semantic_params mapping if provided
                if self.semantic_params and key in self.semantic_params:
                    param_values.extend(v.lower() for v in values)
                elif not self.semantic_params:
                    param_values.extend(v.lower() for v in values)

            if not param_values:
                continue

            # Find clean URLs containing matching segments
            matching_clean = set()
            for value in param_values:
                for clean_url in clean_segments.get(value, []):
                    matching_clean.add(clean_url)

            if matching_clean:
                all_urls = [url] + list(matching_clean)
                best_url = min(matching_clean, key=len)

                groups.append(
                    CannibalizationGroup(
                        urls=all_urls,
                        shared_keywords=param_values[:5],
                        similarity_score=1.0,
                        recommendation=f"Use canonical to {best_url}, remove query param URLs from sitemap",
                    )
                )

        return groups

    def generate_recommendations(self, groups: list[CannibalizationGroup]) -> list[str]:
        """Generate recommendations based on detected cannibalization."""
        recommendations = []

        if not groups:
            recommendations.append("No keyword cannibalization detected")
            return recommendations

        url_pattern_issues = sum(1 for g in groups if g.similarity_score == 1.0)
        keyword_issues = len(groups) - url_pattern_issues

        if url_pattern_issues > 0:
            recommendations.append(
                f"Resolve {url_pattern_issues} URL duplication cases (query params vs clean routes) "
                "using canonical tags"
            )
            recommendations.append(
                "Remove query param URLs from the sitemap, keep only clean routes"
            )

        if keyword_issues > 0:
            recommendations.append(
                f"Analyze {keyword_issues} groups of pages targeting the same keywords"
            )
            recommendations.append("Differentiate content or consolidate similar pages")

        if len(groups) > 10:
            recommendations.append(
                "High number of cannibalization issues - review overall content strategy"
            )

        return recommendations
