"""Meta tag and headline generation with AI + deterministic fallback."""

import logging
from datetime import datetime

from app.services.llm.prompt_templates import (
    SYSTEM_PROMPT_CONTENT_WRITER,
    build_headline_generation_prompt,
    build_meta_generation_prompt,
)

logger = logging.getLogger(__name__)

_CURRENT_YEAR = str(datetime.now().year)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, cutting at last space if possible."""
    if len(text) <= max_len:
        return text
    truncated = text[: max_len - 1]
    last_space = truncated.rfind(" ")
    if last_space > max_len // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "\u2026"


class MetaGeneratorService:
    """Generate optimized meta tags and headlines, with LLM or deterministic fallback."""

    def __init__(self, ai_analyzer, editorial_context):
        self.ai = ai_analyzer
        self.editorial = editorial_context

    async def generate_meta(
        self, target_keyword: str, target_url: str = "", page_data: dict | None = None
    ) -> dict:
        """Generate 5 title tags + 5 meta descriptions with CTR scoring.

        Returns:
            {
                "titles": [{"title": str, "length": int, "ctr_score": float, "strategy": str}, ...],
                "descriptions": [{"description": str, "length": int, "ctr_score": float, "strategy": str}, ...],
                "best_combination": {"title": str, "description": str, "rationale": str},
                "ai_enhanced": bool,
            }
        """
        if page_data is None:
            page_data = {}
        page_data.setdefault("keyword", target_keyword)
        if target_url:
            page_data.setdefault("url", target_url)

        if self.ai.ai_available:
            try:
                brand_context = self.editorial.get_brand_voice()
                prompt = build_meta_generation_prompt(page_data, brand_context)
                raw = await self.ai.llm.complete_json(SYSTEM_PROMPT_CONTENT_WRITER, prompt)
                return self._normalize_ai_meta(raw)
            except Exception as e:
                logger.warning("AI meta generation failed, using fallback: %s", e)

        return self._deterministic_meta(target_keyword)

    async def generate_headlines(self, topic: str, keywords: list | None = None) -> dict:
        """Generate 10+ headline variations with conversion scoring.

        Returns:
            {
                "headlines": [{"headline": str, "score": int, "emotional_trigger": str, "formula": str, "best_for": str}, ...],
                "top_3_picks": [{"headline": str, "rationale": str}, ...],
                "ai_enhanced": bool,
            }
        """
        if keywords is None:
            keywords = []

        if self.ai.ai_available:
            try:
                brand_context = self.editorial.get_brand_voice()
                prompt = build_headline_generation_prompt(topic, keywords, brand_context)
                raw = await self.ai.llm.complete_json(SYSTEM_PROMPT_CONTENT_WRITER, prompt)
                return self._normalize_ai_headlines(raw)
            except Exception as e:
                logger.warning("AI headline generation failed, using fallback: %s", e)

        return self._deterministic_headlines(topic)

    # ── AI result normalization ───────────────────────────────────────

    @staticmethod
    def _normalize_ai_meta(raw: dict) -> dict:
        """Map LLM output keys to our public schema."""
        titles = []
        for t in raw.get("title_tags", []):
            titles.append(
                {
                    "title": t.get("title", ""),
                    "length": t.get("char_count", len(t.get("title", ""))),
                    "ctr_score": t.get("ctr_score", 0),
                    "strategy": t.get("strategy", ""),
                }
            )
        descriptions = []
        for d in raw.get("meta_descriptions", []):
            descriptions.append(
                {
                    "description": d.get("description", ""),
                    "length": d.get("char_count", len(d.get("description", ""))),
                    "ctr_score": d.get("ctr_score", 0),
                    "strategy": d.get("cta_type", ""),
                }
            )
        best = raw.get("best_combination", {})
        return {
            "titles": titles,
            "descriptions": descriptions,
            "best_combination": {
                "title": best.get("title", ""),
                "description": best.get("description", ""),
                "rationale": best.get("rationale", ""),
            },
            "ai_enhanced": True,
        }

    @staticmethod
    def _normalize_ai_headlines(raw: dict) -> dict:
        """Map LLM output keys to our public schema."""
        headlines = []
        for h in raw.get("headlines", []):
            headlines.append(
                {
                    "headline": h.get("headline", ""),
                    "score": h.get("score", 0),
                    "emotional_trigger": h.get("emotional_trigger", ""),
                    "formula": h.get("formula", ""),
                    "best_for": h.get("best_for", ""),
                }
            )
        top_3 = []
        for p in raw.get("top_3_picks", raw.get("top_picks", []))[:3]:
            top_3.append(
                {
                    "headline": p.get("headline", ""),
                    "rationale": p.get("rationale", ""),
                }
            )
        return {
            "headlines": headlines,
            "top_3_picks": top_3,
            "ai_enhanced": True,
        }

    # ── Deterministic fallbacks ───────────────────────────────────────

    def _deterministic_meta(self, keyword: str) -> dict:
        """Generate rule-based meta tags from keyword templates."""
        kw = keyword.strip()
        kw_cap = kw.title()
        year = _CURRENT_YEAR

        raw_titles = [
            (f"{kw_cap} - Guide Complet {year}", "power_word"),
            (f"{kw_cap} : Tout Ce Qu'il Faut Savoir", "curiosity"),
            (f"Top 10 {kw_cap} : Comparatif et Avis {year}", "number"),
            (f"Comment {kw_cap} ? Conseils d'Experts", "question"),
            (f"{kw_cap} : Boostez Vos Performances", "benefit"),
        ]

        titles = []
        for text, strategy in raw_titles:
            text = _truncate(text, 60)
            titles.append(
                {
                    "title": text,
                    "length": len(text),
                    "ctr_score": 5.0,
                    "strategy": strategy,
                }
            )

        raw_descs = [
            (
                f"Découvrez {kw} : notre guide complet avec conseils pratiques, exemples concrets et astuces d'experts pour réussir en {year}.",
                "discover",
            ),
            (
                f"Tout savoir sur {kw}. Comparatif détaillé, avantages, inconvénients et recommandations pour faire le bon choix.",
                "compare",
            ),
            (
                f"Apprenez {kw} étape par étape avec notre méthode éprouvée. Résultats garantis, même pour les débutants.",
                "learn",
            ),
            (
                f"Besoin d'aide avec {kw} ? Nos experts partagent leurs meilleures stratégies et outils testés en {year}.",
                "get",
            ),
            (
                f"Essayez notre approche de {kw} et obtenez des résultats concrets. Guide gratuit avec check-list téléchargeable.",
                "try",
            ),
        ]

        descriptions = []
        for text, cta_type in raw_descs:
            text = _truncate(text, 155)
            descriptions.append(
                {
                    "description": text,
                    "length": len(text),
                    "ctr_score": 5.0,
                    "strategy": cta_type,
                }
            )

        return {
            "titles": titles,
            "descriptions": descriptions,
            "best_combination": {
                "title": titles[0]["title"],
                "description": descriptions[0]["description"],
                "rationale": "Guide complet + découverte CTA — combinaison polyvalente à fort CTR.",
            },
            "ai_enhanced": False,
        }

    def _deterministic_headlines(self, topic: str) -> dict:
        """Generate rule-based headline variations from topic templates."""
        t = topic.strip()
        t_cap = t.title() if len(t) < 40 else t
        year = _CURRENT_YEAR

        raw_headlines = [
            (f"Comment {t_cap} en {year}", 7, "curiosity", "how-to", "blog article"),
            (f"7 Façons de {t_cap} Efficacement", 7, "power", "listicle", "social media"),
            (f"{t_cap} : Le Guide Ultime", 8, "authority", "ultimate guide", "pillar content"),
            (f"Pourquoi {t_cap} Change Tout en {year}", 6, "urgency", "why + year", "newsletter"),
            (f"{t_cap} : Erreurs à Éviter Absolument", 7, "fear", "mistakes", "blog article"),
            (
                f"Les Secrets de {t_cap} Révélés",
                6,
                "exclusivity",
                "secrets revealed",
                "landing page",
            ),
            (f"{t_cap} : Avant/Après en 30 Jours", 8, "proof", "before/after", "case study"),
            (
                f"Tout Savoir sur {t_cap} (Guide {year})",
                6,
                "completeness",
                "comprehensive",
                "SEO content",
            ),
            (
                f"{t_cap} vs Alternatives : Le Vrai Comparatif",
                7,
                "objectivity",
                "versus",
                "comparison page",
            ),
            (
                f"{t_cap} pour Débutants : Par Où Commencer ?",
                6,
                "empathy",
                "beginner guide",
                "tutorial",
            ),
        ]

        headlines = []
        for text, score, trigger, formula, best_for in raw_headlines:
            headlines.append(
                {
                    "headline": text,
                    "score": score,
                    "emotional_trigger": trigger,
                    "formula": formula,
                    "best_for": best_for,
                }
            )

        top_3 = [
            {
                "headline": headlines[2]["headline"],
                "rationale": "Le format guide ultime attire les clics et positionne l'autorité.",
            },
            {
                "headline": headlines[0]["headline"],
                "rationale": "Le how-to répond directement à l'intention de recherche.",
            },
            {
                "headline": headlines[6]["headline"],
                "rationale": "La preuve sociale (avant/après) booste la crédibilité et le CTR.",
            },
        ]

        return {
            "headlines": headlines,
            "top_3_picks": top_3,
            "ai_enhanced": False,
        }
