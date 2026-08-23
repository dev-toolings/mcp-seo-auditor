"""Unit tests for the GEO sub-checkers and the GEOAnalyzer orchestrator.

Locks current behaviour before scoring is tuned. Covers empty / minimal / high /
low / edge inputs for each of the five GEO service classes.
"""

import pytest

from app.services.geo.ai_readability import AIReadabilityChecker
from app.services.geo.citation_readiness import CitationReadinessChecker
from app.services.geo.eeat_detector import EEATDetector
from app.services.geo.faq_completeness import FAQCompletenessChecker
from app.services.geo.geo_analyzer import GEOAnalyzer
from app.services.geo.schema_coverage import SchemaCoverageChecker

# ── Fixtures ────────────────────────────────────────────────────────────────

RICH_HTML = """
<html><head><title>What is GEO?</title></head>
<body><main>
<article>
<h1>What is Generative Engine Optimization?</h1>
<p>Generative Engine Optimization is the practice of optimizing content so that
AI engines such as ChatGPT and Perplexity can cite it. According to a 2025 study,
adding statistics increased citations by 40 percent.</p>
<h2>How does GEO work?</h2>
<p>GEO works by structuring content into self-contained, quotable passages. Our
research found that 73% of cited pages used clear definitions. Updated on 2025-06-01.</p>
<ul><li>Add statistics</li><li>Cite sources</li><li>Use clear headings</li></ul>
<ol><li>First, write a definition.</li><li>Second, add data.</li><li>Third, cite sources.</li></ol>
<p>According to <a href="https://example.org/study">this study</a> and
<a href="https://wikipedia.org/geo">Wikipedia</a>, GEO is now essential.</p>
<p>By Jane Doe, published on 2025-06-01. Based on our experience analyzing 1000 pages.</p>
</article>
</main></body></html>
"""

POOR_HTML = """
<html><body><div>
buy now buy now click here cheap deals everything must go limited time offer act fast
</div></body></html>
"""

FAQ_SCHEMA = [
    {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What is GEO?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "GEO is generative engine optimization.",
                },
            }
        ],
    }
]

ARTICLE_SCHEMA = [
    {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "What is GEO",
        "author": {
            "@type": "Person",
            "name": "Jane Doe",
            "sameAs": "https://www.wikidata.org/wiki/Q1",
        },
        "datePublished": "2025-06-01",
    }
]


# ── AIReadabilityChecker ─────────────────────────────────────────────────────


class TestAIReadability:
    def setup_method(self):
        self.checker = AIReadabilityChecker()

    def test_empty(self):
        r = self.checker.check("", "https://x.com")
        assert r["score"] == 0
        assert r["issues"]

    def test_too_short(self):
        r = self.checker.check("<p>hi</p>", "https://x.com")
        assert r["score"] == 0

    def test_rich_scores_higher_than_poor(self):
        rich = self.checker.check(RICH_HTML, "https://x.com")
        poor = self.checker.check(POOR_HTML, "https://x.com")
        assert 0 <= poor["score"] <= 100
        assert 0 <= rich["score"] <= 100
        assert rich["score"] > poor["score"]
        assert "factual_density" in rich["details"]


# ── SchemaCoverageChecker ────────────────────────────────────────────────────


class TestSchemaCoverage:
    def setup_method(self):
        self.checker = SchemaCoverageChecker()

    def test_no_schema(self):
        r = self.checker.check("https://x.com", [])
        assert r["score"] == 0
        assert any("structured data" in i.lower() for i in r["issues"])

    def test_faq_schema_scores(self):
        r = self.checker.check("https://x.com", FAQ_SCHEMA)
        assert r["score"] > 0
        assert "FAQPage" in r["details"]["schemas_found"]

    def test_entity_clarity_with_sameas(self):
        r = self.checker.check("https://x.com", ARTICLE_SCHEMA)
        # entity_clarity sub-score is exposed and rewards sameAs to authoritative IDs
        assert "entity_clarity" in r["details"]
        assert r["details"]["entity_clarity"]["score"] > 0


# ── EEATDetector ─────────────────────────────────────────────────────────────


class TestEEAT:
    def setup_method(self):
        self.checker = EEATDetector()

    def test_empty(self):
        r = self.checker.check("", "https://x.com")
        assert r["score"] == 0

    def test_rich_has_author_signal(self):
        r = self.checker.check(RICH_HTML, "https://x.com")
        assert 0 <= r["score"] <= 100
        assert "details" in r


# ── FAQCompletenessChecker ───────────────────────────────────────────────────


class TestFAQCompleteness:
    def setup_method(self):
        self.checker = FAQCompletenessChecker()

    def test_empty(self):
        r = self.checker.check("", [])
        assert r["score"] == 0

    def test_with_faq_markup(self):
        r = self.checker.check(RICH_HTML, FAQ_SCHEMA)
        assert r["score"] > 0


# ── CitationReadinessChecker (new 5th dimension) ─────────────────────────────


class TestCitationReadiness:
    def setup_method(self):
        self.checker = CitationReadinessChecker()

    def test_empty(self):
        r = self.checker.check("", "https://x.com")
        assert r["score"] == 0
        assert r["issues"]

    def test_too_short(self):
        r = self.checker.check("<p>hi there friend</p>", "https://x.com")
        assert r["score"] == 0

    def test_rich_scores_higher_than_poor(self):
        rich = self.checker.check(RICH_HTML, "https://x.com")
        poor = self.checker.check(POOR_HTML, "https://x.com")
        assert 0 <= rich["score"] <= 100
        assert 0 <= poor["score"] <= 100
        assert rich["score"] > poor["score"]

    def test_details_expose_subsignals(self):
        r = self.checker.check(RICH_HTML, "https://x.com")
        for key in (
            "stat_density",
            "answer_first",
            "quotable_sentences",
            "cited_sources",
            "freshness",
        ):
            assert key in r["details"]

    def test_cited_sources_detects_outbound_links(self):
        r = self.checker.check(RICH_HTML, "https://x.com")
        assert r["details"]["cited_sources"]["outbound_links"] >= 2


# ── GEOAnalyzer ──────────────────────────────────────────────────────────────


class TestGEOAnalyzer:
    def setup_method(self):
        self.analyzer = GEOAnalyzer(llm_provider=None)

    @pytest.mark.asyncio
    async def test_analyze_single_page(self):
        result = await self.analyzer.analyze_page("https://x.com", RICH_HTML, ARTICLE_SCHEMA)
        assert 0 <= result.geo_score <= 100
        assert result.url == "https://x.com"
        # 5th dimension is wired onto the page result
        assert hasattr(result, "citation_readiness")

    @pytest.mark.asyncio
    async def test_analyze_pages_empty(self):
        report = await self.analyzer.analyze_pages([])
        assert report.geo_score == 0
        assert report.grade == "F"
        assert report.page_results == []

    @pytest.mark.asyncio
    async def test_analyze_pages_handles_bad_input(self):
        # html_content=None must not crash the batch — it degrades to a 0 page result
        report = await self.analyzer.analyze_pages(
            [{"url": "https://x.com", "html_content": None, "structured_data": []}]
        )
        assert len(report.page_results) == 1
        assert 0 <= report.geo_score <= 100

    @pytest.mark.asyncio
    async def test_analyze_pages_good_page(self):
        report = await self.analyzer.analyze_pages(
            [{"url": "https://x.com", "html_content": RICH_HTML, "structured_data": ARTICLE_SCHEMA}]
        )
        assert report.geo_score > 0
        assert report.grade in {"A", "B", "C", "D", "F"}
        assert len(report.dimensions) == 5
        assert {d.name for d in report.dimensions} == {
            "ai_readability",
            "schema_coverage",
            "eeat",
            "faq_completeness",
            "citation_readiness",
        }

    def test_weights_sum_to_one(self):
        assert abs(sum(GEOAnalyzer.WEIGHTS.values()) - 1.0) < 1e-9

    @pytest.mark.parametrize(
        "score,grade",
        [(95, "A"), (85, "B"), (75, "C"), (65, "D"), (10, "F")],
    )
    def test_grade_boundaries(self, score, grade):
        assert self.analyzer._compute_grade(score) == grade
