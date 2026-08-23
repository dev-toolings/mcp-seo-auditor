"""E-commerce SEO prompts (41-45)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_product_pages",
    description="Audit product pages for SEO — titles, descriptions, schema, and unique content prioritized by revenue.",
    tags={"ecommerce"},
)
def seo_product_pages(site_url: str) -> str:
    return f"""Audit my product pages for SEO. Check titles, descriptions, schema markup, \
and unique content. Prioritize fixes by revenue impact.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — product pages
2. seo_analyze(action="structured_data", urls=[<product page>]) — Product schema
3. seo_analyze(action="content", urls=[<product page>]) — content quality
4. For each product: URL | title | schema OK/KO | unique content | revenue priority"""


@mcp.prompt(
    name="seo_category_pages",
    description="Analyze category pages — optimization for head terms, content and structure improvements.",
    tags={"ecommerce", "content"},
)
def seo_category_pages(site_url: str) -> str:
    return f"""Analyze my category pages. Are they properly optimized for head terms? \
Suggest content and structure improvements.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — category pages
2. seo_analyze(action="content", urls=[<category>]) — editorial content
3. gsc_analytics(action="query", site_url="{site_url}", days=28) — queries per category
4. Recommend: editorial text, FAQ, internal links, SEO-friendly filters, pagination"""


@mcp.prompt(
    name="seo_faceted_navigation",
    description="Review faceted navigation setup — identify crawl budget waste and duplicate content from filters.",
    tags={"ecommerce", "technical"},
)
def seo_faceted_navigation(site_url: str) -> str:
    return f"""Review my faceted navigation setup. Identify any crawl budget waste \
or duplicate content issues from filters and sorting options.

Tools to use:
1. seo_site(action="robots", sitemap_url="{site_url}/sitemap.xml") — robots.txt rules for facets
2. seo_site(action="indexation_leaks", sitemap_url="{site_url}/sitemap.xml") — parasitic indexed URLs
3. Analyze: indexed URL parameters, canonicals, noindex, wasted crawl budget
4. Recommend: robots.txt rules, canonicals, meta robots, URL parameter handling in GSC"""


@mcp.prompt(
    name="seo_product_schema",
    description="Audit product schema markup — missing properties and rich result improvements.",
    tags={"ecommerce", "technical"},
)
def seo_product_schema(site_url: str) -> str:
    return f"""Audit my product schema markup. Are important properties missing? How \
can I improve my product rich results?

Tools to use:
1. seo_analyze(action="structured_data", urls=["{site_url}"]) — current schemas
2. Check: name, image, description, offers (price, availability, currency), aggregateRating, review, brand, sku
3. For each missing property: impact on rich results | implementation snippet"""


@mcp.prompt(
    name="seo_out_of_stock",
    description="Best practices for handling out-of-stock product pages — maintain SEO value.",
    tags={"ecommerce", "strategy"},
)
def seo_out_of_stock(site_url: str) -> str:
    return f"""How should I handle out-of-stock product pages? Analyze the current \
handling and recommend best practices to maintain SEO value.

Tools to use:
1. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — product pages
2. seo_analyze(action="technical", urls=[<out-of-stock page>]) — status code, redirects, canonical
3. Recommend based on case: keep with "unavailable" + alternatives, 301 redirect to category, \
redirect to similar product, soft 404 if permanently discontinued"""
