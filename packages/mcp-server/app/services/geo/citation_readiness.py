"""Citation readiness checker for GEO analysis.

Scores how *citation-worthy* a page is for answer engines, based on the signals the
Princeton/IIT-Delhi GEO study found to lift AI citations: statistic density, an
answer-first opening block, self-contained quotable sentences, outbound cited sources,
and freshness. Deterministic; score 0-100.

Distinct from AIReadabilityChecker: that grades *parseability* (sentence/paragraph
structure, generic factual density). This grades *quotability* — whether an engine can
lift a standalone, sourced, current claim from the page.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.core.scoring import CITATION_SUB_WEIGHTS

logger = logging.getLogger(__name__)


class CitationReadinessChecker:
    """Grade a page's citation-worthiness for AI answer engines."""

    STAT_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|x|×)\b|\b\d{2,}(?:[.,]\d+)?\b")
    SOURCE_PATTERN = re.compile(
        r"according to|cited? (?:by|in)|source:|reference|study (?:found|shows|by)|"
        r"research (?:by|from|shows)|\bet al\.?\b|\[\d+\]",
        re.IGNORECASE,
    )
    DEFINITION_PATTERN = re.compile(
        r"\b\w[\w\s]{0,40}?\s+(?:is|are|refers?\s+to|means?)\s+(?:a|an|the|when|the\s+practice)",
        re.IGNORECASE,
    )
    DANGLING_PATTERN = re.compile(
        r"\b(?:as (?:above|mentioned|noted|shown|discussed)|this means|that is why|"
        r"these|those|it (?:is|was|does)|they (?:are|were)|he |she )",
        re.IGNORECASE,
    )

    def check(self, html_content: str, url: str = "") -> dict:
        """Analyze HTML for citation readiness.

        Returns:
            dict with score (0-100), details (dict with sub-scores), issues (list[str])
        """
        if not html_content or not html_content.strip():
            return {
                "score": 0,
                "details": {},
                "issues": ["No content to analyze for citation readiness"],
            }

        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        if not text or len(text.split()) < 30:
            return {
                "score": 0,
                "details": {},
                "issues": ["Content too short for citation analysis"],
            }

        stat_score, stat_details = self._check_stat_density(text)
        answer_score, answer_details = self._check_answer_first(soup, text)
        quote_score, quote_details = self._check_quotable_sentences(text)
        source_score, source_details = self._check_cited_sources(soup, text, url)
        fresh_score, fresh_details = self._check_freshness(text)

        overall = int(
            stat_score * CITATION_SUB_WEIGHTS["stat_density"]
            + answer_score * CITATION_SUB_WEIGHTS["answer_first"]
            + quote_score * CITATION_SUB_WEIGHTS["quotable_sentences"]
            + source_score * CITATION_SUB_WEIGHTS["cited_sources"]
            + fresh_score * CITATION_SUB_WEIGHTS["freshness"]
        )
        overall = max(0, min(100, overall))

        details = {
            "stat_density": {"score": stat_score, **stat_details},
            "answer_first": {"score": answer_score, **answer_details},
            "quotable_sentences": {"score": quote_score, **quote_details},
            "cited_sources": {"score": source_score, **source_details},
            "freshness": {"score": fresh_score, **fresh_details},
        }
        return {"score": overall, "details": details, "issues": self._collect_issues(details)}

    def _check_stat_density(self, text: str) -> tuple[int, dict]:
        """~1 cited statistic per 150-200 words is the GEO-study sweet spot."""
        words = max(1, len(text.split()))
        stats = len(self.STAT_PATTERN.findall(text))
        per_175 = stats / (words / 175)
        if per_175 >= 1:
            score = 100
        elif per_175 >= 0.5:
            score = 70
        elif per_175 > 0:
            score = 40
        else:
            score = 10
        return score, {
            "stats_found": stats,
            "words": words,
            "stats_per_175_words": round(per_175, 2),
        }

    def _check_answer_first(self, soup: BeautifulSoup, text: str) -> tuple[int, dict]:
        """First ~150 words should open with a direct, extractable answer/definition."""
        main = soup.find("main") or soup.find("article") or soup.find("body") or soup
        first_p = main.find("p") if main else None
        opening = first_p.get_text(strip=True) if first_p else " ".join(text.split()[:150])
        opening_words = len(opening.split())
        has_definition = bool(self.DEFINITION_PATTERN.search(opening))
        is_concise = 15 <= opening_words <= 80
        has_stat = bool(self.STAT_PATTERN.search(opening))
        score = 0
        if has_definition:
            score += 55
        if is_concise:
            score += 25
        if has_stat:
            score += 20
        return min(100, score), {
            "opening_words": opening_words,
            "has_definition": has_definition,
            "is_concise": is_concise,
            "has_stat": has_stat,
        }

    def _check_quotable_sentences(self, text: str) -> tuple[int, dict]:
        """Self-contained 8-30 word sentences with no dangling references are quotable."""
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        quotable = 0
        for s in sentences:
            wc = len(s.split())
            if 8 <= wc <= 30 and not self.DANGLING_PATTERN.search(s[:25]):
                quotable += 1
        ratio = quotable / len(sentences) if sentences else 0
        if quotable >= 5 and ratio >= 0.3:
            score = 100
        elif quotable >= 3:
            score = 70
        elif quotable >= 1:
            score = 45
        else:
            score = 10
        return score, {
            "quotable_count": quotable,
            "total_sentences": len(sentences),
            "ratio": round(ratio, 2),
        }

    def _check_cited_sources(self, soup: BeautifulSoup, text: str, url: str) -> tuple[int, dict]:
        """Outbound links to external domains + textual citation cues."""
        page_host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0].lower() if url else ""
        outbound = 0
        for a in soup.find_all("a", href=True):
            raw_href = a["href"]
            href = raw_href if isinstance(raw_href, str) else ""
            m = re.match(r"^https?://([^/]+)/?", href)
            if m and page_host not in m.group(1).lower():
                outbound += 1
        cues = len(self.SOURCE_PATTERN.findall(text))
        score = min(100, outbound * 20 + cues * 15)
        return score, {"outbound_links": outbound, "citation_cues": cues}

    def _check_freshness(self, text: str) -> tuple[int, dict]:
        """Recent year mentions or explicit update markers."""
        year = datetime.now().year
        recent_years = re.findall(rf"\b(?:{year}|{year - 1})\b", text)
        markers = re.findall(
            r"updated?\s+on|last\s+(?:updated|modified|reviewed)|published\s+on",
            text,
            re.IGNORECASE,
        )
        signals = len(recent_years) + len(markers)
        if signals >= 2:
            score = 100
        elif signals == 1:
            score = 60
        else:
            score = 15
        return score, {"recent_year_mentions": len(recent_years), "update_markers": len(markers)}

    def _collect_issues(self, details: dict) -> list[str]:
        issues = []
        if details["stat_density"]["score"] < 50:
            issues.append(
                "Low statistic density. Add ~1 cited stat per 150-200 words to lift AI citations."
            )
        if details["answer_first"]["score"] < 50:
            issues.append(
                "No answer-first opening. Lead with a concise, self-contained definition in the first paragraph."
            )
        if details["quotable_sentences"]["score"] < 50:
            issues.append(
                "Few quotable sentences. Write standalone 8-30 word claims without 'as above'/dangling references."
            )
        if details["cited_sources"]["score"] < 50:
            issues.append(
                "Weak sourcing. Link to authoritative external sources and use citation cues ('according to')."
            )
        if details["freshness"]["score"] < 50:
            issues.append(
                "No freshness signal. Add a visible publish/update date and reference the current year."
            )
        return issues
