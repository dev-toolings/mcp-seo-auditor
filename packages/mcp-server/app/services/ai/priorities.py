"""Quick wins and priority matrix from GSC data."""

import logging
from datetime import datetime, timedelta
from typing import Any

from app.services.ai.ai_analyzer import AIAnalyzer
from app.services.llm.prompt_templates import SYSTEM_PROMPT_SEO_ANALYST
from app.services.llm.token_budget import TokenBudget

logger = logging.getLogger(__name__)

# Expected CTR by position (Google organic, approximate benchmarks)
EXPECTED_CTR_BY_POSITION = {
    1: 0.30,
    2: 0.15,
    3: 0.10,
    4: 0.07,
    5: 0.05,
    6: 0.04,
    7: 0.03,
    8: 0.025,
    9: 0.02,
    10: 0.018,
    11: 0.010,
    12: 0.009,
    13: 0.008,
    14: 0.007,
    15: 0.006,
    16: 0.005,
    17: 0.004,
    18: 0.003,
    19: 0.003,
    20: 0.002,
}

# Effort scoring for different action types
EFFORT_SCORES = {
    "meta_optimization": 1,
    "title_rewrite": 1,
    "content_refresh": 3,
    "content_expansion": 3,
    "new_content": 5,
    "technical_fix": 2,
    "internal_linking": 2,
}


def _expected_ctr(position: float) -> float:
    """Get expected CTR for a given position, interpolating between known values."""
    pos_int = max(1, min(20, int(round(position))))
    return EXPECTED_CTR_BY_POSITION.get(pos_int, 0.002)


def _expected_page1_ctr(position: float) -> float:
    """Estimate CTR if this result moved to page 1 (position 7-10 range)."""
    # Conservative estimate: if currently at pos 12, could reach ~pos 8
    target_pos = max(5, min(10, position - 5))
    return _expected_ctr(target_pos)


class PrioritiesService:
    """Identify quick-win SEO opportunities and build priority matrices from GSC data."""

    def __init__(self, ai_analyzer: AIAnalyzer, gsc_service=None):
        self.ai = ai_analyzer
        self.gsc = gsc_service

    async def quick_wins(self, site_url: str, days: int = 28) -> dict:
        """Identify quick-win SEO opportunities from GSC data.

        Looks for:
        1. Striking distance keywords (position 11-20) — pages almost on page 1
        2. Low CTR opportunities — high impressions but below-average CTR for position
        3. Declining content — pages losing clicks/impressions over time
        4. Title/description optimization — pages where meta improvements could boost CTR

        Returns dict with striking_distance, low_ctr, declining, meta_opportunities,
        summary, total_opportunities, estimated_click_gain, ai_enhanced.
        """
        if not self.gsc or not self.gsc.is_credentials_available:
            return {
                "error": (
                    "GSC credentials not configured. "
                    "Set GOOGLE_CREDENTIALS_PATH or GSC_OAUTH_CLIENT_SECRETS_FILE in .env "
                    "to enable quick wins analysis."
                ),
                "striking_distance": [],
                "low_ctr": [],
                "declining": [],
                "meta_opportunities": [],
                "summary": "GSC data unavailable — cannot identify quick wins.",
                "total_opportunities": 0,
                "estimated_click_gain": 0,
                "ai_enhanced": False,
            }

        try:
            resolved_url = await self._resolve_site_url(site_url)

            # Fetch current period query+page data
            current_data = await self._fetch_query_page_data(resolved_url, days)
            if not current_data:
                return self._empty_result("No GSC data found for this site.")

            # Fetch previous period for decline detection
            previous_data = await self._fetch_query_page_data(resolved_url, days, offset_days=days)

            # 1. Striking distance: position 11-20
            striking_distance = self._find_striking_distance(current_data)

            # 2. Low CTR: high impressions but CTR below expected for position
            low_ctr = self._find_low_ctr(current_data)

            # 3. Declining: queries losing traffic compared to previous period
            declining = self._find_declining(current_data, previous_data)

            # 4. Meta opportunities: pages in top 10 with poor CTR (likely bad title/desc)
            meta_opportunities = self._find_meta_opportunities(current_data)

            # Estimate total click gain
            estimated_click_gain = self._estimate_click_gain(
                striking_distance, low_ctr, meta_opportunities
            )

            total_opportunities = (
                len(striking_distance) + len(low_ctr) + len(declining) + len(meta_opportunities)
            )

            result = {
                "striking_distance": striking_distance[:20],
                "low_ctr": low_ctr[:20],
                "declining": declining[:20],
                "meta_opportunities": meta_opportunities[:20],
                "summary": self._build_summary(
                    striking_distance,
                    low_ctr,
                    declining,
                    meta_opportunities,
                    estimated_click_gain,
                ),
                "total_opportunities": total_opportunities,
                "estimated_click_gain": estimated_click_gain,
                "ai_enhanced": False,
            }

            # AI enrichment
            if self.ai.ai_available:
                try:
                    ai_insights = await self._ai_enrich_quick_wins(result)
                    result["ai_analysis"] = ai_insights
                    result["ai_enhanced"] = True
                except Exception as e:
                    logger.warning("AI enrichment for quick_wins failed: %s", e)

            return result

        except Exception as e:
            logger.exception("quick_wins failed")
            return {"error": str(e)}

    async def priority_matrix(self, site_url: str, days: int = 28) -> dict:
        """Build an effort/impact priority matrix for SEO actions.

        Categories: quick_wins (low effort, high impact), strategic (high effort, high impact),
        fill_ins (low effort, low impact), deprioritize (high effort, low impact).

        Returns dict with quick_wins, strategic, fill_ins, deprioritize,
        recommended_order, ai_enhanced.
        """
        if not self.gsc or not self.gsc.is_credentials_available:
            return {
                "error": (
                    "GSC credentials not configured. "
                    "Set GOOGLE_CREDENTIALS_PATH or GSC_OAUTH_CLIENT_SECRETS_FILE in .env "
                    "to enable priority matrix."
                ),
                "quick_wins": [],
                "strategic": [],
                "fill_ins": [],
                "deprioritize": [],
                "recommended_order": [],
                "ai_enhanced": False,
            }

        try:
            resolved_url = await self._resolve_site_url(site_url)

            # Get quick wins data first
            current_data = await self._fetch_query_page_data(resolved_url, days)
            if not current_data:
                return {
                    "quick_wins": [],
                    "strategic": [],
                    "fill_ins": [],
                    "deprioritize": [],
                    "recommended_order": [],
                    "ai_enhanced": False,
                    "error": "No GSC data found for this site.",
                }

            previous_data = await self._fetch_query_page_data(resolved_url, days, offset_days=days)

            # Score all opportunities
            opportunities = self._score_opportunities(current_data, previous_data)

            # Classify into quadrants
            # Median thresholds for effort and impact
            effort_threshold = 3
            impact_threshold = 3

            quadrants: dict[str, list] = {
                "quick_wins": [],  # low effort, high impact
                "strategic": [],  # high effort, high impact
                "fill_ins": [],  # low effort, low impact
                "deprioritize": [],  # high effort, low impact
            }

            for opp in opportunities:
                effort = opp["effort_score"]
                impact = opp["impact_score"]

                if effort <= effort_threshold and impact >= impact_threshold:
                    quadrants["quick_wins"].append(opp)
                elif effort > effort_threshold and impact >= impact_threshold:
                    quadrants["strategic"].append(opp)
                elif effort <= effort_threshold and impact < impact_threshold:
                    quadrants["fill_ins"].append(opp)
                else:
                    quadrants["deprioritize"].append(opp)

            # Sort each quadrant by priority (impact desc, effort asc)
            for key in quadrants:
                quadrants[key].sort(
                    key=lambda x: (x["impact_score"], -x["effort_score"]), reverse=True
                )

            # Build recommended order: quick_wins first, then strategic, then fill_ins
            recommended_order = []
            for opp in quadrants["quick_wins"][:10]:
                recommended_order.append(opp["action"])
            for opp in quadrants["strategic"][:5]:
                recommended_order.append(opp["action"])
            for opp in quadrants["fill_ins"][:5]:
                recommended_order.append(opp["action"])

            result = {
                "quick_wins": quadrants["quick_wins"][:15],
                "strategic": quadrants["strategic"][:15],
                "fill_ins": quadrants["fill_ins"][:15],
                "deprioritize": quadrants["deprioritize"][:15],
                "recommended_order": recommended_order,
                "ai_enhanced": False,
            }

            # AI enrichment
            if self.ai.ai_available:
                try:
                    ai_insights = await self._ai_enrich_matrix(result)
                    result["ai_analysis"] = ai_insights
                    result["ai_enhanced"] = True
                except Exception as e:
                    logger.warning("AI enrichment for priority_matrix failed: %s", e)

            return result

        except Exception as e:
            logger.exception("priority_matrix failed")
            return {"error": str(e)}

    # ─── Data fetching ─────────────────────────────────

    async def _resolve_site_url(self, site_url: str) -> str:
        """Resolve site_url to GSC property format."""
        from seo_server.gsc_resolve import resolve_site_url

        return await resolve_site_url(site_url)

    async def _fetch_query_page_data(
        self, site_url: str, days: int, offset_days: int = 0
    ) -> list[dict[str, Any]]:
        """Fetch query+page performance data from GSC."""
        end_date = datetime.now().date() - timedelta(days=offset_days)
        start_date = end_date - timedelta(days=days)

        raw = await self.gsc.get_advanced_search_analytics(
            site_url=site_url,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            dimensions=["query", "page"],
            row_limit=2000,
            sort_by="impressions",
            sort_direction="descending",
        )

        if "error" in raw:
            logger.warning("GSC fetch failed: %s", raw["error"])
            return []

        results = []
        for row in raw.get("rows", []):
            keys = row.get("keys", [])
            if len(keys) >= 2:
                results.append(
                    {
                        "query": keys[0],
                        "page": keys[1],
                        "clicks": row.get("clicks", 0),
                        "impressions": row.get("impressions", 0),
                        "ctr": row.get("ctr", 0),  # Already in % from get_advanced_search_analytics
                        "position": row.get("position", 0),
                    }
                )
        return results

    # ─── Opportunity detection ─────────────────────────

    def _find_striking_distance(self, data: list[dict]) -> list[dict]:
        """Find queries at position 11-20 (striking distance to page 1)."""
        results = []
        for row in data:
            pos = row["position"]
            if 11 <= pos <= 20 and row["impressions"] >= 10:
                potential_ctr = _expected_page1_ctr(pos)
                current_ctr = row["ctr"] / 100  # Convert from % to ratio
                click_potential = int(row["impressions"] * (potential_ctr - max(current_ctr, 0)))
                results.append(
                    {
                        "query": row["query"],
                        "page": row["page"],
                        "position": pos,
                        "impressions": row["impressions"],
                        "current_clicks": row["clicks"],
                        "current_ctr": row["ctr"],
                        "estimated_click_gain": max(0, click_potential),
                        "action": f"Optimize '{row['query']}' on {row['page']} (pos {pos:.1f} → page 1)",
                    }
                )
        results.sort(key=lambda x: x["estimated_click_gain"], reverse=True)
        return results

    def _find_low_ctr(self, data: list[dict]) -> list[dict]:
        """Find pages with CTR below expected for their position."""
        results = []
        for row in data:
            pos = row["position"]
            if pos > 20 or row["impressions"] < 50:
                continue
            expected = _expected_ctr(pos) * 100  # Convert to %
            actual = row["ctr"]
            if actual < expected * 0.5:  # CTR less than half of expected
                gap = expected - actual
                click_potential = int(row["impressions"] * gap / 100)
                results.append(
                    {
                        "query": row["query"],
                        "page": row["page"],
                        "position": pos,
                        "impressions": row["impressions"],
                        "current_ctr": actual,
                        "expected_ctr": round(expected, 2),
                        "ctr_gap": round(gap, 2),
                        "estimated_click_gain": max(0, click_potential),
                        "action": (
                            f"Improve title/description for '{row['query']}' "
                            f"(CTR {actual:.1f}% vs expected {expected:.1f}%)"
                        ),
                    }
                )
        results.sort(key=lambda x: x["estimated_click_gain"], reverse=True)
        return results

    def _find_declining(self, current: list[dict], previous: list[dict]) -> list[dict]:
        """Find queries losing traffic compared to previous period."""
        if not previous:
            return []

        # Index previous data by (query, page)
        prev_index: dict[tuple, dict] = {}
        for row in previous:
            key = (row["query"], row["page"])
            prev_index[key] = row

        results = []
        for row in current:
            key = (row["query"], row["page"])
            prev = prev_index.get(key)
            if not prev:
                continue
            click_diff = row["clicks"] - prev["clicks"]
            imp_diff = row["impressions"] - prev["impressions"]
            # Flag if clicks dropped by >30% and at least 5 clicks lost
            if prev["clicks"] > 0 and click_diff < 0:
                pct_change = (click_diff / prev["clicks"]) * 100
                if pct_change <= -30 and abs(click_diff) >= 5:
                    results.append(
                        {
                            "query": row["query"],
                            "page": row["page"],
                            "position": row["position"],
                            "current_clicks": row["clicks"],
                            "previous_clicks": prev["clicks"],
                            "click_change": click_diff,
                            "click_change_pct": round(pct_change, 1),
                            "impression_change": imp_diff,
                            "action": (
                                f"Investigate decline for '{row['query']}' "
                                f"({click_diff:+d} clicks, {pct_change:.0f}%)"
                            ),
                        }
                    )
        results.sort(key=lambda x: x["click_change"])
        return results

    def _find_meta_opportunities(self, data: list[dict]) -> list[dict]:
        """Find pages in top 10 with poor CTR — likely need title/desc optimization."""
        results = []
        for row in data:
            pos = row["position"]
            if pos > 10 or row["impressions"] < 100:
                continue
            expected = _expected_ctr(pos) * 100
            actual = row["ctr"]
            # Only flag if significantly below expected (less than 60%)
            if actual < expected * 0.6:
                results.append(
                    {
                        "query": row["query"],
                        "page": row["page"],
                        "position": pos,
                        "impressions": row["impressions"],
                        "current_ctr": actual,
                        "expected_ctr": round(expected, 2),
                        "action": (
                            f"Rewrite title/meta for '{row['query']}' at pos {pos:.1f} "
                            f"(CTR {actual:.1f}% vs {expected:.1f}% expected)"
                        ),
                    }
                )
        results.sort(key=lambda x: x["impressions"], reverse=True)
        return results

    # ─── Priority matrix scoring ───────────────────────

    def _score_opportunities(self, current: list[dict], previous: list[dict]) -> list[dict]:
        """Score each opportunity on effort (1-5) and impact (1-5)."""
        opportunities = []

        # Striking distance → effort=3 (content update), impact based on impressions
        for row in current:
            pos = row["position"]
            if 11 <= pos <= 20 and row["impressions"] >= 10:
                impact = self._impact_score(row["impressions"], pos, "striking_distance")
                opportunities.append(
                    {
                        "query": row["query"],
                        "page": row["page"],
                        "type": "striking_distance",
                        "effort_score": 3,
                        "impact_score": impact,
                        "impressions": row["impressions"],
                        "position": pos,
                        "action": (
                            f"Content update: optimize '{row['query']}' "
                            f"(pos {pos:.1f}, {row['impressions']} imp)"
                        ),
                    }
                )

        # Low CTR top 10 → effort=1 (meta optimization), impact based on impressions
        for row in current:
            pos = row["position"]
            if pos > 10 or row["impressions"] < 50:
                continue
            expected = _expected_ctr(pos) * 100
            if row["ctr"] < expected * 0.6:
                impact = self._impact_score(row["impressions"], pos, "meta")
                opportunities.append(
                    {
                        "query": row["query"],
                        "page": row["page"],
                        "type": "meta_optimization",
                        "effort_score": 1,
                        "impact_score": impact,
                        "impressions": row["impressions"],
                        "position": pos,
                        "action": (
                            f"Meta optimization: rewrite title/desc for '{row['query']}' "
                            f"(pos {pos:.1f}, CTR {row['ctr']:.1f}%)"
                        ),
                    }
                )

        # Declining content → effort=3 (content refresh), impact based on lost clicks
        if previous:
            prev_index = {(r["query"], r["page"]): r for r in previous}
            for row in current:
                key = (row["query"], row["page"])
                prev = prev_index.get(key)
                if not prev or prev["clicks"] == 0:
                    continue
                click_diff = row["clicks"] - prev["clicks"]
                pct_change = (click_diff / prev["clicks"]) * 100
                if pct_change <= -30 and abs(click_diff) >= 5:
                    impact = min(5, max(1, int(abs(click_diff) / 10) + 1))
                    opportunities.append(
                        {
                            "query": row["query"],
                            "page": row["page"],
                            "type": "content_refresh",
                            "effort_score": 3,
                            "impact_score": impact,
                            "impressions": row["impressions"],
                            "position": row["position"],
                            "action": (
                                f"Content refresh: '{row['query']}' lost {abs(click_diff)} "
                                f"clicks ({pct_change:.0f}%)"
                            ),
                        }
                    )

        # Deduplicate by (query, page) — keep highest impact
        seen: dict[tuple, int] = {}
        deduped: list[dict] = []
        for opp in opportunities:
            key = (opp["query"], opp["page"])
            if key in seen:
                idx = seen[key]
                if opp["impact_score"] > deduped[idx]["impact_score"]:
                    deduped[idx] = opp
            else:
                seen[key] = len(deduped)
                deduped.append(opp)

        return deduped

    @staticmethod
    def _impact_score(impressions: int, position: float, opp_type: str) -> int:
        """Calculate impact score 1-5 based on impressions and position."""
        # Base score from impressions
        if impressions >= 1000:
            base = 5
        elif impressions >= 500:
            base = 4
        elif impressions >= 200:
            base = 3
        elif impressions >= 50:
            base = 2
        else:
            base = 1

        # Bonus for position (closer to page 1 = more impactful)
        if opp_type == "striking_distance" and position <= 15:
            base = min(5, base + 1)
        elif opp_type == "meta" and position <= 5:
            base = min(5, base + 1)

        return base

    # ─── Helpers ───────────────────────────────────────

    def _estimate_click_gain(
        self,
        striking: list[dict],
        low_ctr: list[dict],
        meta: list[dict],
    ) -> int:
        """Estimate total additional clicks from all opportunities."""
        total = 0
        for item in striking:
            total += item.get("estimated_click_gain", 0)
        for item in low_ctr:
            total += item.get("estimated_click_gain", 0)
        # Meta opportunities overlap with low_ctr, use conservative estimate
        for item in meta:
            total += int(item.get("impressions", 0) * 0.02)
        return total

    def _build_summary(
        self,
        striking: list,
        low_ctr: list,
        declining: list,
        meta: list,
        estimated_gain: int,
    ) -> str:
        """Build a human-readable summary."""
        parts = []
        if striking:
            parts.append(
                f"{len(striking)} striking distance keywords (pos 11-20) ready for page 1 push"
            )
        if low_ctr:
            parts.append(f"{len(low_ctr)} queries with CTR below expected for their position")
        if declining:
            parts.append(f"{len(declining)} declining queries need attention")
        if meta:
            parts.append(f"{len(meta)} pages in top 10 could benefit from title/meta optimization")
        if estimated_gain > 0:
            parts.append(f"Estimated potential click gain: +{estimated_gain} clicks/period")
        return ". ".join(parts) + "." if parts else "No quick wins identified."

    @staticmethod
    def _empty_result(message: str) -> dict:
        """Return an empty result with a message."""
        return {
            "striking_distance": [],
            "low_ctr": [],
            "declining": [],
            "meta_opportunities": [],
            "summary": message,
            "total_opportunities": 0,
            "estimated_click_gain": 0,
            "ai_enhanced": False,
        }

    # ─── AI enrichment ─────────────────────────────────

    async def _ai_enrich_quick_wins(self, data: dict) -> dict:
        """Enrich quick wins results with AI analysis."""
        assert self.ai.llm is not None  # only called when ai_available is True
        prompt = (
            "Analyze these SEO quick win opportunities from Google Search Console data.\n"
            "Provide:\n"
            "1. A prioritized top-5 action list with expected impact\n"
            "2. Common patterns across the opportunities\n"
            "3. Strategic recommendations beyond the immediate quick wins\n\n"
            "Return JSON with keys: top_actions (list), patterns (list), "
            "strategic_recommendations (list), executive_summary (str).\n\n"
            "Data:\n"
        )
        compressed = TokenBudget.prepare_audit_data(data, max_tokens=4000)
        prompt += str(compressed)
        return await self.ai.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)

    async def _ai_enrich_matrix(self, data: dict) -> dict:
        """Enrich priority matrix with AI analysis."""
        assert self.ai.llm is not None  # only called when ai_available is True
        prompt = (
            "Analyze this SEO priority matrix built from Google Search Console data.\n"
            "Provide:\n"
            "1. Validation or adjustment of the effort/impact classifications\n"
            "2. A recommended execution timeline (week 1, 2, 3, 4)\n"
            "3. Dependencies between actions\n"
            "4. Resource allocation advice\n\n"
            "Return JSON with keys: timeline (dict), dependencies (list), "
            "resource_advice (str), executive_summary (str).\n\n"
            "Data:\n"
        )
        compressed = TokenBudget.prepare_audit_data(data, max_tokens=4000)
        prompt += str(compressed)
        return await self.ai.llm.complete_json(SYSTEM_PROMPT_SEO_ANALYST, prompt)
