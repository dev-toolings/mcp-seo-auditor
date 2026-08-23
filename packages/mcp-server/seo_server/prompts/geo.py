"""AI search / GEO readiness prompts (31-35)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_ai_readiness",
    description="Analyze content for AI search optimization — is it structured to be cited by AI assistants?",
    tags={"geo", "content"},
)
def seo_ai_readiness(url: str) -> str:
    return f"""Analyze my content for AI search optimization. Is my content structured \
to be easily cited by AI assistants? What improvements would help?

Tools to use:
1. seo_geo(urls=["{url}"]) — full GEO audit (E-E-A-T, FAQ, schema, AI readability)
2. seo_analyze(action="structured_data", urls=["{url}"]) — structured data
3. seo_analyze(action="eeat", urls=["{url}"]) — E-E-A-T signals
4. Recommendations: structure, citations, verifiable facts, schema markup, Q&A format"""


@mcp.prompt(
    name="seo_entity_associations",
    description="Identify which entities your site should be associated with for AI search visibility.",
    tags={"geo", "strategy"},
)
def seo_entity_associations(site_url: str) -> str:
    return f"""Which entities should my site be associated with? How can I strengthen \
these entity connections for better AI search visibility?

Tools to use:
1. seo_site(action="topical_authority", sitemap_url="{site_url}/sitemap.xml") — thematic clusters
2. seo_geo(urls=["{site_url}"]) — current entity associations
3. Identify: key domain entities, missing entities, strengthening strategies (schema, content, links)"""


@mcp.prompt(
    name="seo_ai_citation_potential",
    description="Identify content with highest potential for AI assistant citations and how to improve it.",
    tags={"geo", "content"},
)
def seo_ai_citation_potential(site_url: str) -> str:
    return f"""Which content on my site has the highest potential to be cited by AI assistants? \
What makes content citation-worthy and how can I improve mine?

Tools to use:
1. gsc_analytics(action="ai_queries", site_url="{site_url}") — AI engine-related queries
2. gsc_analytics(action="ai_traffic", site_url="{site_url}") — existing AI traffic
3. seo_geo(urls=[<top pages>]) — AI citability score
4. Criteria: unique facts, proprietary data, demonstrated expertise, extractable format"""


@mcp.prompt(
    name="seo_faq_ai_optimization",
    description="Optimize FAQ sections for AI search — rewrite for direct, factual, extractable answers.",
    tags={"geo", "content"},
)
def seo_faq_ai_optimization(url: str) -> str:
    return f"""Optimize my FAQ section for AI search. Rewrite answers to make them \
more direct, factual, and easily extractable by AI systems.

Tools to use:
1. seo_analyze(action="content", urls=["{url}"]) — current FAQ content
2. seo_geo(urls=["{url}"]) — AI readability score
3. For each Q&A: current version | AI-optimized version | improvements (conciseness, facts, structure)"""


@mcp.prompt(
    name="seo_brand_mentions",
    description="Strategies to increase brand mentions on the web for better AI search visibility.",
    tags={"geo", "strategy"},
)
def seo_brand_mentions(site_url: str, brand: str) -> str:
    return f"""How can I increase mentions of my brand {brand} on the web to improve \
AI search visibility? Suggest PR and content strategies.

Tools to use:
1. seo_geo(urls=["{site_url}"]) — current AI visibility
2. seo_site(action="topical_authority", sitemap_url="{site_url}/sitemap.xml") — topical authority
3. Strategies: guest posts, original studies, expert quotes, press releases, partnerships
4. For each strategy: effort | impact | timeline | concrete actions"""
