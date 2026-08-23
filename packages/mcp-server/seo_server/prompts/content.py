"""Content optimization prompts (16-20)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_content_freshness",
    description="Find pages most in need of updates — declining traffic, outdated info, ranking potential.",
    tags={"content", "strategy"},
)
def seo_content_freshness(site_url: str) -> str:
    return f"""Which pages on my site need updates the most? Consider declining traffic, \
outdated information, and ranking potential.

Tools to use:
1. gsc_analytics(action="compare", site_url="{site_url}", days=90) — declining pages
2. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — last modified dates
3. Prioritize: high-traffic pages in decline > pages with untapped potential > outdated pages"""


@mcp.prompt(
    name="seo_cannibalization",
    description="Find pages competing for the same keywords — recommend merge, differentiate, or redirect.",
    tags={"content", "gsc"},
)
def seo_cannibalization(site_url: str) -> str:
    return f"""Find pages on my site that compete for the same keywords. \
Recommend whether to merge, differentiate, or redirect them.

Tools to use:
1. gsc_analytics(action="cannibalization", site_url="{site_url}") — automatic detection
2. For each case: keyword | conflicting pages | respective clicks | recommendation (merge/differentiate/redirect)"""


@mcp.prompt(
    name="seo_thin_content",
    description="Identify thin or underperforming content — recommend expand, consolidate, or remove.",
    tags={"content", "strategy"},
)
def seo_thin_content(site_url: str) -> str:
    return f"""Identify thin or underperforming content on my site. For each, recommend \
whether to expand, consolidate, or remove it.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — full inventory
2. gsc_analytics(action="query", site_url="{site_url}", days=90) — performance per page
3. Filter: pages < 300 words, pages with no traffic in 90 days
4. For each page: URL | word count | traffic | recommendation (expand/consolidate/remove) | justification"""


@mcp.prompt(
    name="seo_featured_snippet",
    description="Analyze the current featured snippet holder and get specific recommendations to win it.",
    tags={"content", "serp"},
)
def seo_featured_snippet(url: str) -> str:
    return f"""For my page {url}, analyze the current featured snippet holder and provide \
specific recommendations to win the snippet.

Tools to use:
1. seo_analyze(action="content", urls=["{url}"]) — analyze current content
2. gsc_analytics(action="query", site_url="<site>") — page keywords
3. seo_serp(action="predict", keywords=[<keywords>]) — current snippet type
4. Recommendations: optimal format (paragraph, list, table), length, structure, markup"""


@mcp.prompt(
    name="seo_content_improve",
    description="Suggest specific improvements for a page — missing subtopics, formatting, media, and stats.",
    tags={"content"},
)
def seo_content_improve(url: str) -> str:
    return f"""For my page {url}, suggest specific improvements: missing subtopics, \
better formatting, additional media, and updated statistics to add.

Tools to use:
1. seo_analyze(action="content", urls=["{url}"]) — full editorial analysis
2. seo_analyze(action="eeat", urls=["{url}"]) — E-E-A-T signals
3. seo_content(action="optimize", content=<content>, target_keyword=<keyword>) — optimized version
4. Present: improvement | estimated impact | effort | priority"""
