"""Technical SEO prompts (21-25)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_technical_audit",
    description="Full technical SEO audit — crawlability, indexation, and Core Web Vitals prioritized by impact.",
    tags={"technical"},
)
def seo_technical_audit(site_url: str) -> str:
    return f"""Perform a technical SEO audit of my site {site_url}. Prioritize issues by their \
impact on rankings. Focus on crawlability, indexation, and Core Web Vitals.

Tools to use:
1. seo_audit(sitemap_url="{site_url}/sitemap.xml") — full AI-enhanced audit
2. seo_analyze(action="technical", urls=["{site_url}"]) — technical details
3. seo_analyze(action="cwv", urls=["{site_url}"]) — Core Web Vitals
4. seo_site(action="robots", sitemap_url="{site_url}/sitemap.xml") — robots.txt analysis
5. Classify: critical (blocking indexation) > important (performance) > minor (optimization)"""


@mcp.prompt(
    name="seo_indexation_status",
    description="Analyze indexation status in GSC — find important unindexed pages and fix blockers.",
    tags={"technical", "gsc"},
)
def seo_indexation_status(site_url: str) -> str:
    return f"""Analyze my indexation status in GSC. Which important pages are not \
indexed? What is blocking them and how do I fix it?

Tools to use:
1. gsc_manage(action="inspect", site_url="{site_url}", urls=[<important pages>]) — indexation status
2. seo_site(action="indexation_leaks", sitemap_url="{site_url}/sitemap.xml") — indexation leaks
3. seo_site(action="robots", sitemap_url="{site_url}/sitemap.xml") — robots directives
4. For each blocked page: URL | blocking reason | corrective action"""


@mcp.prompt(
    name="seo_site_structure",
    description="Evaluate site structure and URL hierarchy — identify deep pages and structural improvements.",
    tags={"technical", "linking"},
)
def seo_site_structure(site_url: str) -> str:
    return f"""Evaluate my site structure and URL hierarchy. Identify pages that are \
too deep and recommend structural improvements.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — sitemap structure
2. seo_site(action="links", sitemap_url="{site_url}/sitemap.xml") — internal link graph
3. Analyze: average depth, pages more than 3 clicks from homepage, thematic silos
4. Recommend: URL restructuring, adding links, missing hub pages"""


@mcp.prompt(
    name="seo_schema_markup",
    description="Recommend schema markup to implement — prioritized by SERP feature impact.",
    tags={"technical", "serp"},
)
def seo_schema_markup(site_url: str) -> str:
    return f"""What schema markup should I implement on my site? Prioritize by potential \
impact on SERP features. Include implementation recommendations.

Tools to use:
1. seo_analyze(action="structured_data", urls=["{site_url}"]) — existing schemas
2. seo_serp(action="predict", keywords=[<top keywords>]) — available SERP features
3. For each schema: type | target pages | targeted SERP feature | implementation snippet | priority"""


@mcp.prompt(
    name="seo_mobile_performance",
    description="Analyze mobile SEO performance — identify mobile-specific issues affecting rankings and UX.",
    tags={"technical"},
)
def seo_mobile_performance(site_url: str) -> str:
    return f"""Analyze my site's mobile SEO performance. Identify mobile-specific issues \
affecting rankings and user experience.

Tools to use:
1. seo_analyze(action="cwv", urls=["{site_url}"]) — Core Web Vitals (mobile)
2. seo_analyze(action="technical", urls=["{site_url}"]) — viewport, responsive, tap targets
3. Classify by impact: LCP > CLS > INP > other mobile issues"""
