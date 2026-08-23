"""Internal linking prompts (26-30)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_internal_links_audit",
    description="Audit internal link structure — find important pages lacking links and redistribute equity.",
    tags={"linking"},
)
def seo_internal_links_audit(site_url: str) -> str:
    return f"""Analyze my internal link structure. Which important pages lack \
internal links? Which pages have too much link equity that should be redistributed?

Tools to use:
1. seo_site(action="links", sitemap_url="{site_url}/sitemap.xml") — full internal link graph
2. gsc_analytics(action="query", site_url="{site_url}", days=28) — pages by performance
3. Cross-reference: high SEO-potential pages with few internal links vs over-linked pages"""


@mcp.prompt(
    name="seo_orphan_pages",
    description="Find orphan pages with no internal links pointing to them — recommend linking sources.",
    tags={"linking"},
)
def seo_orphan_pages(site_url: str) -> str:
    return f"""Find orphan pages on my site that have no internal links pointing to \
them. Recommend which pages should link to each orphan.

Tools to use:
1. seo_site(action="links", sitemap_url="{site_url}/sitemap.xml") — pages with no inbound links
2. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — all known pages
3. For each orphan: URL | topic | recommended source pages | suggested anchor text"""


@mcp.prompt(
    name="seo_hub_spoke",
    description="Create a hub-and-spoke internal linking plan for a pillar page.",
    tags={"linking", "content"},
)
def seo_hub_spoke(url: str) -> str:
    return f"""For my pillar page {url}, identify all related content that should link to \
and from it. Create a hub-and-spoke linking plan.

Tools to use:
1. seo_analyze(action="content", urls=["{url}"]) — pillar page topic and keywords
2. seo_site(action="topical_authority", sitemap_url="<site>/sitemap.xml") — pages in the same cluster
3. Plan: pillar page -> [spokes] with link direction, anchor text, and insertion context"""


@mcp.prompt(
    name="seo_anchor_text_review",
    description="Review internal link anchor texts — identify over-optimized or generic anchors.",
    tags={"linking"},
)
def seo_anchor_text_review(site_url: str) -> str:
    return f"""Review the anchor texts of my internal links. Identify \
over-optimized or generic anchors and recommend improvements.

Tools to use:
1. seo_site(action="links", sitemap_url="{site_url}/sitemap.xml") — all links with anchors
2. Analyze: anchor distribution (exact match, partial, generic, branded)
3. Flag: "click here" / "learn more" (generic), keyword stuffing (over-optimized)
4. Suggest natural and descriptive anchors for each case"""


@mcp.prompt(
    name="seo_link_equity_map",
    description="Map how link equity flows through the site — ensure money pages receive enough equity.",
    tags={"linking", "strategy"},
)
def seo_link_equity_map(site_url: str) -> str:
    return f"""Map how link equity flows through my site. Which pages \
receive the most internal links? Are my money pages receiving enough link equity?

Tools to use:
1. seo_site(action="links", sitemap_url="{site_url}/sitemap.xml") — link graph
2. gsc_analytics(action="query", site_url="{site_url}", days=28) — pages by revenue/conversions
3. Cross-reference: money pages (high commercial potential) vs internal links received
4. Recommend: equity redistribution via links from high-authority pages"""
