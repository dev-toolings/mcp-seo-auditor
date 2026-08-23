"""Reporting and planning prompts (46-50)."""

from seo_server.server import mcp


@mcp.prompt(
    name="seo_monthly_report",
    description="Generate a monthly SEO performance report — key metrics, wins, concerns, and next actions.",
    tags={"reporting", "gsc"},
)
def seo_monthly_report(site_url: str) -> str:
    return f"""Generate a monthly SEO performance report. Include key metrics, notable wins, \
areas of concern, and recommended actions for next month.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=30) — monthly metrics
2. gsc_analytics(action="compare", site_url="{site_url}", days=30) — vs previous month
3. seo_monitor(action="anomalies", site_url="{site_url}") — detected anomalies
4. Report structure:
   - KPIs: clicks, impressions, average CTR, average position (+ change)
   - Top 5 gains and declines
   - Detected anomalies
   - Priority actions for the following month"""


@mcp.prompt(
    name="seo_goal_tracking",
    description="Track progress toward a traffic or ranking goal — are you on track and what needs to change?",
    tags={"reporting", "strategy"},
)
def seo_goal_tracking(site_url: str, goal: str) -> str:
    return f"""I want to achieve the following goal: {goal}. Based on current trends, \
am I on track? What needs to change to reach my target?

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=90) — 3-month trends
2. gsc_analytics(action="compare", site_url="{site_url}", days=90) — trajectory
3. Analyze: current growth rate, linear projection, gap vs goal
4. Recommend: levers to activate, remaining quick wins, required efforts"""


@mcp.prompt(
    name="seo_traffic_value",
    description="Estimate organic traffic value based on equivalent PPC costs — show evolution over time.",
    tags={"reporting"},
)
def seo_traffic_value(site_url: str) -> str:
    return f"""Calculate the estimated value of my organic traffic based on equivalent PPC costs. \
Show how it has evolved over time.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=90) — clicks per keyword
2. seo_market(action="insights", keywords=[<top keywords>]) — estimated CPC
3. Calculation: sum(clicks * estimated CPC) per keyword = monthly value
4. Evolution: compare month over month to show the trend"""


@mcp.prompt(
    name="seo_ranking_velocity",
    description="Measure how fast new pages gain rankings — compare to benchmarks and identify factors.",
    tags={"reporting", "strategy"},
)
def seo_ranking_velocity(site_url: str) -> str:
    return f"""How fast are my new pages gaining rankings? Compare to \
benchmarks and identify the factors affecting ranking velocity.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=90) — new pages
2. seo_site(action="sitemap", sitemap_url="{site_url}/sitemap.xml") — publish dates
3. Analyze: average time to first impression, time to top 10, factors (internal linking, content, authority)
4. Compare: fast pages vs slow pages — what makes the difference?"""


@mcp.prompt(
    name="seo_90day_plan",
    description="Create a prioritized 90-day SEO action plan based on current data — highest impact first.",
    tags={"reporting", "strategy"},
)
def seo_90day_plan(site_url: str) -> str:
    return f"""Based on my current data, create a prioritized 90-day SEO action plan. \
Focus on highest-impact activities first.

Tools to use:
1. gsc_analytics(action="query", site_url="{site_url}", days=28) — current state
2. seo_strategy(action="quick_wins", site_url="{site_url}") — quick opportunities
3. seo_strategy(action="priorities", site_url="{site_url}") — effort/impact matrix
4. Plan structure:
   - Days 1-30: quick wins (CTR, title tags, internal links)
   - Days 31-60: content (updates, new articles, clusters)
   - Days 61-90: authority (backlinks, PR, GEO)
   - Tracking KPIs per phase"""
