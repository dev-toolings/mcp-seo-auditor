"""Content validation service."""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING

from app.core.config import settings
from app.models.issue import Issue
from app.services.content_readability import analyze as analyze_readability
from app.services.crawler_service import CrawledPage

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def content_score(issues_by_page: list[list[Issue]]) -> int:
    """Content score for a set of pages: the mean of each page's own score.

    A page loses 10 points per critical issue and 3 per warning. Summing those
    penalties across the whole crawl made the score depend on site size: 34
    warnings spread over any number of pages already floored it at 0.
    """
    if not issues_by_page:
        return 100
    page_scores = [
        max(
            0,
            100
            - 10 * sum(1 for i in issues if i.severity == "critical")
            - 3 * sum(1 for i in issues if i.severity == "warning"),
        )
        for issues in issues_by_page
    ]
    return round(sum(page_scores) / len(page_scores))


class ContentValidatorService:
    """Validate page content for SEO issues."""

    def __init__(
        self,
        min_content_words: int | None = None,
        thin_content_threshold: int | None = None,
        listing_url_patterns: list[str] | None = None,
    ):
        self.min_content_words = min_content_words or settings.MIN_CONTENT_WORDS
        self.thin_content_threshold = thin_content_threshold or settings.THIN_CONTENT_THRESHOLD
        self.listing_url_patterns = listing_url_patterns or []

    def validate(
        self,
        page: CrawledPage,
        check_thin_content: bool = True,
        check_empty_listings: bool = False,
        soup: BeautifulSoup | None = None,
        language: str = "en",
    ) -> list[Issue]:
        """Validate a single page for content issues."""
        issues = []

        # Check for HTTP errors
        if page.status_code != 200:
            issues.append(
                Issue(
                    issue_type="http_error",
                    severity="critical",
                    urls=[page.url],
                    description=f"HTTP {page.status_code} error",
                    recommendation="Fix the HTTP error or remove the URL from the sitemap",
                )
            )
            return issues

        # Check for thin content
        if check_thin_content:
            if page.word_count < self.thin_content_threshold:
                issues.append(
                    Issue(
                        issue_type="empty_page",
                        severity="critical",
                        urls=[page.url],
                        description=f"Nearly empty page ({page.word_count} words)",
                        recommendation="Add content or remove the page from the sitemap",
                    )
                )
            elif page.word_count < self.min_content_words:
                issues.append(
                    Issue(
                        issue_type="thin_content",
                        severity="warning",
                        urls=[page.url],
                        description=f"Thin content ({page.word_count} words, recommended minimum: {self.min_content_words})",
                        recommendation="Enrich the page content",
                    )
                )

        # Check for empty listings (generic)
        if check_empty_listings and page.item_count is not None:
            if page.item_count == 0:
                is_listing = not self.listing_url_patterns or any(
                    pattern in page.url for pattern in self.listing_url_patterns
                )
                if is_listing:
                    issues.append(
                        Issue(
                            issue_type="empty_listing",
                            severity="critical",
                            urls=[page.url],
                            description="Listing page with no items",
                            recommendation="Remove from sitemap or add noindex until items are available",
                        )
                    )

        # Check for missing meta description
        if not page.meta_description:
            issues.append(
                Issue(
                    issue_type="missing_meta_description",
                    severity="warning",
                    urls=[page.url],
                    description="Missing meta description",
                    recommendation="Add a unique and relevant meta description",
                )
            )

        # Check for missing title
        if not page.title:
            issues.append(
                Issue(
                    issue_type="missing_title",
                    severity="critical",
                    urls=[page.url],
                    description="Missing title tag",
                    recommendation="Add a unique and descriptive title tag",
                )
            )

        # Check for missing H1
        if not page.h1:
            issues.append(
                Issue(
                    issue_type="missing_h1",
                    severity="warning",
                    urls=[page.url],
                    description="Missing H1 tag",
                    recommendation="Add a unique and relevant H1",
                )
            )

        # Title and meta description length checks (only need page data)
        issues.extend(self.validate_title_length(page))
        issues.extend(self.validate_meta_description_length(page))

        # Checks requiring BeautifulSoup
        if soup is not None:
            issues.extend(self.validate_images(page, soup))
            issues.extend(self.validate_heading_hierarchy(page, soup))

        # Readability analysis (only for pages with enough content)
        if page.word_count >= 100 and page.content:
            readability = analyze_readability(page.content, language=language)
            if not readability.get("error"):
                if language == "fr":
                    ease_data = readability.get("kandel_moles_reading_ease", {})
                else:
                    ease_data = readability.get("flesch_reading_ease", {})
                ease_score = ease_data.get("score", 60) if isinstance(ease_data, dict) else 60
                if ease_score < 30:
                    issues.append(
                        Issue(
                            issue_type="low_readability",
                            severity="warning",
                            urls=[page.url],
                            description=(
                                f"Very low readability score ({ease_score:.0f}"
                                "/100). Content may be too complex for web"
                                " audience"
                            ),
                            recommendation=readability.get(
                                "seo_recommendation",
                                "Simplify sentence structure and use shorter words",
                            ),
                        )
                    )

        return issues

    def validate_title_length(self, page: CrawledPage) -> list[Issue]:
        """Check title tag length."""
        issues = []
        if page.title:
            title_len = len(page.title)
            if title_len < 30:
                issues.append(
                    Issue(
                        issue_type="title_too_short",
                        severity="warning",
                        urls=[page.url],
                        description=f"Title tag too short ({title_len} chars, recommended: 30-60)",
                        recommendation="Expand the title to include target keywords and be more descriptive (30-60 characters)",
                    )
                )
            elif title_len > 60:
                issues.append(
                    Issue(
                        issue_type="title_too_long",
                        severity="warning",
                        urls=[page.url],
                        description=f"Title tag too long ({title_len} chars, recommended: 30-60). May be truncated in SERPs",
                        recommendation="Shorten the title to 60 characters or less to prevent truncation in search results",
                    )
                )
        return issues

    def validate_meta_description_length(self, page: CrawledPage) -> list[Issue]:
        """Check meta description length."""
        issues = []
        if page.meta_description:
            desc_len = len(page.meta_description)
            if desc_len < 120:
                issues.append(
                    Issue(
                        issue_type="meta_description_too_short",
                        severity="info",
                        urls=[page.url],
                        description=f"Meta description too short ({desc_len} chars, recommended: 120-160)",
                        recommendation="Expand the meta description to fully utilize SERP space (120-160 characters)",
                    )
                )
            elif desc_len > 160:
                issues.append(
                    Issue(
                        issue_type="meta_description_too_long",
                        severity="info",
                        urls=[page.url],
                        description=f"Meta description too long ({desc_len} chars, recommended: 120-160). Will be truncated in SERPs",
                        recommendation="Shorten the meta description to 160 characters or less",
                    )
                )
        return issues

    def validate_images(self, page: CrawledPage, soup) -> list[Issue]:
        """Check images for alt text."""
        issues: list[Issue] = []
        images = soup.find_all("img")
        if not images:
            return issues

        missing_alt = [img for img in images if not img.get("alt")]

        total = len(images)
        missing_count = len(missing_alt)

        if missing_count > 0:
            ratio = missing_count / total * 100
            severity = "critical" if ratio > 50 else "warning"
            issues.append(
                Issue(
                    issue_type="images_missing_alt",
                    severity=severity,
                    urls=[page.url],
                    description=f"{missing_count}/{total} images missing alt text ({ratio:.0f}%)",
                    recommendation="Add descriptive alt text to all images for accessibility and image SEO",
                )
            )

        return issues

    def validate_heading_hierarchy(self, page: CrawledPage, soup) -> list[Issue]:
        """Check heading hierarchy."""
        issues = []

        # Check for multiple H1s
        h1_tags = soup.find_all("h1")
        if len(h1_tags) > 1:
            issues.append(
                Issue(
                    issue_type="multiple_h1",
                    severity="warning",
                    urls=[page.url],
                    description=f"Multiple H1 tags found ({len(h1_tags)}). Best practice: single H1 per page",
                    recommendation="Keep only one H1 tag per page that clearly describes the page content",
                )
            )

        # Check heading order (no skips: H1->H3 without H2)
        headings = []
        for level in range(1, 7):
            for tag in soup.find_all(f"h{level}"):
                headings.append(level)

        if headings:
            prev_level = 0
            for level in headings:
                if level > prev_level + 1 and prev_level > 0:
                    issues.append(
                        Issue(
                            issue_type="heading_hierarchy_skip",
                            severity="info",
                            urls=[page.url],
                            description=f"Heading hierarchy skips from H{prev_level} to H{level}. Missing H{prev_level + 1}",
                            recommendation=f"Add H{prev_level + 1} headings between H{prev_level} and H{level} for proper document outline",
                        )
                    )
                    break  # Only report first skip
                prev_level = level

        return issues

    def find_duplicate_titles(self, pages: list[CrawledPage]) -> list[Issue]:
        """Find pages with duplicate titles."""
        issues = []

        title_urls: dict[str, list[str]] = {}
        for page in pages:
            if page.title:
                title = page.title.strip().lower()
                if title not in title_urls:
                    title_urls[title] = []
                title_urls[title].append(page.url)

        for title, urls in title_urls.items():
            if len(urls) > 1:
                issues.append(
                    Issue(
                        issue_type="duplicate_title",
                        severity="warning",
                        urls=urls[:5],
                        description=f'Duplicate title on {len(urls)} pages: "{title[:50]}{"..." if len(title) > 50 else ""}"',
                        recommendation="Create unique titles for each page",
                    )
                )

        return issues

    def find_duplicate_meta_descriptions(self, pages: list[CrawledPage]) -> list[Issue]:
        """Find pages with duplicate meta descriptions."""
        issues = []

        desc_urls: dict[str, list[str]] = {}
        for page in pages:
            if page.meta_description:
                desc = page.meta_description.strip().lower()
                if desc not in desc_urls:
                    desc_urls[desc] = []
                desc_urls[desc].append(page.url)

        for desc, urls in desc_urls.items():
            if len(urls) > 1:
                issues.append(
                    Issue(
                        issue_type="duplicate_meta_description",
                        severity="info",
                        urls=urls[:5],
                        description=f"Duplicate meta description on {len(urls)} pages",
                        recommendation="Create unique meta descriptions for each page",
                    )
                )

        return issues

    def generate_recommendations(self, issues: list[Issue], total_pages: int) -> list[str]:
        """Generate recommendations based on content issues."""
        recommendations = []

        issue_counts = Counter(i.issue_type for i in issues)

        if issue_counts.get("empty_listing", 0) > 0:
            count = issue_counts["empty_listing"]
            recommendations.append(f"Remove {count} empty listing pages from the sitemap")

        if issue_counts.get("thin_content", 0) > total_pages * 0.2:
            recommendations.append("Over 20% of pages have thin content - review content strategy")

        if issue_counts.get("missing_meta_description", 0) > 0:
            count = issue_counts["missing_meta_description"]
            recommendations.append(f"Add meta descriptions to {count} pages")

        if issue_counts.get("duplicate_title", 0) > 0:
            recommendations.append("Implement dynamic titles based on each page's content")

        if not issues:
            recommendations.append("Content validated - no major issues detected")

        return recommendations
