"""Content readability analysis service."""

import logging
import re

logger = logging.getLogger(__name__)


def syllable_count(word: str) -> int:
    """Count syllables in a word using heuristic approach.

    Works well for English, reasonable fallback for other languages.
    """
    word = word.lower().strip()
    if not word:
        return 0

    # Simple English heuristic
    if len(word) <= 3:
        return 1

    # Count vowel groups
    vowels = "aeiouy"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    # Adjust for silent e
    if word.endswith("e") and count > 1:
        count -= 1

    # Adjust for -le ending
    if word.endswith("le") and len(word) > 2 and word[-3] not in vowels:
        count += 1

    return max(1, count)


def syllable_count_fr(word: str) -> int:
    """Count syllables in a French word.

    French-specific rules:
    - Silent trailing 'e' (but not 'é', 'è', 'ê')
    - '-tion' counts as 2 syllables (ti-on)
    - Vowel groups with accented chars
    """
    word = word.lower().strip()
    if not word:
        return 0

    if len(word) <= 3:
        return 1

    # French vowels including accented
    vowels = "aeiouyàâäéèêëïîôùûüœæ"
    count = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel

    # Silent trailing 'e' (not accented)
    if word.endswith("e") and not word.endswith(("ée", "ie", "ue")) and count > 1:
        count -= 1

    # Silent trailing 'es'
    if word.endswith("es") and count > 1:
        count -= 1

    # Silent trailing 'ent' (verb conjugation)
    if word.endswith("ent") and len(word) > 4 and count > 1:
        count -= 1

    return max(1, count)


def avg_sentence_length(text: str) -> float:
    """Calculate average sentence length in words."""
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    word_counts = [len(s.split()) for s in sentences]
    return sum(word_counts) / len(word_counts)


def avg_syllables_per_word(text: str, language: str = "en") -> float:
    """Calculate average syllables per word."""
    words = re.findall(r"\b[a-zA-Z\u00C0-\u00FF]+\b", text)
    if not words:
        return 0.0
    counter = syllable_count_fr if language == "fr" else syllable_count
    total_syllables = sum(counter(w) for w in words)
    return total_syllables / len(words)


def flesch_reading_ease(text: str) -> float:
    """Calculate Flesch Reading Ease score (English).

    Formula: 206.835 - 1.015 x ASL - 84.6 x ASW

    Score interpretation:
    90-100: Very easy (5th grade)
    80-89: Easy (6th grade)
    70-79: Fairly easy (7th grade)
    60-69: Standard (8th-9th grade) - IDEAL for web content
    50-59: Fairly difficult (10th-12th grade)
    30-49: Difficult (college level)
    0-29: Very difficult (graduate level)
    """
    asl = avg_sentence_length(text)
    asw = avg_syllables_per_word(text, "en")

    if asl == 0 or asw == 0:
        return 0.0

    return 206.835 - (1.015 * asl) - (84.6 * asw)


def kandel_moles_reading_ease(text: str) -> float:
    """Calculate Kandel-Moles Reading Ease score (French).

    Formula: 207 - 1.015 x ASL - 73.6 x ASW

    Adapted from Flesch for French language characteristics.
    French has naturally longer words, so the syllable coefficient is lower.

    Score interpretation (similar scale to Flesch):
    90-100: Très facile
    80-89: Facile
    70-79: Assez facile
    60-69: Standard — idéal pour le web
    50-59: Assez difficile
    30-49: Difficile
    0-29: Très difficile
    """
    asl = avg_sentence_length(text)
    asw = avg_syllables_per_word(text, "fr")

    if asl == 0 or asw == 0:
        return 0.0

    return 207.0 - (1.015 * asl) - (73.6 * asw)


def flesch_kincaid_grade(text: str, language: str = "en") -> float:
    """Calculate Flesch-Kincaid Grade Level.

    Formula: 0.39 x ASL + 11.8 x ASW - 15.59

    Returns US grade level (e.g., 8.0 = 8th grade reading level).
    Target for web content: 6th-8th grade.
    """
    asl = avg_sentence_length(text)
    asw = avg_syllables_per_word(text, language)

    if asl == 0 or asw == 0:
        return 0.0

    return (0.39 * asl) + (11.8 * asw) - 15.59


def _interpret_reading_ease(score: float, language: str = "en") -> str:
    """Interpret Flesch/Kandel-Moles Reading Ease score."""
    if language == "fr":
        if score >= 90:
            return "Très facile à lire. Accessible à tous."
        elif score >= 80:
            return "Facile à lire. Langage courant."
        elif score >= 70:
            return "Assez facile. Bon pour la majorité des lecteurs."
        elif score >= 60:
            return "Difficulté standard. Idéal pour le contenu web."
        elif score >= 50:
            return "Assez difficile. Risque de perdre les lecteurs occasionnels."
        elif score >= 30:
            return "Difficile. Niveau universitaire. Envisagez de simplifier."
        else:
            return "Très difficile. Contenu trop complexe pour un public web général."

    if score >= 90:
        return "Very easy to read. Suitable for elementary students."
    elif score >= 80:
        return "Easy to read. Conversational English."
    elif score >= 70:
        return "Fairly easy to read. Good for most audiences."
    elif score >= 60:
        return "Standard difficulty. Ideal for web content (8th-9th grade level)."
    elif score >= 50:
        return "Fairly difficult. May lose casual readers."
    elif score >= 30:
        return "Difficult. College-level reading. Consider simplifying for wider audience."
    else:
        return "Very difficult. Graduate-level reading. Likely too complex for general web content."


def _interpret_grade_level(grade: float) -> str:
    """Interpret grade level for SEO context."""
    if grade <= 6:
        return "Very accessible. Great for broad audience reach."
    elif grade <= 8:
        return "Ideal for web content. Balances depth with accessibility."
    elif grade <= 10:
        return "Somewhat complex. May reduce engagement for casual readers."
    elif grade <= 12:
        return "Complex. Best for technical or specialized audiences."
    else:
        return "Very complex. Consider simplifying unless targeting experts."


def analyze(text: str, language: str = "en") -> dict:
    """Run full readability analysis on text.

    Args:
        text: The content to analyze.
        language: Content language ('en' for Flesch, 'fr' for Kandel-Moles).

    Returns:
        Dict with readability scores, interpretations, and word stats.
    """
    if not text or len(text.strip()) < 50:
        return {
            "error": "Insufficient text for readability analysis (minimum 50 characters)",
            "word_count": len(text.split()) if text else 0,
        }

    words = re.findall(r"\b[a-zA-Z\u00C0-\u00FF]+\b", text)
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]

    asl = avg_sentence_length(text)
    asw = avg_syllables_per_word(text, language)

    if language == "fr":
        reading_ease = kandel_moles_reading_ease(text)
        formula_name = "kandel_moles_reading_ease"
        formula_label = "Kandel-Moles (adapted for French)"
    else:
        reading_ease = flesch_reading_ease(text)
        formula_name = "flesch_reading_ease"
        formula_label = "Flesch Reading Ease"

    fkg = flesch_kincaid_grade(text, language)

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_sentence_length": round(asl, 1),
        "avg_syllables_per_word": round(asw, 2),
        formula_name: {
            "score": round(reading_ease, 1),
            "formula": formula_label,
            "interpretation": _interpret_reading_ease(reading_ease, language),
            "ideal_range": "60-70 for web content",
        },
        "flesch_kincaid_grade": {
            "grade": round(fkg, 1),
            "interpretation": _interpret_grade_level(fkg),
            "ideal_range": "6th-8th grade for web content",
        },
        "seo_recommendation": _seo_readability_recommendation(reading_ease, fkg, asl, language),
        "language": language,
    }


def _seo_readability_recommendation(
    reading_ease: float, fkg: float, asl: float, language: str = "en"
) -> str:
    """Generate SEO-specific readability recommendation."""
    recommendations = []

    if reading_ease < 50:
        if language == "fr":
            recommendations.append(
                "Le contenu est trop complexe pour un public web général. "
                "Simplifiez la structure des phrases et utilisez des mots plus courts."
            )
        else:
            recommendations.append(
                "Content is too complex for general web audience. "
                "Simplify sentence structure and use shorter words."
            )
    elif reading_ease < 60:
        if language == "fr":
            recommendations.append(
                "La lisibilité est en dessous de l'idéal. "
                "Découpez les phrases longues et utilisez un vocabulaire plus simple."
            )
        else:
            recommendations.append(
                "Content readability is below ideal. "
                "Consider breaking long sentences and using simpler vocabulary."
            )

    if asl > 25:
        if language == "fr":
            recommendations.append(
                f"La longueur moyenne des phrases ({asl:.0f} mots) est trop élevée. "
                "Visez 15-20 mots par phrase."
            )
        else:
            recommendations.append(
                f"Average sentence length ({asl:.0f} words) is too high. "
                "Target 15-20 words per sentence."
            )

    if fkg > 10:
        recommendations.append(
            f"Grade level ({fkg:.1f}) is above web content ideal. Target 6th-8th grade level."
        )

    if not recommendations:
        if language == "fr":
            return "La lisibilité est bien optimisée pour le contenu web."
        return "Readability is well-optimized for web content. Good job!"

    return " ".join(recommendations)
