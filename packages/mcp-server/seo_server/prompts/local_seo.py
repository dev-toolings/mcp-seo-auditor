"""Local SEO prompts (36-40)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_local_opportunities",
    description="Find local search opportunities for a business in a specific area — near me + local intent.",
    tags={"local"},
)
def seo_local_opportunities(site_url: str, location: str) -> str:
    return f"""Find local search opportunities for my business in {location}. \
Include "near me" variations and local-intent keywords.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28, filter_dimension="query", filter_operator="contains", filter_expression="{location}") — local queries
2. seo_market(action="insights", keywords=["<niche> {location}", "<niche> near me"]) — local volume
3. List: local keyword | estimated volume | difficulty | intent | recommended target page"""


@mcp.prompt(
    name="seo_local_competitors",
    description="Compare local SEO presence with top local competitors — local pack rankings.",
    tags={"local", "competitors"},
)
def seo_local_competitors(site_url: str, location: str) -> str:
    return f"""Compare my local SEO presence with the top local competitors in {location}. \
Where am I falling behind in local pack rankings?

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28, filter_dimension="query", filter_operator="contains", filter_expression="{location}")
2. seo_serp(action="live", keywords=["<niche> {location}"]) — current local SERP
3. Analyze: local pack presence, GMB listing, reviews, NAP citations, local pages"""


@mcp.prompt(
    name="seo_local_content",
    description="Recommend local content to create for better visibility in a specific area.",
    tags={"local", "content"},
)
def seo_local_content(site_url: str, location: str) -> str:
    return f"""What local content should I create to improve my visibility in {location}? \
Include location page recommendations.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — existing local pages
2. gsc_analytics(action="query", site_url="{site_url}", days=28, filter_dimension="query", filter_operator="contains", filter_expression="{location}")
3. Recommend: location pages, local guides, local testimonials, events
4. For each content piece: topic | format | target keywords | suggested URL"""


@mcp.prompt(
    name="seo_reviews_audit",
    description="Analyze review profile compared to competitors — improve quantity and quality for local rankings.",
    tags={"local"},
)
def seo_reviews_audit(site_url: str) -> str:
    return f"""Analyze my review profile compared to competitors. How can I improve the \
quantity and quality of my reviews for better local rankings?

Tools to use:
1. seo_analyze(action="structured_data", urls=["{site_url}"]) — Review/AggregateRating schema
2. Analyze: review count, average rating, frequency, review responses
3. Strategies: post-purchase email, QR code, incentives, negative review management"""


@mcp.prompt(
    name="seo_multi_location",
    description="Audit location pages for multi-location businesses — avoid duplicate content while targeting each area.",
    tags={"local", "content"},
)
def seo_multi_location(site_url: str) -> str:
    return f"""I have multiple locations. Audit my location pages and recommend \
improvements to avoid duplicate content while targeting each area.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — location pages
2. seo_site(action="cannibalization", sitemap_url="{site_url}/sitemap.xml") — duplicate content
3. For each location page: unique content (%) | duplicated elements | improvements (local testimonials, team, photos)"""
