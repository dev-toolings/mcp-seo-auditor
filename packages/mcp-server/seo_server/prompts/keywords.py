"""Keyword research prompts (1-5)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_quick_wins",
    description="Find quick-win keywords ranked 4-20 with high impressions — prioritized by traffic potential.",
    tags={"keywords", "gsc"},
)
def seo_quick_wins(site_url: str) -> str:
    return f"""Find keywords where {site_url} ranks between positions 4-20 \
with high impressions. These are quick-win opportunities. Sort by potential traffic impact.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — get positions + impressions
2. Filter: position between 4 and 20, impressions > average
3. seo_strategy(action="quick_wins", site_url="{site_url}") — prioritize by impact"""


@mcp.prompt(
    name="seo_competitor_keywords",
    description="Find keywords a competitor ranks for but you don't — focused on commercial intent.",
    tags={"keywords", "competitors"},
)
def seo_competitor_keywords(site_url: str, competitor_url: str) -> str:
    return f"""Analyze my competitor {competitor_url} and find keywords they rank for \
but I don't ({site_url}). Focus on commercial-intent keywords \
with reasonable difficulty.

Tools to use:
1. seo_strategy(action="competitor_gap", sitemap_url="{site_url}/sitemap.xml", competitor_urls=["{competitor_url}"])
2. gsc_analytics(action="query", site_url="{site_url}", days=28) — my current positions
3. Cross-reference both to identify commercial-intent gaps"""


@mcp.prompt(
    name="seo_longtail_suggestions",
    description="Suggest long-tail keyword variations from your top 10 keywords with intent and format recommendations.",
    tags={"keywords", "content"},
)
def seo_longtail_suggestions(site_url: str) -> str:
    return f"""Based on my top 10 keywords, suggest long-tail variations \
I should target. Include search intent and content format recommendations.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — top 10 by clicks
2. seo_market(action="insights", keywords=[<top 10>]) — market analysis and variations
3. For each variation, specify: intent (informational/transactional/navigational), recommended format (guide, listicle, comparison...)"""


@mcp.prompt(
    name="seo_keyword_clusters",
    description="Group keywords by search intent and thematic clusters — identify content gaps.",
    tags={"keywords", "strategy"},
)
def seo_keyword_clusters(site_url: str) -> str:
    return f"""Group my keywords by search intent and thematic clusters. \
Identify which clusters need more content and which are well covered.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — all keywords
2. seo_site(action="topical_authority", sitemap_url="{site_url}/sitemap.xml") — existing clusters
3. Cross-reference to identify: well-covered clusters vs thematic gaps"""


@mcp.prompt(
    name="seo_seasonal_keywords",
    description="Identify seasonal keywords to target in the next 3 months with optimal publish dates.",
    tags={"keywords", "strategy"},
)
def seo_seasonal_keywords(site_url: str, niche: str) -> str:
    return f"""Based on my niche ({niche}), identify seasonal keywords I should \
target in the next 3 months. Include recommended publish dates for optimal timing.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=90) — recent history
2. seo_market(action="trends", keywords=[<niche keywords>]) — seasonal trends
3. For each seasonal keyword: estimated volume, peak date, recommended publish date"""
