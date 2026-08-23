"""AI Query Intelligence — detect and classify AI-engine-generated queries from GSC data.

AI search engines (ChatGPT, Perplexity, Google AI Mode) decompose user queries
into conversational sub-queries that appear in GSC.  This module detects them
using regex heuristics and classifies them by intent type.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

logger = logging.getLogger(__name__)

# ── Regex patterns for AI-generated query detection ────────────────

# Queries with 10+ words are a signature of AI sub-queries
LONG_QUERY_THRESHOLD = 10
VERY_LONG_QUERY_THRESHOLD = 15

# Conversational patterns — French
AI_PATTERNS_FR = [
    re.compile(
        r"^(comment|quel|quelle|quels|quelles|pourquoi|est-ce que"
        r"|quelle est la meilleure|étape par étape|guide complet"
        r"|comparer|vs|différence entre)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(meilleur|comparatif|alternative|guide|tutoriel"
        r"|explication|définition|versus|avis|classement)",
        re.IGNORECASE,
    ),
]

# Conversational patterns — English
AI_PATTERNS_EN = [
    re.compile(
        r"^(how to|what is|why does|best way to|step by step"
        r"|compare|vs|difference between|should i|can i|is it worth)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(best|comparison|alternative|tutorial|explanation"
        r"|definition|versus|review|ranking|top \d+)",
        re.IGNORECASE,
    ),
]

# Question words (language-agnostic signal)
QUESTION_WORDS_FR = {"comment", "pourquoi", "quel", "quelle", "quels", "quelles", "où", "quand"}
QUESTION_WORDS_EN = {"how", "what", "why", "which", "where", "when", "who", "whose"}

# Intent classification patterns
CLASSIFICATION_PATTERNS = {
    "comparison": [
        re.compile(r"(vs|versus|compar|différence entre|difference between|ou choisir)", re.I),
        re.compile(r"(meilleur|best|top \d+|classement|ranking)", re.I),
    ],
    "how_to": [
        re.compile(r"(comment|how to|étape|step|tutoriel|tutorial|guide)", re.I),
        re.compile(r"(faire|créer|configurer|installer|setup|build|make)", re.I),
    ],
    "definition": [
        re.compile(r"(qu'?est[- ]ce qu|what is|définition|definition|signifi|meaning)", re.I),
        re.compile(r"(c'?est quoi|explain|expliquer)", re.I),
    ],
    "guide": [
        re.compile(r"(guide complet|complete guide|tout savoir|everything about)", re.I),
        re.compile(r"(comprendre|understand|en détail|in depth|approfondi)", re.I),
    ],
    "best_of": [
        re.compile(r"(meilleur|best|top \d+|recommand|suggest)", re.I),
        re.compile(r"(idéal|ideal|parfait|perfect|choix|choice|pick)", re.I),
    ],
    "evaluation": [
        re.compile(r"(avis|review|test|vaut|worth|fiable|reliable)", re.I),
        re.compile(r"(avantage|inconvénient|pros|cons|pour et contre)", re.I),
    ],
}


@dataclass
class ClassifiedQuery:
    """A GSC query classified by AI probability and intent."""

    query: str
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0
    page: str = ""
    ai_probability: float = 0.0
    category: str = "unknown"
    word_count: int = 0
    signals: list[str] = field(default_factory=list)


@dataclass
class AIQueryReport:
    """Report on AI-generated query analysis."""

    total_queries_analyzed: int = 0
    ai_queries_detected: int = 0
    ai_query_ratio: float = 0.0
    categories: dict[str, dict] = field(default_factory=dict)
    top_ai_queries: list[dict] = field(default_factory=list)
    enrichment_opportunities: list[dict] = field(default_factory=list)
    growth: dict = field(default_factory=dict)


class AIQueryIntelligenceService:
    """Detect and classify AI-engine-generated queries from GSC data."""

    def __init__(self, gsc_service=None, ai_analyzer=None):
        self.gsc = gsc_service
        self.ai = ai_analyzer

    async def analyze(
        self,
        site_url: str,
        days: int = 90,
        language: str = "fr",
    ) -> dict[str, Any]:
        """Run full AI query intelligence analysis.

        1. Fetch queries from GSC
        2. Classify each query
        3. Group by category
        4. Find enrichment opportunities
        5. Track growth if enough data
        """
        if not self.gsc or not self.gsc.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        # 1. Fetch queries with page dimension
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        raw = await self.gsc.get_advanced_search_analytics(
            site_url=site_url,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            dimensions=["query", "page"],
            row_limit=5000,
            sort_by="impressions",
            sort_direction="descending",
        )

        if raw.get("error"):
            return raw

        rows = raw.get("rows", [])
        if not rows:
            return {
                "total_queries_analyzed": 0,
                "ai_queries_detected": 0,
                "ai_query_ratio": 0.0,
                "message": "No query data found in GSC for this period",
            }

        # 2. Build query list
        queries = []
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 2:
                continue
            queries.append(
                {
                    "query": keys[0],
                    "page": keys[1],
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": row.get("ctr", 0.0),
                    "position": row.get("position", 0.0),
                }
            )

        # 3. Classify
        classified = self.detect_ai_queries(queries, language)

        # 4. Filter AI queries
        ai_queries = [q for q in classified if q.ai_probability >= 0.5]

        # 5. Group by category
        categories = self._group_by_category(ai_queries)

        # 6. Find enrichment opportunities
        opportunities = self.find_enrichment_opportunities(ai_queries)

        # 7. Build report
        top_ai = sorted(ai_queries, key=lambda q: q.impressions, reverse=True)[:20]

        result = {
            "total_queries_analyzed": len(queries),
            "ai_queries_detected": len(ai_queries),
            "ai_query_ratio": round(len(ai_queries) / max(len(queries), 1), 3),
            "categories": categories,
            "top_ai_queries": [
                {
                    "query": q.query,
                    "category": q.category,
                    "ai_probability": round(q.ai_probability, 2),
                    "clicks": q.clicks,
                    "impressions": q.impressions,
                    "ctr": round(q.ctr * 100, 2),
                    "position": round(q.position, 1),
                    "page": q.page,
                    "signals": q.signals,
                }
                for q in top_ai
            ],
            "enrichment_opportunities": opportunities[:15],
            "period_days": days,
            "language": language,
        }

        # 8. AI enrichment
        if self.ai and self.ai.ai_available:
            try:
                ai_insights = await self.ai.analyze_gsc_keywords(result)
                result["ai_insights"] = ai_insights
            except Exception as e:
                logger.warning("AI GSC keyword enrichment failed: %s", e)

        return result

    def detect_ai_queries(
        self,
        queries: list[dict],
        language: str = "fr",
    ) -> list[ClassifiedQuery]:
        """Classify each query by AI probability and intent category."""
        classified = []

        patterns = AI_PATTERNS_FR if language == "fr" else AI_PATTERNS_EN
        question_words = QUESTION_WORDS_FR if language == "fr" else QUESTION_WORDS_EN

        for q in queries:
            query_text = q.get("query", "")
            if not query_text:
                continue

            words = query_text.split()
            word_count = len(words)
            probability = 0.0
            signals = []

            # Signal 1: Word count
            if word_count >= VERY_LONG_QUERY_THRESHOLD:
                probability += 0.5
                signals.append(f"very_long_query ({word_count} words)")
            elif word_count >= LONG_QUERY_THRESHOLD:
                probability += 0.3
                signals.append(f"long_query ({word_count} words)")

            # Signal 2: Conversational patterns
            for pattern in patterns:
                if pattern.search(query_text):
                    probability += 0.2
                    signals.append(f"pattern_match: {pattern.pattern[:40]}")
                    break  # Count only once

            # Signal 3: Question words
            first_word = words[0].lower().rstrip("?") if words else ""
            if first_word in question_words:
                probability += 0.15
                signals.append("question_word")

            # Signal 4: Natural language vs keyword-style
            if self._is_natural_language(query_text):
                probability += 0.1
                signals.append("natural_language")

            # Cap at 1.0
            probability = min(1.0, probability)

            # Classify intent
            category = self._classify_intent(query_text)

            classified.append(
                ClassifiedQuery(
                    query=query_text,
                    clicks=q.get("clicks", 0),
                    impressions=q.get("impressions", 0),
                    ctr=q.get("ctr", 0.0),
                    position=q.get("position", 0.0),
                    page=q.get("page", ""),
                    ai_probability=probability,
                    category=category,
                    word_count=word_count,
                    signals=signals,
                )
            )

        return classified

    async def track_ai_traffic_growth(
        self,
        site_url: str,
        periods: int = 6,
        period_days: int = 14,
        language: str = "fr",
    ) -> dict[str, Any]:
        """Track growth of AI-generated query traffic over time periods."""
        if not self.gsc or not self.gsc.is_credentials_available:
            return {"error": "Google Search Console not configured"}

        end_date = datetime.now().date()
        period_data = []

        for i in range(periods):
            p_end = end_date - timedelta(days=i * period_days)
            p_start = p_end - timedelta(days=period_days)

            raw = await self.gsc.get_advanced_search_analytics(
                site_url=site_url,
                start_date=p_start.isoformat(),
                end_date=p_end.isoformat(),
                dimensions=["query"],
                row_limit=2000,
                sort_by="impressions",
                sort_direction="descending",
            )

            if raw.get("error"):
                continue

            rows = raw.get("rows", [])
            queries = [{"query": r.get("keys", [""])[0], **r} for r in rows if r.get("keys")]

            classified = self.detect_ai_queries(queries, language)
            ai_queries = [q for q in classified if q.ai_probability >= 0.5]

            total_clicks = sum(q.clicks for q in ai_queries)
            total_impressions = sum(q.impressions for q in ai_queries)

            period_data.append(
                {
                    "period_start": p_start.isoformat(),
                    "period_end": p_end.isoformat(),
                    "total_queries": len(queries),
                    "ai_queries": len(ai_queries),
                    "ai_clicks": total_clicks,
                    "ai_impressions": total_impressions,
                    "ai_ratio": round(len(ai_queries) / max(len(queries), 1), 3),
                }
            )

        # Reverse to chronological order
        period_data.reverse()

        # Calculate growth
        growth = self._calculate_growth(period_data)

        return {
            "periods": period_data,
            "growth_rate": growth.get("growth_rate", 0),
            "trend": growth.get("trend", "stable"),
            "summary": growth.get("summary", ""),
        }

    def find_enrichment_opportunities(
        self,
        ai_queries: list[ClassifiedQuery],
    ) -> list[dict]:
        """Find pages that could better serve AI queries.

        Opportunities: high impressions + low CTR + poor position.
        """
        opportunities = []

        for q in ai_queries:
            # High impressions but poor performance
            if q.impressions >= 50 and (q.position > 10 or q.ctr < 0.02):
                content_type = self._suggest_content_type(q.category)
                opportunities.append(
                    {
                        "query": q.query,
                        "category": q.category,
                        "current_page": q.page,
                        "impressions": q.impressions,
                        "clicks": q.clicks,
                        "position": round(q.position, 1),
                        "ctr": round(q.ctr * 100, 2),
                        "suggested_content_type": content_type,
                        "opportunity_score": self._calculate_opportunity_score(q),
                        "action": self._suggest_action(q),
                    }
                )

        opportunities.sort(key=lambda x: cast(float, x["opportunity_score"]), reverse=True)
        return opportunities

    def _is_natural_language(self, query: str) -> bool:
        """Check if query uses natural language (vs keyword-style)."""
        # Natural language indicators: articles, prepositions, conjunctions
        nl_words = {
            "le",
            "la",
            "les",
            "un",
            "une",
            "des",
            "du",
            "de",
            "pour",
            "avec",
            "dans",
            "sur",
            "par",
            "entre",
            "et",
            "ou",
            "mais",
            "the",
            "a",
            "an",
            "for",
            "with",
            "in",
            "on",
            "by",
            "between",
            "and",
            "or",
            "but",
            "to",
            "of",
        }
        words = set(query.lower().split())
        nl_count = len(words & nl_words)
        return nl_count >= 2

    def _classify_intent(self, query: str) -> str:
        """Classify query intent using regex patterns."""
        for category, patterns in CLASSIFICATION_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(query):
                    return category
        return "informational"

    def _suggest_content_type(self, category: str) -> str:
        """Suggest optimal content type for a query category."""
        mapping = {
            "comparison": "comparison_table",
            "how_to": "step_by_step_guide",
            "definition": "detailed_explanation",
            "guide": "comprehensive_guide",
            "best_of": "curated_list",
            "evaluation": "in_depth_review",
            "informational": "faq_section",
        }
        return mapping.get(category, "enriched_article")

    def _calculate_opportunity_score(self, q: ClassifiedQuery) -> float:
        """Score the enrichment opportunity (0-100)."""
        score = 0.0
        # High impressions = big opportunity
        if q.impressions >= 500:
            score += 40
        elif q.impressions >= 100:
            score += 25
        elif q.impressions >= 50:
            score += 15

        # Poor position = room to improve
        if q.position > 20:
            score += 30
        elif q.position > 10:
            score += 20
        elif q.position > 5:
            score += 10

        # Low CTR = meta/snippet needs work
        if q.ctr < 0.01:
            score += 20
        elif q.ctr < 0.03:
            score += 10

        # High AI probability = more relevant
        score += q.ai_probability * 10

        return min(100, round(score, 1))

    def _suggest_action(self, q: ClassifiedQuery) -> str:
        """Suggest concrete action for an opportunity."""
        if q.position > 20:
            return (
                f"Create dedicated {self._suggest_content_type(q.category)} "
                f"page targeting '{q.query[:50]}'"
            )
        if q.position > 10:
            return (
                f"Optimize existing page with {q.category}-focused content "
                f"and FAQ schema for '{q.query[:50]}'"
            )
        if q.ctr < 0.02:
            return (
                f"Improve title/meta description for '{q.query[:50]}' — "
                f"page ranks #{q.position:.0f} but CTR is only {q.ctr * 100:.1f}%"
            )
        return f"Monitor and maintain ranking for '{q.query[:50]}'"

    def _group_by_category(self, ai_queries: list[ClassifiedQuery]) -> dict[str, dict]:
        """Group AI queries by category with aggregate metrics."""
        categories: dict[str, dict] = {}

        for q in ai_queries:
            cat = q.category
            if cat not in categories:
                categories[cat] = {
                    "count": 0,
                    "total_clicks": 0,
                    "total_impressions": 0,
                    "positions": [],
                }
            categories[cat]["count"] += 1
            categories[cat]["total_clicks"] += q.clicks
            categories[cat]["total_impressions"] += q.impressions
            categories[cat]["positions"].append(q.position)

        # Calculate averages
        for cat, data in categories.items():
            positions = data.pop("positions")
            data["avg_position"] = round(sum(positions) / len(positions), 1) if positions else 0

        return categories

    def _calculate_growth(self, period_data: list[dict]) -> dict:
        """Calculate growth metrics from period data."""
        if len(period_data) < 2:
            return {"growth_rate": 0, "trend": "insufficient_data", "summary": ""}

        first = period_data[0]
        last = period_data[-1]

        first_ratio = first.get("ai_ratio", 0)
        last_ratio = last.get("ai_ratio", 0)

        if first_ratio > 0:
            growth_rate = round(((last_ratio - first_ratio) / first_ratio) * 100, 1)
        else:
            growth_rate = 100.0 if last_ratio > 0 else 0.0

        # Determine trend
        ratios = [p.get("ai_ratio", 0) for p in period_data]
        increasing = sum(1 for i in range(1, len(ratios)) if ratios[i] > ratios[i - 1])
        if increasing >= len(ratios) * 0.7:
            trend = "accelerating"
        elif increasing >= len(ratios) * 0.5:
            trend = "growing"
        elif increasing <= len(ratios) * 0.3:
            trend = "declining"
        else:
            trend = "stable"

        summary = (
            f"AI query ratio moved from {first_ratio:.1%} to {last_ratio:.1%} "
            f"over {len(period_data)} periods ({growth_rate:+.1f}% change). "
            f"Trend: {trend}."
        )

        return {
            "growth_rate": growth_rate,
            "trend": trend,
            "summary": summary,
        }
