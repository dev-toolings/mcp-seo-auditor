"""Tests for sitemap parser service."""

from app.services.sitemap_parser import SitemapParserService


class TestSitemapParser:
    """Test sitemap XML parsing."""

    def test_parse_simple_sitemap(self):
        """Test parsing a simple sitemap."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url>
                <loc>https://www.iautos.fr/page1</loc>
                <lastmod>2024-01-15</lastmod>
                <changefreq>weekly</changefreq>
                <priority>0.8</priority>
            </url>
            <url>
                <loc>https://www.iautos.fr/page2</loc>
            </url>
        </urlset>
        """

        parser = SitemapParserService()
        data = parser.parse_xml(xml_content)

        assert len(data.urls) == 2
        assert data.urls[0].loc == "https://www.iautos.fr/page1"
        assert data.urls[0].priority == 0.8
        assert data.urls[1].loc == "https://www.iautos.fr/page2"
        assert data.is_index is False

    def test_parse_sitemap_index(self):
        """Test parsing a sitemap index."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap>
                <loc>https://www.iautos.fr/sitemap1.xml</loc>
            </sitemap>
            <sitemap>
                <loc>https://www.iautos.fr/sitemap2.xml</loc>
            </sitemap>
        </sitemapindex>
        """

        parser = SitemapParserService()
        data = parser.parse_xml(xml_content)

        assert data.is_index is True
        assert len(data.sitemaps) == 2
        assert "sitemap1.xml" in data.sitemaps[0]

    def test_parse_sitemap_with_alternates(self):
        """Test parsing sitemap with hreflang alternates."""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
                xmlns:xhtml="http://www.w3.org/1999/xhtml">
            <url>
                <loc>https://www.iautos.fr/page</loc>
                <xhtml:link rel="alternate" hreflang="fr" href="https://www.iautos.fr/fr/page"/>
                <xhtml:link rel="alternate" hreflang="en" href="https://www.iautos.fr/en/page"/>
            </url>
        </urlset>
        """

        parser = SitemapParserService()
        data = parser.parse_xml(xml_content)

        assert len(data.urls) == 1
        assert "fr" in data.urls[0].alternates
        assert data.urls[0].alternates["fr"] == "https://www.iautos.fr/fr/page"
