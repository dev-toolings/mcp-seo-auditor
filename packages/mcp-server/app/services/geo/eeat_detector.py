"""E-E-A-T signal detector for GEO analysis.

Detects Experience, Expertise, Authority, and Trust signals in page content.
Score 0-100, weight 25%.
"""

import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.core.scoring import AUTHORITATIVE_DOMAINS, EEAT_EXPERIENCE_THRESHOLDS, EEAT_MAX_POINTS

logger = logging.getLogger(__name__)


def _attr_str(value: object) -> str:
    """Coerce a BeautifulSoup attribute value to str.

    Single-valued attrs (href, content) are ``str`` at runtime; the typed
    ``AttributeValueList``/``None`` cases are impossible here and map to "".
    """
    return value if isinstance(value, str) else ""


class EEATDetector:
    """Detect E-E-A-T signals in HTML content."""

    def check(self, html_content: str, url: str = "") -> dict:
        """Analyze page content for E-E-A-T signals.

        Args:
            html_content: Raw HTML of the page
            url: Page URL (used for trust signals like HTTPS)

        Returns:
            dict with score (0-100), details (dict with sub-scores), issues (list[str])
        """
        if not html_content or not html_content.strip():
            return {
                "score": 0,
                "details": {},
                "issues": ["No content to analyze for E-E-A-T signals"],
            }

        soup = BeautifulSoup(html_content, "html.parser")
        text = soup.get_text(separator=" ", strip=True)

        if len(text) < 50:
            return {
                "score": 0,
                "details": {},
                "issues": ["Content too short for E-E-A-T analysis"],
            }

        # Sub-scores (each with defined max points)
        author_score, author_details = self._check_author_info(soup)  # max 20
        date_score, date_details = self._check_publication_date(soup)  # max 10
        citation_score, citation_details = self._check_external_citations(soup)  # max 15
        contact_score, contact_details = self._check_contact_about(soup)  # max 10
        social_score, social_details = self._check_social_proof(soup, text)  # max 10
        research_score, research_details = self._check_original_research(soup, text)  # max 15
        trust_score, trust_details = self._check_trust_signals(soup, url)  # max 10
        experience_score, experience_details = self._check_experience_markers(text)  # max 10

        total = (
            author_score
            + date_score
            + citation_score
            + contact_score
            + social_score
            + research_score
            + trust_score
            + experience_score
        )
        total = max(0, min(100, total))

        details = {
            "author_info": {"score": author_score, "max": 20, **author_details},
            "publication_date": {"score": date_score, "max": 10, **date_details},
            "external_citations": {"score": citation_score, "max": 15, **citation_details},
            "contact_about": {"score": contact_score, "max": 10, **contact_details},
            "social_proof": {"score": social_score, "max": 10, **social_details},
            "original_research": {"score": research_score, "max": 15, **research_details},
            "trust_signals": {"score": trust_score, "max": 10, **trust_details},
            "experience_markers": {"score": experience_score, "max": 10, **experience_details},
        }

        issues = self._collect_issues(details)

        return {"score": total, "details": details, "issues": issues}

    def _check_author_info(self, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for author bio, credentials, and links. Max 20 points."""
        score = 0
        found = []

        # Look for author-related elements
        author_selectors = [
            "[class*='author']",
            "[rel='author']",
            "[itemprop='author']",
            ".byline",
            ".writer",
        ]
        for selector in author_selectors:
            elements = soup.select(selector)
            if elements:
                found.append(f"author element ({selector})")
                score += 8
                break

        # Check for author bio/description
        bio_patterns = [
            "[class*='bio']",
            "[class*='about-author']",
            "[class*='author-desc']",
            "[class*='author-info']",
        ]
        for selector in bio_patterns:
            elements = soup.select(selector)
            if elements:
                found.append("author bio section")
                score += 7
                break

        # Check for author links (LinkedIn, Twitter, etc.)
        author_links = soup.find_all(
            "a",
            href=re.compile(
                r"linkedin\.com|twitter\.com|x\.com|github\.com|orcid\.org", re.IGNORECASE
            ),
        )
        if author_links:
            found.append(f"{len(author_links)} author social links")
            score += 5

        return min(EEAT_MAX_POINTS["author_info"], score), {"signals": found}

    def _check_publication_date(self, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for publication/modification dates. Max 10 points."""
        score = 0
        found = []

        # Check meta tags
        date_metas = [
            "article:published_time",
            "article:modified_time",
            "datePublished",
            "dateModified",
            "date",
            "DC.date",
        ]
        for name in date_metas:
            meta = soup.find("meta", attrs={"property": name}) or soup.find(
                "meta", attrs={"name": name}
            )
            if meta and meta.get("content"):
                found.append(f"meta {name}")
                score += 5
                break

        # Check time elements
        time_elements = soup.find_all("time")
        if time_elements:
            for t in time_elements:
                if t.get("datetime"):
                    found.append("time element with datetime")
                    score += 5
                    break

        # Check for visible date patterns in content
        date_selectors = [
            "[class*='date']",
            "[class*='published']",
            "[class*='modified']",
            "[itemprop='datePublished']",
            "[itemprop='dateModified']",
        ]
        for selector in date_selectors:
            elements = soup.select(selector)
            if elements:
                found.append(f"visible date ({selector})")
                score += 3
                break

        return min(EEAT_MAX_POINTS["publication_date"], score), {"signals": found}

    def _check_external_citations(self, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for links to authoritative external sources. Max 15 points."""
        external_links = soup.find_all("a", href=re.compile(r"^https?://"))
        authoritative_count = 0
        external_count = 0

        for link in external_links:
            href = _attr_str(link.get("href", ""))
            try:
                parsed = urlparse(href)
                domain = parsed.netloc.lower()
            except Exception:
                continue

            external_count += 1

            for auth_domain in AUTHORITATIVE_DOMAINS:
                if domain.endswith(auth_domain):
                    authoritative_count += 1
                    break

        score = 0
        if authoritative_count >= 3:
            score = 15
        elif authoritative_count >= 2:
            score = 12
        elif authoritative_count >= 1:
            score = 8
        elif external_count >= 5:
            score = 5
        elif external_count >= 1:
            score = 3

        return score, {
            "external_links": external_count,
            "authoritative_links": authoritative_count,
        }

    # i18n patterns for trust page detection
    ABOUT_PATTERNS = ["about", "a-propos", "qui-sommes-nous", "notre-equipe", "equipe"]
    CONTACT_PATTERNS = ["contact", "nous-contacter", "contactez"]

    def _check_contact_about(self, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for contact/about page links. Max 10 points."""
        score = 0
        found = []

        links = soup.find_all("a", href=True)

        for link in links:
            href = _attr_str(link.get("href", "")).lower()
            text = link.get_text(strip=True).lower()
            if any(p in href or p in text for p in self.ABOUT_PATTERNS):
                found.append("about page link")
                score += 5
                break

        for link in links:
            href = _attr_str(link.get("href", "")).lower()
            text = link.get_text(strip=True).lower()
            if any(p in href or p in text for p in self.CONTACT_PATTERNS):
                found.append("contact page link")
                score += 5
                break

        return min(EEAT_MAX_POINTS["contact_about"], score), {"signals": found}

    def _check_social_proof(self, soup: BeautifulSoup, text: str) -> tuple[int, dict]:
        """Check for reviews, testimonials, ratings. Max 10 points."""
        score = 0
        found = []

        # Check for review/testimonial sections
        review_selectors = [
            "[class*='review']",
            "[class*='testimonial']",
            "[class*='rating']",
            "[itemprop='review']",
            "[itemprop='aggregateRating']",
        ]
        for selector in review_selectors:
            elements = soup.select(selector)
            if elements:
                found.append(f"review/testimonial section ({selector})")
                score += 5
                break

        # Check for star ratings or rating patterns
        rating_patterns = [
            r"\d+(?:\.\d+)?\s*(?:/\s*5|out\s+of\s+5|stars?)",
            r"\d+\s*reviews?",
            r"rated?\s+\d",
        ]
        for pattern in rating_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append("rating/review mentions in text")
                score += 5
                break

        return min(EEAT_MAX_POINTS["social_proof"], score), {"signals": found}

    def _check_original_research(self, soup: BeautifulSoup, text: str) -> tuple[int, dict]:
        """Check for original research: data tables, statistics, charts. Max 15 points."""
        score = 0
        found = []

        # Data tables
        tables = soup.find_all("table")
        data_tables = [t for t in tables if len(t.find_all("tr")) >= 3]
        if data_tables:
            found.append(f"{len(data_tables)} data tables")
            score += 5

        # Charts/graphs (canvas, svg, chart-related classes)
        chart_selectors = [
            "canvas",
            "[class*='chart']",
            "[class*='graph']",
            "svg[class*='chart']",
        ]
        for selector in chart_selectors:
            elements = soup.select(selector)
            if elements:
                found.append("charts/graphs detected")
                score += 5
                break

        # Original statistics patterns (EN + FR)
        stat_patterns = [
            # English
            r"our\s+(?:data|research|survey|study)\s+(?:shows?|found|indicates?|reveals?)",
            r"we\s+(?:found|discovered|observed|measured|tested|surveyed|analyzed)",
            r"(?:based\s+on|according\s+to)\s+our\s+(?:analysis|research|findings)",
            r"\d+%?\s+of\s+(?:our|the)\s+(?:respondents|users|customers|participants)",
            # French
            r"(?:notre|nos)\s+(?:données|recherches?|enquête|étude)\s+(?:montrent?|révèlent?|indiquent?)",
            r"nous\s+avons\s+(?:découvert|observé|mesuré|analysé|constaté)",
            r"(?:d'après|selon)\s+(?:notre|nos)\s+(?:analyse|recherche|résultats)",
            r"\d+%?\s+(?:de\s+nos|des)\s+(?:répondants|utilisateurs|clients|participants)",
        ]
        for pattern in stat_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                found.append("original research language")
                score += 5
                break

        return min(EEAT_MAX_POINTS["original_research"], score), {"signals": found}

    # i18n patterns for privacy and terms detection
    PRIVACY_KEYWORDS = [
        "privacy",
        "confidentialite",
        "politique-de-confidentialite",
        "donnees-personnelles",
        "rgpd",
        "gdpr",
    ]
    TERMS_KEYWORDS = [
        "terms",
        "conditions",
        "cgv",
        "cgu",
        "mentions-legales",
        "legal",
        "tos",
    ]

    def _check_trust_signals(self, soup: BeautifulSoup, url: str) -> tuple[int, dict]:
        """Check HTTPS, privacy policy, terms of service. Max 10 points."""
        score = 0
        found = []

        # HTTPS check
        if url.startswith("https://"):
            found.append("HTTPS")
            score += 4

        # Privacy policy and terms links
        links = soup.find_all("a", href=True)
        for link in links:
            href = _attr_str(link.get("href", "")).lower()
            text = link.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in self.PRIVACY_KEYWORDS):
                found.append("privacy policy link")
                score += 3
                break

        for link in links:
            href = _attr_str(link.get("href", "")).lower()
            text = link.get_text(strip=True).lower()
            if any(kw in href or kw in text for kw in self.TERMS_KEYWORDS):
                found.append("terms of service link")
                score += 3
                break

        return min(EEAT_MAX_POINTS["trust_signals"], score), {"signals": found}

    def _check_experience_markers(self, text: str) -> tuple[int, dict]:
        """Check for first-person experience narratives. Max 10 points."""
        score = 0
        found = []

        experience_patterns = [
            # English
            r"(?:in\s+my|our)\s+experience",
            r"(?:we|I)\s+(?:have\s+)?(?:been|worked|spent)\s+\d+\s+years?",
            r"case\s+study",
            r"we\s+tested",
            r"(?:our|my)\s+(?:team|company|organization)\s+(?:has|have)",
            r"hands-on\s+(?:experience|testing|work)",
            r"real-world\s+(?:example|scenario|case|application)",
            # French
            r"(?:dans|d'après)\s+(?:mon|notre)\s+expérience",
            r"(?:nous|j'ai)\s+(?:testé|travaillé|passé)\s+\d+\s+ans?",
            r"étude\s+de\s+cas",
            r"nous\s+avons\s+testé",
            r"(?:notre|mon)\s+(?:équipe|entreprise|société)\s+(?:a|ont)",
            r"(?:retour|expérience)\s+(?:terrain|concret|pratique)",
            r"(?:exemple|cas)\s+(?:réel|concret|pratique)",
        ]

        for pattern in experience_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found.append(matches[0])

        for min_count, points in EEAT_EXPERIENCE_THRESHOLDS:
            if len(found) >= min_count:
                score = points
                break

        return score, {"signals": found[:5], "signal_count": len(found)}

    def _collect_issues(self, details: dict) -> list[str]:
        """Collect E-E-A-T issues from sub-scores."""
        issues = []

        if details["author_info"]["score"] < 10:
            issues.append(
                "Author information is weak or missing. Add author bio, "
                "credentials, and social links."
            )

        if details["publication_date"]["score"] < 5:
            issues.append(
                "No publication or modification date found. Add dates to signal content freshness."
            )

        if details["external_citations"]["score"] < 8:
            issues.append(
                "Few or no authoritative external citations. "
                "Link to .gov, .edu, or major publications to build trust."
            )

        if details["contact_about"]["score"] < 5:
            issues.append(
                "Missing contact or about page links. Add links to demonstrate transparency."
            )

        if details["original_research"]["score"] < 5:
            issues.append(
                "No original research signals detected. "
                "Add data tables, unique statistics, or original findings."
            )

        if details["trust_signals"]["score"] < 5:
            issues.append(
                "Weak trust signals. Ensure HTTPS, privacy policy, "
                "and terms of service are present."
            )

        if details["experience_markers"]["score"] < 4:
            issues.append(
                "No first-person experience markers. Add case studies, "
                "hands-on testing references, or personal narratives."
            )

        return issues
