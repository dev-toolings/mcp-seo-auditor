"""Topical Authority Map — cluster pages by topic and identify coverage gaps.

Uses TF-IDF vectorization and agglomerative clustering to group pages
by semantic topic, then identifies gaps in topical coverage and suggests
hub-and-spoke content strategies.
"""

import logging
import re
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class TopicalAuthorityService:
    """Map topical authority across a site's content."""

    def __init__(self, gsc_service=None, ai_analyzer=None):
        self.gsc = gsc_service
        self.ai = ai_analyzer

    async def analyze(
        self,
        pages: list[dict],
        gsc_queries: list[dict] | None = None,
        site_url: str | None = None,
        n_clusters: int | None = None,
    ) -> dict[str, Any]:
        """Build topical authority map from crawled pages.

        Args:
            pages: List of dicts with 'url', 'title', 'content' (or 'text')
            gsc_queries: Optional GSC query data for enrichment
            site_url: Optional site URL for GSC data fetch
            n_clusters: Number of topic clusters (auto-detected if None)

        Returns:
            Dict with clusters, gaps, hub-spoke suggestions
        """
        if not pages:
            return {"error": "No pages provided for analysis"}

        # 1. Prepare text corpus
        corpus = []
        urls = []
        for page in pages:
            text = self._extract_text(page)
            if text and len(text) > 50:
                corpus.append(text)
                urls.append(page.get("url", ""))

        if len(corpus) < 3:
            return {
                "error": "Not enough content pages for clustering (minimum 3)",
                "pages_with_content": len(corpus),
            }

        # 2. TF-IDF vectorization
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words="english",
                min_df=2 if len(corpus) > 10 else 1,
                max_df=0.9,
                ngram_range=(1, 2),
            )
            tfidf_matrix = vectorizer.fit_transform(corpus)
            feature_names = vectorizer.get_feature_names_out()
        except ImportError:
            return {
                "error": "scikit-learn not installed. Required for topic clustering.",
            }

        # 3. Agglomerative clustering
        if n_clusters is None:
            # Auto-detect: sqrt(n) clusters, min 2, max 15
            import math

            n_clusters = max(2, min(15, int(math.sqrt(len(corpus)))))

        n_clusters = min(n_clusters, len(corpus))

        try:
            from sklearn.cluster import AgglomerativeClustering

            clustering = AgglomerativeClustering(
                n_clusters=n_clusters,
                metric="cosine",
                linkage="average",
            )
            labels = clustering.fit_predict(tfidf_matrix.toarray())
        except Exception as e:
            return {"error": f"Clustering failed: {e}"}

        # 4. Build clusters with topic labels
        clusters = defaultdict(list)
        for i, label in enumerate(labels):
            clusters[int(label)].append(
                {
                    "url": urls[i],
                    "title": pages[i].get("title", ""),
                }
            )

        # Extract top terms per cluster
        topic_clusters = []
        for cluster_id in sorted(clusters.keys()):
            cluster_pages = clusters[cluster_id]
            cluster_indices = [i for i, lbl in enumerate(labels) if lbl == cluster_id]

            # Get top TF-IDF terms for this cluster
            if cluster_indices:
                cluster_tfidf = tfidf_matrix[cluster_indices].mean(axis=0)
                cluster_array = cluster_tfidf.A1
                top_indices = cluster_array.argsort()[-5:][::-1]
                top_terms = [feature_names[idx] for idx in top_indices]
            else:
                top_terms = []

            topic_clusters.append(
                {
                    "cluster_id": cluster_id,
                    "topic_label": " / ".join(top_terms[:3]),
                    "top_terms": top_terms,
                    "page_count": len(cluster_pages),
                    "pages": cluster_pages,
                }
            )

        # 5. Identify coverage gaps
        gaps = self._identify_gaps(topic_clusters, gsc_queries)

        # 6. Suggest hub-and-spoke structure
        hub_spoke = self._suggest_hub_spoke(topic_clusters)

        # 7. Calculate authority scores per topic
        authority_scores = self._calculate_authority_scores(topic_clusters, gsc_queries)

        result = {
            "total_pages_analyzed": len(corpus),
            "clusters_found": len(topic_clusters),
            "clusters": topic_clusters,
            "coverage_gaps": gaps,
            "hub_spoke_suggestions": hub_spoke,
            "authority_scores": authority_scores,
        }

        # 8. AI enrichment
        if self.ai and self.ai.ai_available:
            try:
                ai_insights = await self.ai.analyze_topical_clusters(result)
                result["ai_insights"] = ai_insights
            except Exception as e:
                logger.warning("AI topical authority enrichment failed: %s", e)

        return result

    def _extract_text(self, page: dict) -> str:
        """Extract text content from a page dict."""
        text = page.get("content", page.get("text", ""))
        title = page.get("title", "")
        h1 = page.get("h1", "")

        # Combine title + h1 + content for better topic signal
        parts = [p for p in [title, h1, text] if p]
        combined = " ".join(parts)

        # Basic cleanup
        combined = re.sub(r"<[^>]+>", " ", combined)  # Strip HTML
        combined = re.sub(r"\s+", " ", combined).strip()

        return combined

    def _identify_gaps(
        self,
        clusters: list[dict],
        gsc_queries: list[dict] | None,
    ) -> list[dict]:
        """Identify topical coverage gaps."""
        gaps = []

        # Gap 1: Small clusters (thin coverage)
        for cluster in clusters:
            if cluster["page_count"] == 1:
                gaps.append(
                    {
                        "type": "thin_coverage",
                        "topic": cluster["topic_label"],
                        "description": (
                            f"Topic '{cluster['topic_label']}' has only 1 page. "
                            "Consider creating supporting content."
                        ),
                        "action": (
                            f"Create 3-5 articles around '{cluster['top_terms'][0]}' "
                            "to build topical depth"
                        ),
                        "priority": "medium",
                    }
                )

        # Gap 2: GSC queries not covered by any cluster
        if gsc_queries:
            all_terms: set[str] = set()
            for cluster in clusters:
                all_terms.update(t.lower() for t in cluster.get("top_terms", []))

            for q in gsc_queries[:50]:
                query = q.get("query", "").lower()
                query_words = set(query.split())
                overlap = query_words & all_terms
                if not overlap and q.get("impressions", 0) > 100:
                    gaps.append(
                        {
                            "type": "uncovered_query",
                            "query": q.get("query", ""),
                            "impressions": q.get("impressions", 0),
                            "description": (
                                f"Query '{q.get('query', '')}' has {q.get('impressions', 0)} "
                                "impressions but no topical cluster covers it"
                            ),
                            "action": "Create dedicated content targeting this query",
                            "priority": "high" if q.get("impressions", 0) > 500 else "medium",
                        }
                    )

        return gaps[:15]

    def _suggest_hub_spoke(self, clusters: list[dict]) -> list[dict]:
        """Suggest hub-and-spoke content structure per topic cluster."""
        suggestions = []

        for cluster in clusters:
            if cluster["page_count"] < 2:
                continue

            # Identify potential hub (shortest URL or most general title)
            hub_candidates = cluster["pages"]
            hub = min(hub_candidates, key=lambda p: len(p.get("url", "")))

            spokes = [p for p in hub_candidates if p != hub]

            suggestions.append(
                {
                    "topic": cluster["topic_label"],
                    "hub_page": hub,
                    "spoke_pages": spokes[:10],
                    "recommendation": (
                        f"Make '{hub.get('url', '')}' the hub page for "
                        f"'{cluster['topic_label']}'. Add internal links from "
                        f"all {len(spokes)} spoke pages back to the hub, and "
                        f"cross-link between related spokes."
                    ),
                }
            )

        return suggestions

    def _calculate_authority_scores(
        self,
        clusters: list[dict],
        gsc_queries: list[dict] | None,
    ) -> list[dict]:
        """Calculate topical authority score per cluster."""
        scores = []

        for cluster in clusters:
            page_count = cluster["page_count"]
            # Base score from depth — "strong" at 50 pages
            depth_score = min(100, page_count * 2)

            # Bonus from GSC data
            gsc_bonus = 0
            if gsc_queries:
                cluster_terms = set(t.lower() for t in cluster.get("top_terms", []))
                matching_impressions = 0
                for q in gsc_queries:
                    query_words = set(q.get("query", "").lower().split())
                    if query_words & cluster_terms:
                        matching_impressions += q.get("impressions", 0)
                if matching_impressions > 1000:
                    gsc_bonus = 30
                elif matching_impressions > 100:
                    gsc_bonus = 15
                elif matching_impressions > 0:
                    gsc_bonus = 5

            authority_score = min(100, depth_score + gsc_bonus)

            scores.append(
                {
                    "topic": cluster["topic_label"],
                    "authority_score": authority_score,
                    "page_count": page_count,
                    "assessment": (
                        "strong"
                        if authority_score >= 70
                        else "moderate"
                        if authority_score >= 40
                        else "weak"
                    ),
                }
            )

        scores.sort(key=lambda x: x["authority_score"], reverse=True)
        return scores
