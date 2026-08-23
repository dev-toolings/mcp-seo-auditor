"""AI Readability checker for GEO analysis.

Evaluates how well content can be consumed and cited by AI engines.
Score 0-100, weight 30%.
"""

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.core.scoring import (
    READABILITY_IDEAL_SENTENCE_MAX,
    READABILITY_IDEAL_SENTENCE_MIN,
    READABILITY_SUB_WEIGHTS,
)

logger = logging.getLogger(__name__)


class AIReadabilityChecker:
    """Check how easily AI engines can parse, understand, and cite content."""

    # Direct answer patterns
    DEFINITION_PATTERNS = [
        r"\b\w+\s+is\s+(?:a|an|the)\s+",
        r"\b\w+\s+are\s+",
        r"\b\w+\s+refers?\s+to\s+",
        r"\b\w+\s+means?\s+",
    ]

    FRESHNESS_PATTERNS = [
        r"updated?\s+on",
        r"last\s+(?:modified|updated|reviewed)",
        r"published\s+on",
        r"as\s+of\s+\d{4}",
        rf"\b(?:{'|'.join(str(y) for y in range(datetime.now().year - 2, datetime.now().year + 1))})\b",
    ]

    EXPERTISE_PATTERNS = [
        r"based\s+on\s+our\s+(?:experience|research|data|analysis)",
        r"our\s+(?:data|research|findings|analysis)\s+show",
        r"according\s+to",
        r"(?:study|studies|research)\s+(?:show|suggest|indicate|found)",
        r"original\s+(?:research|data|findings)",
        r"we\s+(?:tested|measured|analyzed|found|observed)",
    ]

    def check(self, html_content: str, url: str = "") -> dict:
        """Analyze HTML content for AI readability.

        Returns:
            dict with score (0-100), details (dict with sub-scores), issues (list[str])
        """
        if not html_content or not html_content.strip():
            return {
                "score": 0,
                "details": {},
                "issues": ["No content to analyze"],
            }

        soup = BeautifulSoup(html_content, "html.parser")

        # Remove script, style, nav, footer elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        if not text or len(text) < 50:
            return {
                "score": 0,
                "details": {},
                "issues": ["Content too short for meaningful analysis"],
            }

        # Calculate sub-scores
        sentence_score, sentence_details = self._check_sentence_structure(text, soup)
        factual_score, factual_details = self._check_factual_density(text)
        answer_score, answer_details = self._check_direct_answers(text, soup)
        freshness_score, freshness_details = self._check_freshness(text)
        expertise_score, expertise_details = self._check_expertise(text)
        ai_summary_score, ai_summary_details = self._check_ai_summary(soup)

        # Weighted sub-scores + AI summary bonus (up to 15 pts)
        overall = int(
            sentence_score * READABILITY_SUB_WEIGHTS["sentence"]
            + factual_score * READABILITY_SUB_WEIGHTS["factual"]
            + answer_score * READABILITY_SUB_WEIGHTS["answers"]
            + freshness_score * READABILITY_SUB_WEIGHTS["freshness"]
            + expertise_score * READABILITY_SUB_WEIGHTS["expertise"]
            + ai_summary_score
        )
        overall = max(0, min(100, overall))

        details = {
            "sentence_structure": {"score": sentence_score, **sentence_details},
            "factual_density": {"score": factual_score, **factual_details},
            "direct_answers": {"score": answer_score, **answer_details},
            "freshness_signals": {"score": freshness_score, **freshness_details},
            "expertise_signals": {"score": expertise_score, **expertise_details},
            "ai_summary": {"score": ai_summary_score, **ai_summary_details},
        }

        issues = self._collect_issues(details)

        return {"score": overall, "details": details, "issues": issues}

    def _check_sentence_structure(self, text: str, soup: BeautifulSoup) -> tuple[int, dict]:
        """Evaluate sentence and paragraph structure."""
        sentences = re.split(r"[.!?]+\s+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return 0, {"avg_sentence_length": 0, "paragraph_count": 0}

        word_counts = [len(s.split()) for s in sentences]
        avg_length = sum(word_counts) / len(word_counts)

        # Score sentence length: ideal is 15-25 words
        if READABILITY_IDEAL_SENTENCE_MIN <= avg_length <= READABILITY_IDEAL_SENTENCE_MAX:
            length_score = 100
        elif avg_length < READABILITY_IDEAL_SENTENCE_MIN:
            length_score = max(0, int(100 - (READABILITY_IDEAL_SENTENCE_MIN - avg_length) * 8))
        else:
            length_score = max(0, int(100 - (avg_length - READABILITY_IDEAL_SENTENCE_MAX) * 5))

        # Paragraph analysis
        paragraphs = soup.find_all("p")
        paragraph_count = len(paragraphs)
        paragraph_score = min(100, paragraph_count * 10) if paragraph_count > 0 else 0

        # Check paragraph length (ideal: 3-6 sentences)
        para_length_score = 80  # default
        if paragraphs:
            para_lengths = []
            for p in paragraphs:
                p_text = p.get_text(strip=True)
                if p_text:
                    p_sentences = re.split(r"[.!?]+\s+", p_text)
                    para_lengths.append(len([s for s in p_sentences if s.strip()]))
            if para_lengths:
                avg_para = sum(para_lengths) / len(para_lengths)
                if 3 <= avg_para <= 6:
                    para_length_score = 100
                elif avg_para < 3:
                    para_length_score = max(40, int(avg_para / 3 * 100))
                else:
                    para_length_score = max(40, int(100 - (avg_para - 6) * 10))

        score = int(length_score * 0.4 + paragraph_score * 0.3 + para_length_score * 0.3)

        return score, {
            "avg_sentence_length": round(avg_length, 1),
            "sentence_count": len(sentences),
            "paragraph_count": paragraph_count,
        }

    def _check_factual_density(self, text: str) -> tuple[int, dict]:
        """Count factual elements: numbers, dates, proper nouns."""
        # Count numbers and statistics
        numbers = re.findall(r"\b\d+(?:[.,]\d+)?(?:\s*%|\s*percent)?\b", text)
        number_count = len(numbers)

        # Count date patterns
        dates = re.findall(
            r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})\b",
            text,
        )
        date_count = len(dates)

        # Count proper nouns (capitalized words not at sentence start)
        proper_nouns = re.findall(r"(?<=[.!?]\s)[a-z].*?([A-Z][a-z]{2,})", text)
        proper_noun_count = len(proper_nouns)

        # Calculate word count for density
        word_count = len(text.split())
        paragraphs = max(1, word_count // 100)  # approximate paragraphs

        # Factual elements per paragraph
        factual_per_para = (number_count + date_count + proper_noun_count) / paragraphs

        # Score: more factual density = better for AI citation
        if factual_per_para >= 5:
            score = 100
        elif factual_per_para >= 3:
            score = 80
        elif factual_per_para >= 1:
            score = 60
        elif factual_per_para > 0:
            score = 40
        else:
            score = 20

        return score, {
            "numbers_found": number_count,
            "dates_found": date_count,
            "proper_nouns_found": proper_noun_count,
            "factual_density_per_100_words": round(factual_per_para, 2),
        }

    def _check_direct_answers(self, text: str, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for patterns AI engines can directly cite."""
        score = 0
        found_patterns = []

        # Definition patterns (up to 30 pts)
        definition_count = 0
        for pattern in self.DEFINITION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            definition_count += len(matches)
        if definition_count >= 3:
            score += 30
        elif definition_count >= 1:
            score += 15
        if definition_count > 0:
            found_patterns.append(f"{definition_count} definition patterns")

        # Lists: numbered or bullet (up to 25 pts)
        lists = soup.find_all(["ul", "ol"])
        list_count = len(lists)
        if list_count >= 3:
            score += 25
        elif list_count >= 1:
            score += 15
        if list_count > 0:
            found_patterns.append(f"{list_count} lists")

        # Step-by-step instructions (up to 20 pts)
        step_patterns = re.findall(
            r"(?:step\s+\d|first[,.]|second[,.]|third[,.]|finally[,.]|next[,.])",
            text,
            re.IGNORECASE,
        )
        if len(step_patterns) >= 3:
            score += 20
        elif len(step_patterns) >= 1:
            score += 10
        if step_patterns:
            found_patterns.append(f"{len(step_patterns)} step-by-step markers")

        # Headings with question words (up to 25 pts)
        headings = soup.find_all(["h1", "h2", "h3", "h4"])
        question_headings = 0
        for h in headings:
            h_text = h.get_text(strip=True)
            if re.match(r"(?:how|what|why|when|where|can|does|is|are|do)\b", h_text, re.IGNORECASE):
                question_headings += 1
        if question_headings >= 3:
            score += 25
        elif question_headings >= 1:
            score += 12
        if question_headings > 0:
            found_patterns.append(f"{question_headings} question headings")

        return min(100, score), {
            "patterns_found": found_patterns,
            "definition_count": definition_count,
            "list_count": list_count,
            "question_headings": question_headings,
        }

    def _check_freshness(self, text: str) -> tuple[int, dict]:
        """Detect freshness signals in content."""
        signals_found = []

        for pattern in self.FRESHNESS_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                signals_found.extend(matches[:2])  # limit per pattern

        # Score based on freshness signals
        if len(signals_found) >= 3:
            score = 100
        elif len(signals_found) >= 2:
            score = 80
        elif len(signals_found) >= 1:
            score = 50
        else:
            score = 20

        return score, {
            "signals_found": signals_found[:5],
            "signal_count": len(signals_found),
        }

    def _check_expertise(self, text: str) -> tuple[int, dict]:
        """Detect expertise and authority signals."""
        signals_found = []

        for pattern in self.EXPERTISE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                signals_found.extend(matches[:2])

        if len(signals_found) >= 4:
            score = 100
        elif len(signals_found) >= 2:
            score = 70
        elif len(signals_found) >= 1:
            score = 40
        else:
            score = 15

        return score, {
            "signals_found": signals_found[:5],
            "signal_count": len(signals_found),
        }

    def _check_ai_summary(self, soup: BeautifulSoup) -> tuple[int, dict]:
        """Check for an AI-ready summary (concise 2-sentence intro at top of page).

        Looks for the first <p> tag in main content and checks:
        - Word count in 20-60 range (concise summary)
        - Contains a definition pattern ("X is...", "X est...")

        Returns up to 15 bonus points.
        """
        # Find main content area, fall back to body
        main = soup.find("main") or soup.find("article") or soup.find("body")
        if not main:
            return 0, {"has_summary": False, "reason": "no content area found"}

        first_p = main.find("p")
        if not first_p:
            return 0, {"has_summary": False, "reason": "no paragraph found"}

        p_text = first_p.get_text(strip=True)
        if not p_text:
            return 0, {"has_summary": False, "reason": "first paragraph empty"}

        word_count = len(p_text.split())
        score = 0
        is_concise = 20 <= word_count <= 60

        # Check for definition pattern (EN: "X is...", FR: "X est...")
        has_definition = bool(
            re.search(r"\b\w+\s+(?:is|are|est|sont|refers?\s+to|means?)\s+", p_text, re.IGNORECASE)
        )

        if is_concise and has_definition:
            score = 15
        elif is_concise:
            score = 10
        elif has_definition:
            score = 5

        return score, {
            "has_summary": score > 0,
            "first_paragraph_words": word_count,
            "is_concise": is_concise,
            "has_definition": has_definition,
        }

    def _collect_issues(self, details: dict) -> list[str]:
        """Collect issues from sub-score analysis."""
        issues = []

        # Sentence structure
        ss = details.get("sentence_structure", {})
        if ss.get("score", 0) < 50:
            avg = ss.get("avg_sentence_length", 0)
            if avg < READABILITY_IDEAL_SENTENCE_MIN:
                issues.append(
                    f"Sentences too short (avg {avg} words). "
                    f"Aim for {READABILITY_IDEAL_SENTENCE_MIN}-{READABILITY_IDEAL_SENTENCE_MAX} words."
                )
            elif avg > READABILITY_IDEAL_SENTENCE_MAX:
                issues.append(
                    f"Sentences too long (avg {avg} words). "
                    f"Aim for {READABILITY_IDEAL_SENTENCE_MIN}-{READABILITY_IDEAL_SENTENCE_MAX} words."
                )
        if ss.get("paragraph_count", 0) < 3:
            issues.append("Too few paragraphs. Break content into more digestible sections.")

        # Factual density
        fd = details.get("factual_density", {})
        if fd.get("score", 0) < 50:
            issues.append(
                "Low factual density. Add specific numbers, dates, and data points "
                "to make content more citable by AI."
            )

        # Direct answers
        da = details.get("direct_answers", {})
        if da.get("score", 0) < 50:
            issues.append(
                "Few direct answer patterns. Add definitions ('X is...'), "
                "lists, and question-based headings for AI citation."
            )

        # Freshness
        fr = details.get("freshness_signals", {})
        if fr.get("score", 0) < 50:
            issues.append(
                "No freshness signals detected. Add publication/update dates "
                "to signal content currency."
            )

        # Expertise
        ex = details.get("expertise_signals", {})
        if ex.get("score", 0) < 50:
            issues.append(
                "Weak expertise signals. Reference original research, data, "
                "or experience to strengthen authority."
            )

        # AI summary
        ai_sum = details.get("ai_summary", {})
        if ai_sum.get("score", 0) == 0:
            issues.append(
                "No AI-ready summary found. Start with a concise 20-60 word intro paragraph "
                "containing a clear definition ('X is...') for better AI citation."
            )

        return issues
