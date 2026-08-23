"""E-E-A-T deep audit service.

Extends the existing EEATDetector with cross-page analysis,
author page detection, schema validation, and optional LLM enrichment.
"""

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.models.eeat_models import EEATDimension, EEATPageResult, EEATReport
from app.services.geo.eeat_detector import EEATDetector
from app.services.llm.base_provider import BaseLLMProvider
from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_SEO_ANALYST,
    build_eeat_audit_prompt,
)

logger = logging.getLogger(__name__)

# Patterns for author page detection
AUTHOR_PAGE_PATTERNS = [
    r"/about/?$",
    r"/team/?$",
    r"/author/",
    r"/authors/?$",
    r"/equipe/?$",
    r"/a-propos/?$",
    r"/qui-sommes-nous/?$",
    r"/who-we-are/?$",
]

# Patterns for trust/legal pages detection
TRUST_PAGE_PATTERNS = [
    r"/privacy/?$",
    r"/confidentialite/?$",
    r"/politique-de-confidentialite/?$",
    r"/cgv/?$",
    r"/cgu/?$",
    r"/terms/?$",
    r"/conditions/?$",
    r"/mentions-legales/?$",
    r"/legal/?$",
    r"/contact/?$",
    r"/nous-contacter/?$",
]


class EEATAuditService:
    """Deep E-E-A-T audit across multiple pages."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.detector = EEATDetector()
        self.llm = llm_provider

    async def audit(
        self,
        pages: list[dict],
        sitemap_urls: list[str] | None = None,
    ) -> EEATReport:
        """Run deep E-E-A-T audit on crawled pages.

        Args:
            pages: List of dicts with keys: url, html_content, structured_data
            sitemap_urls: All URLs from sitemap (for author page detection)

        Returns:
            EEATReport with per-page and cross-page analysis
        """
        page_results: list[EEATPageResult] = []
        all_authors: dict[str, list[str]] = {}  # author_name -> [urls]

        # Detect author and trust pages in sitemap
        author_pages_in_sitemap = self._find_author_pages(sitemap_urls or [])
        trust_pages_in_sitemap = self._find_trust_pages(sitemap_urls or [])

        for page in pages:
            url = page.get("url", "")
            html = page.get("html_content", "")
            structured_data = page.get("structured_data", [])

            try:
                result = self._analyze_page(url, html, structured_data, author_pages_in_sitemap)
                page_results.append(result)

                # Track authors for consistency check
                authors = self._extract_authors(html)
                for author in authors:
                    all_authors.setdefault(author, []).append(url)

            except Exception as e:
                logger.error("E-E-A-T analysis failed for %s: %s", url, e)
                page_results.append(
                    EEATPageResult(
                        url=url,
                        eeat_score=0,
                        experience=EEATDimension(name="experience", score=0),
                        expertise=EEATDimension(name="expertise", score=0),
                        authoritativeness=EEATDimension(name="authoritativeness", score=0),
                        trustworthiness=EEATDimension(name="trustworthiness", score=0),
                        issues=[f"Analysis failed: {e}"],
                    )
                )

        # Cross-page analysis
        cross_consistency = self._check_cross_page_consistency(all_authors, page_results)
        author_coverage = self._compute_author_coverage(
            page_results, author_pages_in_sitemap, trust_pages_in_sitemap
        )

        # Aggregate scores
        report = self._build_report(page_results, cross_consistency, author_coverage)

        # Optional LLM enrichment
        if self.llm and self.llm.is_available():
            try:
                report = await self._enrich_with_llm(report)
            except Exception as e:
                logger.warning("LLM enrichment for E-E-A-T failed: %s", e)

        return report

    def _analyze_page(
        self,
        url: str,
        html: str,
        structured_data: list[dict],
        author_pages: list[str],
    ) -> EEATPageResult:
        """Analyze a single page for E-E-A-T signals."""
        # Use existing detector for base scores
        base_result = self.detector.check(html, url)
        details = base_result.get("details", {})

        soup = BeautifulSoup(html, "html.parser") if html else None

        # Map detector sub-scores to E-E-A-T dimensions
        experience = self._build_experience_dimension(details)
        expertise = self._build_expertise_dimension(details, structured_data)
        authoritativeness = self._build_authoritativeness_dimension(details, structured_data)
        trustworthiness = self._build_trustworthiness_dimension(details)

        # Check for author page link
        has_author_page = self._has_author_page_link(soup, author_pages)

        # Check for Organization/Person schema
        has_org_schema = self._has_schema_type(structured_data, "Organization")
        has_person_schema = self._has_schema_type(structured_data, "Person")

        # Weighted overall score
        eeat_score = int(
            experience.score * 0.20
            + expertise.score * 0.30
            + authoritativeness.score * 0.25
            + trustworthiness.score * 0.25
        )
        eeat_score = max(0, min(100, eeat_score))

        # Collect issues
        all_issues = (
            experience.issues + expertise.issues + authoritativeness.issues + trustworthiness.issues
        )

        # Build recommendations
        recommendations = self._page_recommendations(
            experience,
            expertise,
            authoritativeness,
            trustworthiness,
            has_author_page,
            has_org_schema,
            has_person_schema,
        )

        return EEATPageResult(
            url=url,
            eeat_score=eeat_score,
            experience=experience,
            expertise=expertise,
            authoritativeness=authoritativeness,
            trustworthiness=trustworthiness,
            has_author_info=details.get("author_info", {}).get("score", 0) > 0,
            has_author_page=has_author_page,
            has_organization_schema=has_org_schema,
            has_person_schema=has_person_schema,
            issues=all_issues,
            recommendations=recommendations,
        )

    def _build_experience_dimension(self, details: dict) -> EEATDimension:
        """Build Experience dimension from detector details."""
        exp_markers = details.get("experience_markers", {})
        original_research = details.get("original_research", {})

        score = 0
        signals = []
        issues = []

        # Experience markers (max 10 in detector, scale to 50)
        exp_score = exp_markers.get("score", 0)
        score += int(exp_score * 5)  # 10 -> 50
        signals.extend(exp_markers.get("signals", []))

        # Original research (max 15 in detector, scale to 50)
        res_score = original_research.get("score", 0)
        score += int(res_score * 50 / 15)
        signals.extend(original_research.get("signals", []))

        score = max(0, min(100, score))

        if score < 30:
            issues.append(
                "No first-person experience markers. Add case studies, "
                "hands-on testing, or personal narratives."
            )
        if res_score < 5:
            issues.append(
                "No original research detected. Add data tables, statistics, or original findings."
            )

        return EEATDimension(name="experience", score=score, signals=signals[:5], issues=issues)

    def _build_expertise_dimension(
        self, details: dict, structured_data: list[dict]
    ) -> EEATDimension:
        """Build Expertise dimension."""
        author_info = details.get("author_info", {})
        citations = details.get("external_citations", {})

        score = 0
        signals = []
        issues = []

        # Author info (max 20 in detector, scale to 40)
        auth_score = author_info.get("score", 0)
        score += int(auth_score * 2)
        signals.extend(author_info.get("signals", []))

        # Citations (max 15 in detector, scale to 30)
        cit_score = citations.get("score", 0)
        score += int(cit_score * 2)
        auth_links = citations.get("authoritative_links", 0)
        if auth_links > 0:
            signals.append(f"{auth_links} authoritative citations")

        # Person/Organization schema bonus
        has_person = self._has_schema_type(structured_data, "Person")
        has_org = self._has_schema_type(structured_data, "Organization")
        if has_person:
            score += 15
            signals.append("Person schema present")
        if has_org:
            score += 15
            signals.append("Organization schema present")

        score = max(0, min(100, score))

        if auth_score < 10:
            issues.append(
                "Author information is weak. Add detailed author bio "
                "with credentials and professional links."
            )
        if not has_person and not has_org:
            issues.append(
                "Missing Person or Organization schema. Add JSON-LD "
                "to declare author/organization expertise."
            )

        return EEATDimension(name="expertise", score=score, signals=signals[:5], issues=issues)

    def _build_authoritativeness_dimension(
        self, details: dict, structured_data: list[dict]
    ) -> EEATDimension:
        """Build Authoritativeness dimension."""
        citations = details.get("external_citations", {})
        social = details.get("social_proof", {})

        score = 0
        signals = []
        issues = []

        # External citations (max 15, scale to 40)
        cit_score = citations.get("score", 0)
        score += int(cit_score * 40 / 15)
        ext_links = citations.get("external_links", 0)
        auth_links = citations.get("authoritative_links", 0)
        if ext_links > 0:
            signals.append(f"{ext_links} external links, {auth_links} authoritative")

        # Social proof (max 10, scale to 30)
        soc_score = social.get("score", 0)
        score += int(soc_score * 3)
        signals.extend(social.get("signals", []))

        # Organization schema bonus
        has_org = self._has_schema_type(structured_data, "Organization")
        if has_org:
            score += 15
            signals.append("Organization schema validates authority")

        # sameAs links in schema (social profiles)
        for sd in structured_data:
            if isinstance(sd, dict) and sd.get("sameAs"):
                same_as = sd["sameAs"]
                if isinstance(same_as, list) and len(same_as) > 0:
                    score += 15
                    signals.append(f"sameAs links: {len(same_as)} profiles")
                    break

        score = max(0, min(100, score))

        if auth_links < 1:
            issues.append(
                "No authoritative external citations. Link to .gov, .edu, "
                "or recognized sources to build authority."
            )

        return EEATDimension(
            name="authoritativeness",
            score=score,
            signals=signals[:5],
            issues=issues,
        )

    def _build_trustworthiness_dimension(self, details: dict) -> EEATDimension:
        """Build Trustworthiness dimension."""
        trust = details.get("trust_signals", {})
        contact = details.get("contact_about", {})
        pub_date = details.get("publication_date", {})

        score = 0
        signals = []
        issues = []

        # Trust signals (max 10, scale to 35)
        tr_score = trust.get("score", 0)
        score += int(tr_score * 35 / 10)
        signals.extend(trust.get("signals", []))

        # Contact/About (max 10, scale to 35)
        ct_score = contact.get("score", 0)
        score += int(ct_score * 35 / 10)
        signals.extend(contact.get("signals", []))

        # Publication date (max 10, scale to 30)
        dt_score = pub_date.get("score", 0)
        score += int(dt_score * 3)
        signals.extend(pub_date.get("signals", []))

        score = max(0, min(100, score))

        if tr_score < 5:
            issues.append(
                "Weak trust signals. Ensure HTTPS, privacy policy, "
                "and terms of service are present."
            )
        if ct_score < 5:
            issues.append(
                "Missing contact or about page links. Add links to demonstrate transparency."
            )

        return EEATDimension(
            name="trustworthiness",
            score=score,
            signals=signals[:5],
            issues=issues,
        )

    def _find_author_pages(self, urls: list[str]) -> list[str]:
        """Find author/about/team pages in sitemap URLs."""
        author_pages = []
        for url in urls:
            path = urlparse(url).path.lower()
            for pattern in AUTHOR_PAGE_PATTERNS:
                if re.search(pattern, path):
                    author_pages.append(url)
                    break
        return author_pages

    def _find_trust_pages(self, urls: list[str]) -> list[str]:
        """Find trust/legal pages (privacy, CGV, contact, etc.) in sitemap URLs."""
        trust_pages = []
        for url in urls:
            path = urlparse(url).path.lower()
            for pattern in TRUST_PAGE_PATTERNS:
                if re.search(pattern, path):
                    trust_pages.append(url)
                    break
        return trust_pages

    def _has_author_page_link(self, soup: Optional[BeautifulSoup], author_pages: list[str]) -> bool:
        """Check if page links to any detected author page."""
        if not soup:
            return False

        links = soup.find_all("a", href=True)
        for link in links:
            raw_href = link.get("href", "")
            href = raw_href if isinstance(raw_href, str) else ""
            # Check against known author pages
            for ap in author_pages:
                if ap in href or href in ap:
                    return True
            # Check URL patterns
            for pattern in AUTHOR_PAGE_PATTERNS:
                if re.search(pattern, href.lower()):
                    return True
        return False

    def _has_schema_type(self, structured_data: list[dict], schema_type: str) -> bool:
        """Check if any schema block has the given @type."""
        for sd in structured_data:
            if not isinstance(sd, dict):
                continue
            sd_type = sd.get("@type", "")
            if isinstance(sd_type, str) and sd_type.lower() == schema_type.lower():
                return True
            if isinstance(sd_type, list):
                for t in sd_type:
                    if isinstance(t, str) and t.lower() == schema_type.lower():
                        return True
        return False

    def _extract_authors(self, html: str) -> list[str]:
        """Extract author names from HTML."""
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        authors = set()

        # From structured data in page
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json

                data = json.loads(script.string or "")
                if isinstance(data, dict):
                    author = data.get("author", {})
                    if isinstance(author, dict):
                        name = author.get("name", "")
                        if name:
                            authors.add(name.strip().lower())
                    elif isinstance(author, list):
                        for a in author:
                            if isinstance(a, dict):
                                name = a.get("name", "")
                                if name:
                                    authors.add(name.strip().lower())
            except Exception:
                continue

        # From HTML elements
        selectors = [
            "[rel='author']",
            "[itemprop='author']",
            "[class*='author-name']",
            ".byline",
        ]
        for sel in selectors:
            for el in soup.select(sel):
                text = el.get_text(strip=True)
                if text and len(text) < 100:
                    authors.add(text.lower())

        return list(authors)

    def _check_cross_page_consistency(
        self,
        authors: dict[str, list[str]],
        page_results: list[EEATPageResult],
    ) -> dict:
        """Check E-E-A-T consistency across pages."""
        consistency: dict[str, Any] = {
            "unique_authors": len(authors),
            "authors": {
                name: {"pages_count": len(urls), "urls": urls[:3]} for name, urls in authors.items()
            },
            "pages_with_author": sum(1 for r in page_results if r.has_author_info),
            "pages_without_author": sum(1 for r in page_results if not r.has_author_info),
            "issues": [],
        }

        total = len(page_results)
        if total > 0:
            pct_with_author = consistency["pages_with_author"] / total
            if pct_with_author < 0.5:
                consistency["issues"].append(
                    f"Only {int(pct_with_author * 100)}% of pages have author info. "
                    "Add author attribution to all content pages."
                )

        # Check for inconsistent author naming
        if len(authors) > 1:
            # Look for very similar names (possible inconsistency)
            names = list(authors.keys())
            for i, n1 in enumerate(names):
                for n2 in names[i + 1 :]:
                    if n1 in n2 or n2 in n1:
                        consistency["issues"].append(
                            f"Possible inconsistent author naming: "
                            f"'{n1}' vs '{n2}'. Standardize author names."
                        )

        return consistency

    def _compute_author_coverage(
        self,
        page_results: list[EEATPageResult],
        author_pages: list[str],
        trust_pages: list[str] | None = None,
    ) -> dict:
        """Compute author and trust page coverage statistics."""
        result = {
            "author_pages_found": len(author_pages),
            "author_page_urls": author_pages[:5],
            "pages_linking_to_author": sum(1 for r in page_results if r.has_author_page),
            "organization_schema_count": sum(1 for r in page_results if r.has_organization_schema),
            "person_schema_count": sum(1 for r in page_results if r.has_person_schema),
        }
        if trust_pages is not None:
            result["trust_pages_found"] = len(trust_pages)
            result["trust_page_urls"] = trust_pages[:10]
        return result

    def _page_recommendations(
        self,
        experience: EEATDimension,
        expertise: EEATDimension,
        authoritativeness: EEATDimension,
        trustworthiness: EEATDimension,
        has_author_page: bool,
        has_org_schema: bool,
        has_person_schema: bool,
    ) -> list[str]:
        """Generate page-level recommendations."""
        recs = []

        if experience.score < 30:
            recs.append(
                "Add first-hand experience signals: case studies, "
                "testing results, personal narratives."
            )
        if expertise.score < 30:
            recs.append(
                "Strengthen expertise signals: detailed author bio, "
                "credentials, professional links."
            )
        if authoritativeness.score < 30:
            recs.append(
                "Build authority with authoritative citations, "
                "social proof, and recognized source links."
            )
        if trustworthiness.score < 30:
            recs.append(
                "Improve trust: add privacy policy, terms of service, "
                "contact information, and HTTPS."
            )
        if not has_author_page:
            recs.append("Link to a dedicated author/about page to validate expertise.")
        if not has_org_schema and not has_person_schema:
            recs.append(
                "Add Person or Organization JSON-LD schema to declare authorship and expertise."
            )

        return recs[:5]

    def _build_report(
        self,
        page_results: list[EEATPageResult],
        cross_consistency: dict,
        author_coverage: dict,
    ) -> EEATReport:
        """Build aggregated E-E-A-T report."""
        if not page_results:
            return EEATReport(
                eeat_score=0,
                grade="F",
                experience_score=0,
                expertise_score=0,
                authoritativeness_score=0,
                trustworthiness_score=0,
                issues=["No pages analyzed"],
            )

        count = len(page_results)
        exp_avg = int(sum(r.experience.score for r in page_results) / count)
        expt_avg = int(sum(r.expertise.score for r in page_results) / count)
        auth_avg = int(sum(r.authoritativeness.score for r in page_results) / count)
        trust_avg = int(sum(r.trustworthiness.score for r in page_results) / count)
        overall = int(exp_avg * 0.20 + expt_avg * 0.30 + auth_avg * 0.25 + trust_avg * 0.25)
        overall = max(0, min(100, overall))

        grade = self._compute_grade(overall)

        # Aggregate issues
        all_issues = list(cross_consistency.get("issues", []))
        seen = set(all_issues)
        for r in page_results:
            for issue in r.issues:
                if issue not in seen:
                    seen.add(issue)
                    all_issues.append(issue)

        # Aggregate recommendations
        all_recs = []
        seen_recs = set()
        for r in page_results:
            for rec in r.recommendations:
                if rec not in seen_recs:
                    seen_recs.add(rec)
                    all_recs.append(rec)

        return EEATReport(
            eeat_score=overall,
            grade=grade,
            experience_score=exp_avg,
            expertise_score=expt_avg,
            authoritativeness_score=auth_avg,
            trustworthiness_score=trust_avg,
            page_results=page_results,
            cross_page_consistency=cross_consistency,
            author_coverage=author_coverage,
            issues=all_issues[:15],
            recommendations=all_recs[:10],
        )

    async def _enrich_with_llm(self, report: EEATReport) -> EEATReport:
        """Enrich report with LLM-generated recommendations."""
        assert self.llm is not None  # guarded by caller (self.llm.is_available())
        report_data = {
            "eeat_score": report.eeat_score,
            "grade": report.grade,
            "dimensions": {
                "experience": report.experience_score,
                "expertise": report.expertise_score,
                "authoritativeness": report.authoritativeness_score,
                "trustworthiness": report.trustworthiness_score,
            },
            "cross_page_consistency": report.cross_page_consistency,
            "author_coverage": report.author_coverage,
            "issues": report.issues[:10],
            "page_scores": [
                {"url": r.url, "score": r.eeat_score, "issues": r.issues[:3]}
                for r in report.page_results[:5]
            ],
        }

        prompt = build_eeat_audit_prompt(report_data)
        response = await self.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)

        if isinstance(response, dict):
            ai_recs = response.get("recommendations", [])
            enriched_recs = []
            for rec in ai_recs:
                if isinstance(rec, str):
                    enriched_recs.append(rec)
                elif isinstance(rec, dict):
                    text = (
                        rec.get("action")
                        or rec.get("recommendation")
                        or rec.get("description")
                        or str(rec)
                    )
                    enriched_recs.append(text)

            report.recommendations = enriched_recs + report.recommendations
            report.recommendations = report.recommendations[:15]
            report.ai_enhanced = True

        return report

    @staticmethod
    def _compute_grade(score: int) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"
