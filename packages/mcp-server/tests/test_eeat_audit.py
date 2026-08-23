"""Tests for E-E-A-T audit service."""

import pytest

from app.models.eeat_models import EEATDimension, EEATPageResult, EEATReport
from app.services.eeat_audit_service import EEATAuditService

# ── Model Tests ────────────────────────────────────────────


class TestEEATModels:
    def test_eeat_dimension_creation(self):
        dim = EEATDimension(name="experience", score=75)
        assert dim.name == "experience"
        assert dim.score == 75
        assert dim.signals == []
        assert dim.issues == []

    def test_eeat_dimension_with_signals(self):
        dim = EEATDimension(
            name="expertise",
            score=60,
            signals=["author bio found", "LinkedIn link"],
            issues=["Missing credentials"],
        )
        assert len(dim.signals) == 2
        assert len(dim.issues) == 1

    def test_eeat_page_result(self):
        result = EEATPageResult(
            url="https://www.iautos.fr/page",
            eeat_score=65,
            experience=EEATDimension(name="experience", score=50),
            expertise=EEATDimension(name="expertise", score=70),
            authoritativeness=EEATDimension(name="authoritativeness", score=60),
            trustworthiness=EEATDimension(name="trustworthiness", score=80),
        )
        assert result.eeat_score == 65
        assert result.has_author_info is False

    def test_eeat_report(self):
        report = EEATReport(
            eeat_score=55,
            grade="D",
            experience_score=40,
            expertise_score=60,
            authoritativeness_score=50,
            trustworthiness_score=70,
        )
        assert report.grade == "D"
        assert report.ai_enhanced is False


# ── Service Tests ──────────────────────────────────────────


class TestEEATAuditService:
    def setup_method(self):
        self.service = EEATAuditService()

    def test_find_author_pages(self):
        urls = [
            "https://www.iautos.fr/",
            "https://www.iautos.fr/about",
            "https://www.iautos.fr/team/",
            "https://www.iautos.fr/author/john",
            "https://www.iautos.fr/blog/post-1",
            "https://www.iautos.fr/a-propos",
        ]
        result = self.service._find_author_pages(urls)
        assert len(result) == 4  # about, team, author/john, a-propos

    def test_find_author_pages_empty(self):
        result = self.service._find_author_pages([])
        assert result == []

    def test_has_schema_type_organization(self):
        structured_data = [{"@type": "Organization", "name": "Example Corp"}]
        assert self.service._has_schema_type(structured_data, "Organization")
        assert not self.service._has_schema_type(structured_data, "Person")

    def test_has_schema_type_list(self):
        structured_data = [{"@type": ["Organization", "LocalBusiness"], "name": "Example"}]
        assert self.service._has_schema_type(structured_data, "Organization")
        assert self.service._has_schema_type(structured_data, "LocalBusiness")

    def test_extract_authors_from_jsonld(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "author": {"@type": "Person", "name": "John Doe"}}
        </script>
        </head><body>Content</body></html>
        """
        authors = self.service._extract_authors(html)
        assert "john doe" in authors

    def test_extract_authors_from_html(self):
        html = """
        <html><body>
        <span class="author-name">Jane Smith</span>
        <a rel="author">Bob Johnson</a>
        </body></html>
        """
        authors = self.service._extract_authors(html)
        assert any("jane smith" in a for a in authors)

    def test_extract_authors_empty(self):
        authors = self.service._extract_authors("")
        assert authors == []

    def test_compute_grade(self):
        assert self.service._compute_grade(95) == "A"
        assert self.service._compute_grade(85) == "B"
        assert self.service._compute_grade(75) == "C"
        assert self.service._compute_grade(65) == "D"
        assert self.service._compute_grade(45) == "F"

    @pytest.mark.asyncio
    async def test_audit_empty_pages(self):
        report = await self.service.audit([])
        assert report.eeat_score == 0
        assert report.grade == "F"

    @pytest.mark.asyncio
    async def test_audit_minimal_page(self):
        pages = [
            {
                "url": "https://www.iautos.fr",
                "html_content": """
                <html>
                <head><title>Example</title></head>
                <body>
                <h1>Welcome to Example</h1>
                <p>This is a page with some content that is long enough
                for analysis. We need at least fifty characters of text
                content for the EEAT detector to work properly.</p>
                <a href="/about">About us</a>
                <a href="/contact">Contact</a>
                <a href="https://www.iautos.fr/privacy">Privacy Policy</a>
                </body>
                </html>
                """,
                "structured_data": [],
            }
        ]
        report = await self.service.audit(pages)
        assert 0 <= report.eeat_score <= 100
        assert report.grade in ("A", "B", "C", "D", "F")
        assert len(report.page_results) == 1

    @pytest.mark.asyncio
    async def test_audit_with_strong_eeat(self):
        pages = [
            {
                "url": "https://www.iautos.fr/article",
                "html_content": """
                <html>
                <head>
                <meta property="article:published_time" content="2025-01-01">
                <title>Expert Article</title>
                </head>
                <body>
                <article>
                <div class="author-info">
                    <span class="author-name">Dr. Jane Expert</span>
                    <div class="bio">PhD in Computer Science, 15 years experience</div>
                    <a href="https://linkedin.com/in/jane">LinkedIn</a>
                </div>
                <time datetime="2025-01-01">January 1, 2025</time>
                <h1>Expert Analysis of AI Trends</h1>
                <p>In my experience over the past decade, I have found that
                AI technology has transformed how we work. Our research shows
                significant improvements. We tested multiple approaches
                and our data reveals interesting patterns.</p>
                <p>According to our analysis, the results are clear.
                Based on our findings from surveying 1000 participants,
                the trend is unmistakable.</p>
                <a href="https://scholar.google.com/article">Research Paper</a>
                <a href="https://nature.com/study">Nature Study</a>
                <a href="https://nih.gov/data">NIH Data</a>
                <a href="/about">About Us</a>
                <a href="/contact">Contact</a>
                <a href="/privacy">Privacy Policy</a>
                <a href="/terms">Terms of Service</a>
                <div class="testimonial">4.5/5 stars - 200 reviews</div>
                </article>
                </body>
                </html>
                """,
                "structured_data": [
                    {"@type": "Person", "name": "Dr. Jane Expert"},
                    {
                        "@type": "Organization",
                        "name": "Expert Corp",
                        "sameAs": ["https://linkedin.com/company/expert"],
                    },
                ],
            }
        ]
        report = await self.service.audit(pages)
        # Strong EEAT signals should produce a decent score
        assert report.eeat_score >= 30
        assert report.page_results[0].has_author_info

    def test_cross_page_consistency(self):
        authors = {
            "john doe": ["https://www.iautos.fr/a", "https://www.iautos.fr/b"],
            "john": ["https://www.iautos.fr/c"],
        }
        results = [
            EEATPageResult(
                url="https://www.iautos.fr/a",
                eeat_score=50,
                experience=EEATDimension(name="experience", score=50),
                expertise=EEATDimension(name="expertise", score=50),
                authoritativeness=EEATDimension(name="authoritativeness", score=50),
                trustworthiness=EEATDimension(name="trustworthiness", score=50),
                has_author_info=True,
            ),
            EEATPageResult(
                url="https://www.iautos.fr/b",
                eeat_score=40,
                experience=EEATDimension(name="experience", score=40),
                expertise=EEATDimension(name="expertise", score=40),
                authoritativeness=EEATDimension(name="authoritativeness", score=40),
                trustworthiness=EEATDimension(name="trustworthiness", score=40),
                has_author_info=False,
            ),
        ]
        consistency = self.service._check_cross_page_consistency(authors, results)
        assert consistency["unique_authors"] == 2
        assert consistency["pages_with_author"] == 1
        # Should detect similar names
        assert any("inconsistent" in i.lower() for i in consistency["issues"])
