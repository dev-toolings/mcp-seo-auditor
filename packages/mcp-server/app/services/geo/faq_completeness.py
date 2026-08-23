"""FAQ completeness checker for GEO analysis.

Evaluates FAQ content coverage and schema markup quality.
Score 0-100, weight 20%.
"""

import logging
import re

from bs4 import BeautifulSoup

from app.core.scoring import FAQ_MIN_ANSWER_WORDS, FAQ_SUB_WEIGHTS

logger = logging.getLogger(__name__)

# Question starter patterns
QUESTION_PATTERNS = [
    r"(?:^|\n)\s*(?:how\s+(?:to|do|does|can|much|many|long|often))\b",
    r"(?:^|\n)\s*(?:what\s+(?:is|are|does|do|was|were|should|can))\b",
    r"(?:^|\n)\s*(?:why\s+(?:is|are|does|do|should|would|can))\b",
    r"(?:^|\n)\s*(?:when\s+(?:is|are|does|do|should|can|will))\b",
    r"(?:^|\n)\s*(?:where\s+(?:is|are|does|do|can|should))\b",
    r"(?:^|\n)\s*(?:can\s+(?:I|you|we|they|it))\b",
    r"(?:^|\n)\s*(?:does\s+(?:it|this|the|a|an))\b",
    r"(?:^|\n)\s*(?:is\s+(?:it|this|there|the))\b",
]


class FAQCompletenessChecker:
    """Evaluate FAQ content coverage and markup quality."""

    def check(self, html_content: str, structured_data: list[dict]) -> dict:
        """Analyze FAQ content and markup completeness.

        Args:
            html_content: Raw HTML of the page
            structured_data: List of JSON-LD blocks

        Returns:
            dict with score (0-100), details (dict), issues (list[str])
        """
        if not html_content or not html_content.strip():
            return {
                "score": 0,
                "details": {},
                "issues": ["No content to analyze for FAQ completeness"],
            }

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract questions from content
        content_questions = self._extract_content_questions(soup)

        # Extract FAQ markup from structured data
        faq_markup = self._extract_faq_markup(structured_data)

        # Sub-scores
        pattern_score, pattern_details = self._score_question_patterns(content_questions)
        markup_score, markup_details = self._score_faq_markup(faq_markup)
        correspondence_score, correspondence_details = self._score_markup_correspondence(
            content_questions, faq_markup
        )
        quality_score, quality_details = self._score_answer_quality(faq_markup)
        missing_score, missing_details = self._score_missing_questions(
            content_questions, faq_markup
        )

        # Weighted overall score
        overall = int(
            pattern_score * FAQ_SUB_WEIGHTS["patterns"]
            + markup_score * FAQ_SUB_WEIGHTS["markup"]
            + correspondence_score * FAQ_SUB_WEIGHTS["correspondence"]
            + quality_score * FAQ_SUB_WEIGHTS["quality"]
            + missing_score * FAQ_SUB_WEIGHTS["missing"]
        )
        overall = max(0, min(100, overall))

        details = {
            "content_questions": content_questions[:10],
            "faq_markup_questions": [q["question"] for q in faq_markup][:10],
            "question_patterns": {"score": pattern_score, **pattern_details},
            "faq_markup": {"score": markup_score, **markup_details},
            "markup_correspondence": {"score": correspondence_score, **correspondence_details},
            "answer_quality": {"score": quality_score, **quality_details},
            "missing_in_markup": {"score": missing_score, **missing_details},
        }

        issues = self._collect_issues(details, content_questions, faq_markup)

        return {"score": overall, "details": details, "issues": issues}

    def _extract_content_questions(self, soup: BeautifulSoup) -> list[str]:
        """Extract question-like content from headings and text."""
        questions = []

        # Check headings for question patterns
        headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
        for heading in headings:
            text = heading.get_text(strip=True)
            if text.endswith("?") or self._is_question_pattern(text):
                questions.append(text)

        # Check paragraphs and text for question patterns
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Only consider standalone question sentences
            sentences = re.split(r"[.!]\s+", text)
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence.endswith("?") and len(sentence) > 10:
                    questions.append(sentence)

        # Check dt elements (definition lists often used for FAQs)
        dt_elements = soup.find_all("dt")
        for dt in dt_elements:
            text = dt.get_text(strip=True)
            if text:
                questions.append(text)

        # Deduplicate while preserving order
        seen = set()
        unique_questions = []
        for q in questions:
            q_lower = q.lower().strip()
            if q_lower not in seen:
                seen.add(q_lower)
                unique_questions.append(q)

        return unique_questions

    def _is_question_pattern(self, text: str) -> bool:
        """Check if text matches a question pattern."""
        text_lower = text.lower().strip()
        for pattern in QUESTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False

    def _extract_faq_markup(self, structured_data: list[dict]) -> list[dict]:
        """Extract FAQ questions and answers from FAQPage structured data."""
        faqs = []

        for block in structured_data:
            # Check top-level
            if block.get("@type") == "FAQPage":
                faqs.extend(self._extract_qa_from_faq(block))

            # Check @graph
            if "@graph" in block:
                for item in block["@graph"]:
                    if isinstance(item, dict) and item.get("@type") == "FAQPage":
                        faqs.extend(self._extract_qa_from_faq(item))

        return faqs

    def _extract_qa_from_faq(self, faq_block: dict) -> list[dict]:
        """Extract Q&A pairs from a FAQPage block."""
        qa_pairs = []
        main_entity = faq_block.get("mainEntity", [])

        if not isinstance(main_entity, list):
            main_entity = [main_entity]

        for entity in main_entity:
            if not isinstance(entity, dict):
                continue
            if entity.get("@type") != "Question":
                continue

            question = entity.get("name", "")
            accepted_answer = entity.get("acceptedAnswer", {})
            if isinstance(accepted_answer, dict):
                answer = accepted_answer.get("text", "")
            else:
                answer = str(accepted_answer)

            if question:
                qa_pairs.append({"question": question, "answer": answer})

        return qa_pairs

    def _score_question_patterns(self, content_questions: list[str]) -> tuple[int, dict]:
        """Score the presence of question patterns in content."""
        count = len(content_questions)

        if count >= 8:
            score = 100
        elif count >= 5:
            score = 80
        elif count >= 3:
            score = 60
        elif count >= 1:
            score = 35
        else:
            score = 0

        return score, {"question_count": count}

    def _score_faq_markup(self, faq_markup: list[dict]) -> tuple[int, dict]:
        """Score the presence and completeness of FAQPage markup."""
        if not faq_markup:
            return 0, {"has_faq_markup": False, "faq_count": 0}

        count = len(faq_markup)
        if count >= 5:
            score = 100
        elif count >= 3:
            score = 75
        elif count >= 1:
            score = 50
        else:
            score = 0

        return score, {"has_faq_markup": True, "faq_count": count}

    def _score_markup_correspondence(
        self, content_questions: list[str], faq_markup: list[dict]
    ) -> tuple[int, dict]:
        """Check if markup questions correspond to content questions."""
        if not faq_markup:
            # No markup to compare
            return 0 if content_questions else 50, {"matching_count": 0}

        if not content_questions:
            # Markup exists but no content questions
            return 50, {"matching_count": 0}

        # Fuzzy matching: check if markup questions appear in content
        markup_questions = {q["question"].lower().strip() for q in faq_markup}
        content_lower = {q.lower().strip() for q in content_questions}

        matching = 0
        for mq in markup_questions:
            for cq in content_lower:
                # Check for substantial overlap (at least 3 shared words)
                mq_words = set(mq.split())
                cq_words = set(cq.split())
                common = mq_words & cq_words
                if len(common) >= 3 or mq == cq:
                    matching += 1
                    break

        if not markup_questions:
            return 50, {"matching_count": 0}

        ratio = matching / len(markup_questions)
        score = int(ratio * 100)

        return score, {"matching_count": matching, "total_markup": len(markup_questions)}

    def _score_answer_quality(self, faq_markup: list[dict]) -> tuple[int, dict]:
        """Score the quality of answers in FAQ markup."""
        if not faq_markup:
            return 0, {"avg_answer_length": 0, "short_answers": 0}

        answer_lengths = []
        short_count = 0

        for qa in faq_markup:
            answer = qa.get("answer", "")
            word_count = len(answer.split())
            answer_lengths.append(word_count)
            if word_count < FAQ_MIN_ANSWER_WORDS:
                short_count += 1

        avg_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0

        if avg_length >= FAQ_MIN_ANSWER_WORDS and short_count == 0:
            score = 100
        elif avg_length >= FAQ_MIN_ANSWER_WORDS:
            score = 75
        elif avg_length >= 25:
            score = 50
        elif avg_length > 0:
            score = 25
        else:
            score = 0

        return score, {
            "avg_answer_length": round(avg_length, 1),
            "short_answers": short_count,
            "total_answers": len(faq_markup),
        }

    def _score_missing_questions(
        self, content_questions: list[str], faq_markup: list[dict]
    ) -> tuple[int, dict]:
        """Score how many content questions are missing from FAQ markup."""
        if not content_questions:
            return 50, {"missing_count": 0}  # Neutral

        if not faq_markup:
            # All content questions are missing from markup
            return 0, {
                "missing_count": len(content_questions),
                "missing_questions": content_questions[:5],
            }

        markup_lower = {q["question"].lower().strip() for q in faq_markup}
        missing = []

        for cq in content_questions:
            cq_lower = cq.lower().strip()
            found = False
            for mq in markup_lower:
                mq_words = set(mq.split())
                cq_words = set(cq_lower.split())
                common = mq_words & cq_words
                if len(common) >= 3 or mq == cq_lower:
                    found = True
                    break
            if not found:
                missing.append(cq)

        if not missing:
            score = 100
        else:
            ratio = 1 - (len(missing) / len(content_questions))
            score = max(0, int(ratio * 100))

        return score, {
            "missing_count": len(missing),
            "missing_questions": missing[:5],
        }

    def _collect_issues(
        self, details: dict, content_questions: list[str], faq_markup: list[dict]
    ) -> list[str]:
        """Collect FAQ-related issues."""
        issues = []

        if details["question_patterns"]["score"] < 40:
            issues.append(
                "Few question-based patterns found in content. "
                "Add 'How to', 'What is', 'Why' headings for better AI coverage."
            )

        if details["faq_markup"]["score"] == 0:
            if content_questions:
                issues.append(
                    f"Found {len(content_questions)} question(s) in content "
                    "but no FAQPage markup. Add FAQPage structured data."
                )
            else:
                issues.append(
                    "No FAQ content or FAQPage markup found. "
                    "Add Q&A sections with proper schema markup."
                )

        if details["markup_correspondence"]["score"] < 50 and faq_markup:
            issues.append(
                "FAQ markup questions don't match content well. "
                "Ensure markup questions appear in the visible page content."
            )

        if details["answer_quality"]["score"] < 50 and faq_markup:
            short = details["answer_quality"].get("short_answers", 0)
            issues.append(
                f"{short} FAQ answer(s) are too short (under {FAQ_MIN_ANSWER_WORDS} words). "
                "Expand answers for better AI citation potential."
            )

        missing_details = details.get("missing_in_markup", {})
        missing_count = missing_details.get("missing_count", 0)
        if missing_count > 0 and faq_markup:
            issues.append(
                f"{missing_count} question(s) in content not included in FAQPage markup. "
                "Add these to structured data for complete coverage."
            )

        return issues
