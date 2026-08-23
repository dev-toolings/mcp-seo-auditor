"""Migration Planner — URL mapping, redirect rules, and traffic impact prediction.

Given old and new sitemaps, generates a migration plan with URL mapping,
redirect rules, chain detection, and traffic impact estimation.
"""

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class MigrationPlannerService:
    """Plan site migrations with URL mapping and impact prediction."""

    def __init__(self, sitemap_parser=None, gsc_service=None):
        self.sitemap_parser = sitemap_parser
        self.gsc = gsc_service

    async def plan(
        self,
        old_sitemap_url: str,
        new_sitemap_url: str,
        site_url: str | None = None,
    ) -> dict[str, Any]:
        """Generate a migration plan.

        1. Parse both sitemaps
        2. Match old URLs to new URLs
        3. Detect removed/added URLs
        4. Generate redirect rules
        5. Detect potential redirect chains
        6. Estimate traffic impact (if GSC available)
        """
        if not self.sitemap_parser:
            return {"error": "Sitemap parser not available"}

        # 1. Parse sitemaps
        try:
            old_data = await self.sitemap_parser.fetch_and_parse(old_sitemap_url)
            new_data = await self.sitemap_parser.fetch_and_parse(new_sitemap_url)
        except Exception as e:
            return {"error": f"Failed to parse sitemaps: {e}"}

        old_urls = {u.loc for u in old_data.urls}
        new_urls = {u.loc for u in new_data.urls}

        # 2. Categorize URLs
        unchanged = old_urls & new_urls
        removed = old_urls - new_urls
        added = new_urls - old_urls

        # 3. Map removed URLs to best new URL matches
        mappings = []
        unmatched = []

        for old_url in sorted(removed):
            best_match = self._find_best_match(old_url, list(added))
            if best_match:
                mappings.append(
                    {
                        "old_url": old_url,
                        "new_url": best_match["url"],
                        "confidence": best_match["confidence"],
                        "match_type": best_match["match_type"],
                    }
                )
            else:
                unmatched.append(old_url)

        # 4. Generate redirect rules
        redirects = self._generate_redirect_rules(mappings)

        # 5. Detect potential redirect chains
        chains = self._detect_chains(mappings)

        # 6. Traffic impact estimation
        impact = {}
        if self.gsc and site_url and self.gsc.is_credentials_available:
            impact = await self._estimate_traffic_impact(removed, unmatched, site_url)

        return {
            "summary": {
                "old_sitemap": old_sitemap_url,
                "new_sitemap": new_sitemap_url,
                "old_url_count": len(old_urls),
                "new_url_count": len(new_urls),
                "unchanged": len(unchanged),
                "removed": len(removed),
                "added": len(added),
                "mapped": len(mappings),
                "unmatched": len(unmatched),
            },
            "url_mappings": mappings[:100],
            "unmatched_urls": unmatched[:50],
            "redirect_rules": redirects,
            "redirect_chains": chains,
            "new_urls": sorted(added)[:50],
            "traffic_impact": impact,
            "recommendations": self._generate_recommendations(mappings, unmatched, chains, impact),
        }

    def _find_best_match(self, old_url: str, candidates: list[str]) -> Optional[dict]:
        """Find the best matching new URL for an old URL."""
        if not candidates:
            return None

        old_parsed = urlparse(old_url)
        old_path = old_parsed.path.rstrip("/")
        old_segments = [s for s in old_path.split("/") if s]

        best_score = 0.0
        best_url = None
        best_type = "fuzzy"

        for new_url in candidates:
            new_parsed = urlparse(new_url)
            new_path = new_parsed.path.rstrip("/")
            new_segments = [s for s in new_path.split("/") if s]

            # Exact path match (different domain)
            if old_path == new_path:
                return {
                    "url": new_url,
                    "confidence": 1.0,
                    "match_type": "exact_path",
                }

            # Slug match (last segment)
            if old_segments and new_segments:
                if old_segments[-1] == new_segments[-1]:
                    return {
                        "url": new_url,
                        "confidence": 0.9,
                        "match_type": "slug_match",
                    }

            # Fuzzy path similarity
            similarity = SequenceMatcher(None, old_path, new_path).ratio()

            if similarity > best_score:
                best_score = similarity
                best_url = new_url

        if best_score >= 0.6 and best_url:
            return {
                "url": best_url,
                "confidence": round(best_score, 2),
                "match_type": best_type,
            }

        return None

    def _generate_redirect_rules(self, mappings: list[dict]) -> dict[str, object]:
        """Generate redirect configuration for Apache and Nginx."""
        apache_rules = []
        nginx_rules = []

        for mapping in mappings:
            old_path = urlparse(mapping["old_url"]).path
            new_url = mapping["new_url"]

            apache_rules.append(f"Redirect 301 {old_path} {new_url}")
            nginx_rules.append(f"rewrite ^{re.escape(old_path)}$ {new_url} permanent;")

        return {
            "apache_htaccess": apache_rules[:200],
            "nginx_conf": nginx_rules[:200],
            "total_rules": len(mappings),
        }

    def _detect_chains(self, mappings: list[dict]) -> list[dict]:
        """Detect potential redirect chains (A -> B -> C)."""
        chains = []
        redirect_map = {m["old_url"]: m["new_url"] for m in mappings}

        for old_url, new_url in redirect_map.items():
            chain = [old_url, new_url]
            current = new_url
            while current in redirect_map:
                current = redirect_map[current]
                chain.append(current)
                if len(chain) > 5:
                    break

            if len(chain) > 2:
                chains.append(
                    {
                        "chain": chain,
                        "length": len(chain) - 1,
                        "recommendation": (
                            f"Redirect chain detected ({len(chain) - 1} hops). "
                            f"Update {old_url} to redirect directly to {chain[-1]}"
                        ),
                    }
                )

        return chains

    async def _estimate_traffic_impact(
        self,
        removed_urls: set[str],
        unmatched_urls: list[str],
        site_url: str,
    ) -> dict:
        """Estimate traffic impact of the migration using GSC data."""
        try:
            top_pages = await self.gsc.get_top_pages(days=28, limit=200, site_url=site_url)
        except Exception as e:
            return {"error": f"Failed to fetch GSC data: {e}"}

        page_traffic = {p.url: p for p in top_pages}

        at_risk_clicks = 0
        at_risk_impressions = 0
        at_risk_pages = []

        for url in unmatched_urls:
            if url in page_traffic:
                perf = page_traffic[url]
                at_risk_clicks += perf.clicks
                at_risk_impressions += perf.impressions
                at_risk_pages.append(
                    {
                        "url": url,
                        "clicks": perf.clicks,
                        "impressions": perf.impressions,
                        "position": round(perf.position, 1),
                    }
                )

        # Sort by clicks descending
        at_risk_pages.sort(key=lambda x: x["clicks"], reverse=True)

        total_clicks = sum(p.clicks for p in top_pages)
        impact_pct = round(at_risk_clicks / max(total_clicks, 1) * 100, 1) if total_clicks else 0

        return {
            "at_risk_clicks": at_risk_clicks,
            "at_risk_impressions": at_risk_impressions,
            "at_risk_pages": at_risk_pages[:20],
            "total_site_clicks": total_clicks,
            "traffic_impact_percentage": impact_pct,
            "risk_level": (
                "critical"
                if impact_pct > 20
                else "high"
                if impact_pct > 10
                else "medium"
                if impact_pct > 5
                else "low"
            ),
        }

    def _generate_recommendations(
        self,
        mappings: list[dict],
        unmatched: list[str],
        chains: list[dict],
        impact: dict,
    ) -> list[str]:
        """Generate migration recommendations."""
        recs = []

        if unmatched:
            recs.append(
                f"{len(unmatched)} URLs have no redirect target. "
                "Create 301 redirects or serve 410 Gone for removed content."
            )

        low_confidence = [m for m in mappings if m["confidence"] < 0.7]
        if low_confidence:
            recs.append(
                f"{len(low_confidence)} URL mappings have low confidence. "
                "Manually verify these redirect targets before deployment."
            )

        if chains:
            recs.append(
                f"{len(chains)} redirect chains detected. "
                "Update to point directly to final destination."
            )

        risk = impact.get("risk_level", "")
        if risk in ("critical", "high"):
            recs.append(
                f"Traffic impact is {risk}: {impact.get('traffic_impact_percentage', 0)}% "
                "of clicks at risk. Prioritize redirect mapping for high-traffic pages."
            )

        recs.append(
            "After migration: monitor GSC for 404 errors, "
            "submit updated sitemap, and track indexing status."
        )

        return recs
