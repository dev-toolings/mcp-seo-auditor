"""GSC analytics prompts (6-10)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_gsc_review",
    description="Analyze GSC data over the last 3 months — biggest wins, losses, and concerning trends.",
    tags={"analytics", "gsc"},
)
def seo_gsc_review(site_url: str, days: int = 90) -> str:
    return f"""Analyze my GSC data over the last {days} days. What are my biggest wins \
and losses? Identify concerning trends I should address immediately.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days={days}) — recent data
2. gsc_analytics(action="compare", site_url="{site_url}", days={days}) — comparison with previous period
3. Summarize: top 5 gains, top 5 declines, trends to watch"""


@mcp.prompt(
    name="seo_traffic_drop",
    description="Diagnose a traffic drop — identify which pages and keywords lost visibility and why.",
    tags={"analytics", "gsc"},
)
def seo_traffic_drop(site_url: str) -> str:
    return f"""My traffic has dropped recently. Analyze which pages and keywords lost the most \
visibility. What are the likely causes and how should I fix them?

Tools to use:
1. gsc_analytics(action="compare", site_url="{site_url}", days=28) — before/after
2. seo_monitor(action="anomalies", site_url="{site_url}") — anomaly detection
3. gsc_analytics(action="query", site_url="{site_url}", days=28) — declining pages
4. Diagnose: algorithm update, technical issue, cannibalization, outdated content?"""


@mcp.prompt(
    name="seo_ctr_optimization",
    description="Find pages with high impressions but below-average CTR — suggest title and meta improvements.",
    tags={"analytics", "gsc", "content"},
)
def seo_ctr_optimization(site_url: str) -> str:
    return f"""Find pages with high impressions but below-average CTR. \
Suggest title tag and meta description improvements to increase click-through rate.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — impressions + CTR per page
2. Filter: impressions > 100, CTR < site average
3. seo_content(action="meta", target_url=<page>) — generate optimized meta tags for each page
4. Present in a table: page | impressions | current CTR | suggested title | estimated CTR"""


@mcp.prompt(
    name="seo_ranking_stability",
    description="Identify keywords with unstable rankings and recommend stabilization strategies.",
    tags={"analytics", "gsc"},
)
def seo_ranking_stability(site_url: str) -> str:
    return f"""Which of my important keywords have unstable rankings? Identify \
pages with significant fluctuations and recommend stabilization strategies.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=90) — position history
2. gsc_analytics(action="cannibalization", site_url="{site_url}") — check for cannibalization
3. For each unstable keyword: fluctuation range, likely cause, corrective action"""


@mcp.prompt(
    name="seo_intent_alignment",
    description="Check if pages rank for the right queries — identify intent mismatches.",
    tags={"analytics", "gsc", "content"},
)
def seo_intent_alignment(site_url: str) -> str:
    return f"""Check if my pages rank for the right queries. Identify \
misalignments where user intent doesn't match my content.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — queries per page
2. seo_analyze(action="content", urls=[<page>]) — analyze the content of each suspect page
3. For each misalignment: query | current page | actual intent | action (re-optimize, create new page, redirect)"""
