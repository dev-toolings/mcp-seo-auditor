"""Competitive analysis prompts (11-15)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_competitor_compare",
    description="Compare your site with a competitor — find their top keywords you're missing.",
    tags={"competitors", "keywords"},
)
def seo_competitor_compare(site_url: str, competitor_url: str) -> str:
    return f"""Compare my site {site_url} with {competitor_url}. Show me their top-performing \
keywords that I'm missing and prioritize them by traffic potential.

Tools to use:
1. seo_strategy(action="competitor_gap", sitemap_url="{site_url}/sitemap.xml", competitor_urls=["{competitor_url}"])
2. gsc_analytics(action="query", site_url="{site_url}", days=28) — my current positions
3. Present: keyword | competitor position | my position (or missing) | estimated volume | priority"""


@mcp.prompt(
    name="seo_competitor_content",
    description="Analyze a competitor's content strategy — topics, formats, and differentiation opportunities.",
    tags={"competitors", "content"},
)
def seo_competitor_content(competitor_url: str) -> str:
    return f"""Analyze the content strategy of {competitor_url}. What topics do they cover? \
Which content formats work best for them? How can I differentiate myself?

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{competitor_url}/sitemap.xml") — page inventory
2. seo_site(action="topical_authority", sitemap_url="{competitor_url}/sitemap.xml") — thematic clusters
3. Summarize: topics covered, dominant formats (guides, listicles, comparisons), differentiation angles"""


@mcp.prompt(
    name="seo_competitor_visibility",
    description="Compare SERP visibility with a competitor on your top keywords — who holds which positions.",
    tags={"competitors", "serp"},
)
def seo_competitor_visibility(site_url: str, competitor_url: str) -> str:
    return f"""Compare my SERP visibility with my competitor {competitor_url} on my top keywords \
({site_url}). Where do they outrank me, and on which queries am I ahead?

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — my top keywords and positions
2. seo_serp(action="live", keywords=[<top keywords>], site_domain=<competitor domain>) — competitor positions on the same keywords
3. For each keyword: my position | competitor position | gap | page to strengthen"""


@mcp.prompt(
    name="seo_serp_features",
    description="Identify which competitors win SERP features and how to capture those positions.",
    tags={"competitors", "serp"},
)
def seo_serp_features(site_url: str) -> str:
    return f"""For my top keywords, which competitors win featured snippets, \
PAA boxes, and other SERP features? How can I capture those positions?

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — my top keywords
2. seo_serp(action="predict", keywords=[<top keywords>]) — SERP feature prediction
3. For each feature: keyword | feature type | current holder | action to capture it"""


@mcp.prompt(
    name="seo_competitor_weaknesses",
    description="Analyze a competitor's SEO weaknesses and exploitable opportunities.",
    tags={"competitors", "strategy"},
)
def seo_competitor_weaknesses(competitor_url: str) -> str:
    return f"""Analyze {competitor_url} and find their SEO weaknesses. Where are they vulnerable? \
What opportunities can I exploit?

Tools to use:
1. seo_analyze(action="technical", urls=["{competitor_url}"]) — technical audit
2. seo_analyze(action="content", urls=["{competitor_url}"]) — content quality
3. seo_site(action="sitemap", sitemap_url="{competitor_url}/sitemap.xml") — site structure
4. Summarize: technical weaknesses, content gaps, exploitable opportunities with priority"""
