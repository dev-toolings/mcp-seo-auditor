"""Centralized scoring constants for the SEO Auditor.

All scoring weights, thresholds, and magic numbers live here so tuning
is possible without modifying 5 different service files.
"""

# ── Grade boundaries (shared by ai_analyzer, geo_analyzer, quick_check) ──
GRADE_BOUNDARIES = {"A": 90, "B": 80, "C": 70, "D": 60}  # below D → F


def compute_grade(score: int) -> str:
    """Convert numeric score (0-100) to letter grade."""
    for letter, threshold in GRADE_BOUNDARIES.items():
        if score >= threshold:
            return letter
    return "F"


# ── Effort mapping (shared by ai_analyzer, action_plan) ──────────────────
EFFORT_MAP = {"minimal": 1, "low": 3, "medium": 5, "high": 7, "major": 9}

# ── Overall dimension weights (single source of truth) ───────────────────
DIMENSION_WEIGHTS = {
    "technical": 0.15,
    "content": 0.20,
    "links": 0.15,
    "schema": 0.15,
    "performance": 0.10,
    "geo": 0.25,
}


class AuditScorer:
    """Centralized scoring utilities for SEO audits."""

    @staticmethod
    def calculate_overall_score(dimension_scores: dict[str, int]) -> int:
        """Weighted average of measured dimension scores.

        Missing dimensions are not treated as zero. Some audits intentionally skip
        optional checks such as Core Web Vitals, and third-party data such as GEO
        enrichment can fail independently. Counting absent dimensions as zero
        makes the score describe tool coverage rather than SEO quality.
        """
        measured = {
            key: score
            for key, score in dimension_scores.items()
            if key in DIMENSION_WEIGHTS and score is not None
        }
        total_weight = sum(DIMENSION_WEIGHTS[key] for key in measured)
        if total_weight == 0:
            return 0

        total = sum(score * DIMENSION_WEIGHTS[key] for key, score in measured.items())
        total = total / total_weight
        return max(0, min(100, int(total)))

    @staticmethod
    def compute_grade(score: int) -> str:
        """Convert numeric score (0-100) to letter grade."""
        return compute_grade(score)


# ── GEO dimension weights (geo_analyzer) ─────────────────────────────────
GEO_WEIGHTS = {
    "ai_readability": 0.25,
    "schema_coverage": 0.20,
    "eeat": 0.20,
    "faq_completeness": 0.15,
    "citation_readiness": 0.20,
}

# ── Citation readiness sub-weights (geo/citation_readiness) ──────────────
CITATION_SUB_WEIGHTS = {
    "stat_density": 0.25,
    "answer_first": 0.25,
    "quotable_sentences": 0.20,
    "cited_sources": 0.20,
    "freshness": 0.10,
}

# ── Per-engine GEO weight profiles ───────────────────────────────────────
# Each profile re-weights the five GEO dimensions to match how a given AI engine
# sources its answers. Every profile sums to 1.0. "all" uses the balanced default.
ENGINE_GEO_WEIGHTS = {
    "all": GEO_WEIGHTS,
    # AI Overviews rides Google's index: schema + E-E-A-T dominate.
    "google_ai_overviews": {
        "ai_readability": 0.20,
        "schema_coverage": 0.25,
        "eeat": 0.25,
        "faq_completeness": 0.15,
        "citation_readiness": 0.15,
    },
    # Perplexity is citation-first: outbound sources + quotable, current claims.
    "perplexity": {
        "ai_readability": 0.20,
        "schema_coverage": 0.10,
        "eeat": 0.20,
        "faq_completeness": 0.10,
        "citation_readiness": 0.40,
    },
    # ChatGPT Search rides Bing: parseability + citation-worthiness.
    "chatgpt_search": {
        "ai_readability": 0.25,
        "schema_coverage": 0.15,
        "eeat": 0.20,
        "faq_completeness": 0.10,
        "citation_readiness": 0.30,
    },
    # Gemini rides Google: schema + readability heavy.
    "gemini": {
        "ai_readability": 0.25,
        "schema_coverage": 0.25,
        "eeat": 0.20,
        "faq_completeness": 0.15,
        "citation_readiness": 0.15,
    },
}

# ── Cross-tool correlator signal weights ─────────────────────────────────
SIGNAL_WEIGHTS = {
    "thin_content": 3,
    "missing_meta": 2,
    "missing_h1": 2,
    "missing_schema": 2,
    "broken_link_target": 3,
    "orphan_page": 3,
    "canonical_issue": 3,
    "noindex_in_sitemap": 4,
    "low_cwv": 2,
    "low_eeat": 2,
    "low_geo": 2,
    "cannibalized": 3,
    "low_readability": 1,
    "missing_alt": 1,
    "redirect_chain": 2,
}

COMPOUND_THRESHOLD = 3  # Minimum signals to flag as compound issue

# ── Scoring thresholds ───────────────────────────────────────────────────
# Below these, recommendations are generated
RECOMMENDATION_THRESHOLDS = {
    "technical": 60,
    "content": 60,
    "links": 60,
    "schema": 50,
    "performance": 60,
    "geo": 60,
}

# ── Issue scoring multipliers (used in core_seo tools) ───────────────────
CRITICAL_ISSUE_PENALTY = 10  # Points deducted per critical issue
WARNING_ISSUE_PENALTY = 2  # Points deducted per warning (sitemap/quick_check)
CONTENT_WARNING_PENALTY = 3  # Points deducted per warning (content audit)
CANNIBALIZATION_CRITICAL_PENALTY = 15
CANNIBALIZATION_WARNING_PENALTY = 5

# ── Full audit link penalties ────────────────────────────────────────────
ORPHAN_PAGE_PENALTY = 5
BROKEN_LINK_PENALTY = 10

# ── Cross-correlator thresholds ──────────────────────────────────────────
THIN_CONTENT_WORD_THRESHOLD = 100
LOW_CWV_THRESHOLD = 50
LOW_GEO_THRESHOLD = 40
LOW_EEAT_THRESHOLD = 40
COMPOUND_CRITICAL_WEIGHT = 10  # total_weight >= this → "critical" priority

# ── Action plan thresholds ───────────────────────────────────────────────
QUICK_WIN_MIN_IMPACT = 7
QUICK_WIN_MAX_EFFORT = 3
STRATEGIC_MIN_IMPACT = 7
STRATEGIC_MIN_EFFORT = 6
TIMELINE_ORDER = ["immediate", "short-term", "medium-term", "long-term"]

# ── FAQ completeness (geo/faq_completeness) ──────────────────────────────
FAQ_MIN_ANSWER_WORDS = 100
FAQ_SUB_WEIGHTS = {
    "patterns": 0.25,
    "markup": 0.25,
    "correspondence": 0.20,
    "quality": 0.15,
    "missing": 0.15,
}
FAQ_QUESTION_COUNT_THRESHOLDS = [(8, 100), (5, 80), (3, 60), (1, 35), (0, 0)]
FAQ_MARKUP_COUNT_THRESHOLDS = [(5, 100), (3, 75), (1, 50), (0, 0)]
# (min_avg_words, score) — first entry also requires short_count==0
FAQ_ANSWER_QUALITY_THRESHOLDS = [(50, 100), (50, 75), (25, 50), (0, 25)]

# ── AI readability (geo/ai_readability) ──────────────────────────────────
READABILITY_IDEAL_SENTENCE_MIN = 15
READABILITY_IDEAL_SENTENCE_MAX = 25
READABILITY_SUB_WEIGHTS = {
    "sentence": 0.25,
    "factual": 0.20,
    "answers": 0.25,
    "freshness": 0.15,
    "expertise": 0.15,
}
READABILITY_FACTUAL_THRESHOLDS = [(5, 100), (3, 80), (1, 60), (0, 40)]
READABILITY_FRESHNESS_THRESHOLDS = [(3, 100), (2, 80), (1, 50), (0, 20)]
READABILITY_EXPERTISE_THRESHOLDS = [(4, 100), (2, 70), (1, 40), (0, 15)]

# ── E-E-A-T detector (geo/eeat_detector) ────────────────────────────────
EEAT_MAX_POINTS = {
    "author_info": 20,
    "publication_date": 10,
    "external_citations": 15,
    "contact_about": 10,
    "social_proof": 10,
    "original_research": 15,
    "trust_signals": 10,
    "experience_markers": 10,
}
EEAT_EXPERIENCE_THRESHOLDS = [(3, 10), (2, 7), (1, 4), (0, 0)]
EEAT_CITATION_THRESHOLDS = [(3, 15), (2, 12), (1, 8)]  # authoritative
EEAT_CITATION_EXTERNAL_FALLBACK = [(5, 5), (1, 3)]  # non-authoritative external
AUTHORITATIVE_DOMAINS = {
    # International
    ".gov",
    ".edu",
    "wikipedia.org",
    "who.int",
    "nih.gov",
    "cdc.gov",
    "nature.com",
    "sciencedirect.com",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
    "reuters.com",
    "apnews.com",
    # French / EU
    ".gouv.fr",
    "service-public.fr",
    "legifrance.gouv.fr",
    "data.gouv.fr",
    "europa.eu",
    "insee.fr",
    "has-sante.fr",
    "education.gouv.fr",
    "economie.gouv.fr",
    "ameli.fr",
}

# ── Schema coverage (geo/schema_coverage) ────────────────────────────────
AI_PRIORITY_SCHEMAS = {
    "FAQPage": 25,
    "HowTo": 20,
    "Article": 20,
    "Dataset": 20,
    "DefinedTerm": 18,
    "ItemList": 18,
    "Claim": 18,
    "ClaimReview": 18,
    "WebPage": 15,
    "Product": 15,
    "Review": 12,
    "Event": 12,
    "VideoObject": 10,
    "NewsArticle": 5,
    "BlogPosting": 5,
}
SCHEMA_SUB_WEIGHTS = {
    "presence": 0.22,
    "speakable": 0.15,
    "priority": 0.22,
    "nesting": 0.08,
    "author": 0.18,
    "entity_clarity": 0.15,
}
SCHEMA_PRIORITY_POINTS = {
    "FAQPage": 25,
    "HowTo": 20,
    "Article": 20,
    "NewsArticle": 20,
    "BlogPosting": 20,
    "Dataset": 20,
    "DefinedTerm": 18,
    "ItemList": 18,
    "Claim": 18,
    "ClaimReview": 18,
    "WebPage": 15,
    "Product": 15,
    "Review": 12,
    "Event": 12,
    "VideoObject": 10,
}

# Authoritative identity hosts that a schema `sameAs` should point to (entity clarity).
AUTHORITATIVE_SAMEAS_HOSTS = (
    "wikidata.org",
    "wikipedia.org",
    "linkedin.com",
    "crunchbase.com",
    "github.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "imdb.com",
    "musicbrainz.org",
)

# ── SaaS viability (market/saas_viability) ───────────────────────────────
SAAS_DIMENSION_WEIGHTS = {
    "demand": 0.30,
    "growth": 0.25,
    "competition": 0.25,
    "opensource": 0.20,
}
SAAS_VERDICT_THRESHOLDS = {"go": 70, "explore": 40}  # below explore → "no-go"
SAAS_RECOMMENDATION_THRESHOLDS = {
    "low_demand": 30,
    "high_demand": 70,
    "high_growth": 65,
    "low_growth": 35,
    "high_competition": 30,
    "low_opensource": 40,
}

# ── AI analyzer score multipliers ────────────────────────────────────────
AI_ANALYZER_SCORE_MULTIPLIERS = {
    "issue_ratio": 20,
    "content_issues": 30,
    "link_issues": 25,
    "lcp_baseline": 1.5,
    "lcp_multiplier": 20,
}
