"""Prompt templates for AI-powered SEO analysis.

Expert-level prompts with persona, scoring calibration, site-type context,
and few-shot examples for consistent, actionable LLM output.
"""

import json

# ── Expert System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT_SEO_ANALYST = """\
You are a world-class SEO strategist and former Google Search Quality team member \
with 18+ years of hands-on technical SEO experience. You have consulted for \
Fortune 500 companies including Amazon, Shopify, and HubSpot, and you regularly \
speak at conferences like BrightonSEO, SMX, and SearchLove.

Your expertise spans:
- Technical SEO (crawlability, indexability, site architecture, Core Web Vitals, JS rendering)
- On-page SEO (content quality, keyword optimization, meta tags, heading hierarchy, internal linking)
- Off-page SEO (link profile analysis, digital PR strategy, brand signals)
- Structured data and Schema.org markup (JSON-LD validation, rich result eligibility)
- Generative Engine Optimization (GEO) - optimizing for AI-powered search engines \
(ChatGPT, Perplexity, Google AI Overviews, Bing Copilot)
- E-E-A-T signals (Experience, Expertise, Authoritativeness, Trustworthiness)

## Prioritization Framework

Rank every recommendation using: Impact x Probability / Effort.

## Scoring Calibration

Use this scale consistently across all audits:
- 90-100: Top 5% of the web (Amazon, HubSpot-level optimization)
- 80-89: Professional SEO team in place, well-optimized site
- 70-79: Competent SEO, but missing advanced optimizations
- 60-69: Basic DIY SEO, significant gaps remain
- 50-59: Major problems actively affecting organic traffic
- Below 50: Critical issues, likely losing significant traffic daily

## Impact Levels

- critical: Direct traffic loss risk, fix within 24-48 hours
- high: 20%+ potential traffic impact, fix within 1-2 weeks
- medium: 5-20% impact potential, fix within 1 month
- low: <5% impact, fix within the quarter

## Effort Levels

- minimal: <2 hours of developer time
- low: 2-8 hours of developer time
- medium: 1-3 days of developer time
- high: 1-2 weeks of developer time
- major: >2 weeks of developer time

## Output Rules

- Always respond in the same language as the analyzed content.
- Always output valid JSON.
- Quantify impact whenever possible (estimated traffic gain, revenue impact).
- Explain the "why" behind every recommendation with technical rationale.
- Never give generic advice; tailor every recommendation to the specific data provided."""


# ── Site Type Contexts ────────────────────────────────────────────────

SITE_TYPE_CONTEXTS = {
    "ecommerce": {
        "priorities": (
            "Product page optimization, category structure, faceted navigation, "
            "product schema markup, inventory management for SEO, breadcrumb navigation, "
            "review aggregation, price competitiveness signals"
        ),
        "key_metrics": (
            "Revenue per organic visit, product page indexation rate, category CTR, "
            "conversion rate by landing page, average order value from organic traffic"
        ),
        "common_issues": (
            "Thin product descriptions, duplicate content from variants/colors/sizes, "
            "faceted navigation creating duplicate URLs, missing product schema, "
            "out-of-stock pages returning 200, pagination issues, "
            "cannibalization between category and product pages"
        ),
    },
    "saas": {
        "priorities": (
            "Landing page optimization, feature pages, comparison pages, "
            "integration pages, pricing page SEO, documentation indexation, "
            "programmatic SEO for use-case pages, trial/demo conversion funnels"
        ),
        "key_metrics": (
            "Trial signups from organic, MQL from organic, feature page engagement, "
            "documentation search visibility, branded vs non-branded ratio"
        ),
        "common_issues": (
            "Thin feature pages, missing comparison/alternative pages, "
            "documentation not indexed or poorly structured, JS-rendered content "
            "not crawlable, poor internal linking between marketing and docs, "
            "login/dashboard pages wasting crawl budget"
        ),
    },
    "blog": {
        "priorities": (
            "Content freshness, topical authority clustering, author E-E-A-T signals, "
            "internal linking between related articles, content decay detection, "
            "featured snippet optimization, FAQ schema for informational queries"
        ),
        "key_metrics": (
            "Organic traffic per article, content decay rate, topical coverage score, "
            "featured snippet capture rate, average time on page, pages per session"
        ),
        "common_issues": (
            "Content cannibalization between similar articles, thin content, "
            "missing author pages or weak author bios, no content update strategy, "
            "poor heading hierarchy, missing FAQ schema, images without alt text, "
            "no topical clustering strategy"
        ),
    },
    "local": {
        "priorities": (
            "Google Business Profile optimization, local schema markup (LocalBusiness), "
            "NAP consistency, local landing pages, review signals, "
            "local keyword targeting, service-area pages"
        ),
        "key_metrics": (
            "Local pack visibility, Google Business Profile impressions, "
            "direction requests, phone calls from organic, local CTR, "
            "review count and average rating"
        ),
        "common_issues": (
            "Inconsistent NAP across directories, missing LocalBusiness schema, "
            "duplicate location pages, no location-specific content, "
            "missing review markup, poor mobile experience, "
            "no service-area page strategy"
        ),
    },
    "news": {
        "priorities": (
            "Google News eligibility, article schema markup, publication speed, "
            "AMP or fast-loading pages, topical authority, author credibility, "
            "Google Discover optimization, real-time indexing"
        ),
        "key_metrics": (
            "Google News impressions, Discover traffic, indexing speed, "
            "article CTR, top stories appearances, AMP cache hit rate"
        ),
        "common_issues": (
            "Slow indexing of breaking news, missing NewsArticle schema, "
            "poor headline optimization, duplicate syndicated content, "
            "missing author pages, no breadcrumb navigation, "
            "images not optimized for Discover, paywall implementation issues"
        ),
    },
    "marketplace": {
        "priorities": (
            "Listing page optimization, category taxonomy, user-generated content SEO, "
            "seller/provider pages, search result pages, filter URL management, "
            "review aggregation schema, location-based landing pages"
        ),
        "key_metrics": (
            "Indexed listing pages ratio, category page organic traffic, "
            "listing-to-conversion rate, UGC contribution to indexation, "
            "long-tail keyword coverage from listings"
        ),
        "common_issues": (
            "Thin listing pages with minimal content, duplicate listings, "
            "search result pages being indexed (crawl budget waste), "
            "filter combinations creating millions of URLs, "
            "user-generated content quality issues, missing review schema, "
            "expired listings returning 200 instead of 410"
        ),
    },
}


def _inject_site_type_context(site_type: str | None) -> str:
    """Build a site-type context block if a recognized type is provided."""
    if not site_type or site_type not in SITE_TYPE_CONTEXTS:
        return ""
    ctx = SITE_TYPE_CONTEXTS[site_type]
    return (
        f"\n\nSITE TYPE CONTEXT ({site_type.upper()}):\n"
        f"- Key priorities: {ctx['priorities']}\n"
        f"- Key metrics to evaluate: {ctx['key_metrics']}\n"
        f"- Common issues to check: {ctx['common_issues']}\n"
    )


# ── Prompt Builders ───────────────────────────────────────────────────


def build_full_audit_prompt(audit_data: dict, site_type: str | None = None) -> str:
    """Build a prompt for complete SEO audit analysis with few-shot example."""
    site_ctx = _inject_site_type_context(site_type)

    gsc_instruction = ""
    if audit_data.get("gsc_performance"):
        gsc_instruction = """
GSC DATA AVAILABLE: The audit includes Google Search Console performance data (clicks, impressions, CTR, positions).
- Correlate technical issues with real traffic impact. Example: "This page has thin content AND 800 impressions but 0.5% CTR → fixing the title tag could generate +40 clicks/month."
- Include a "gsc_correlated_issues" array in your response: each item should link a technical issue to its traffic impact using GSC metrics.
- Use low_ctr_opportunities to identify pages where title/description improvements would have the highest ROI.
"""

    return f"""Analyze this SEO audit data and provide a comprehensive analysis.
{site_ctx}{gsc_instruction}
AUDIT DATA:
{json.dumps(audit_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "executive_summary": A concise 2-3 paragraph summary of findings
- "overall_score": Integer 0-100 overall SEO health score (use the scoring calibration from your instructions)
- "dimension_scores": Object with scores (0-100) for: technical, content, links, schema, performance, geo
- "prioritized_recommendations": Array of objects (see example below)
- "quick_wins": Array of easy improvements with high impact
- "strategic_insights": Array of longer-term strategic observations
- "risk_factors": Array of critical risks that need immediate attention
- "gsc_correlated_issues": (if GSC data present) Array of technical issues correlated with traffic impact

EXAMPLE RECOMMENDATION (follow this exact structure for each item in prioritized_recommendations):
{{
  "title": "Add missing hreflang tags for multi-language pages",
  "description": "12 pages serve content in both English and French but lack hreflang annotations. This causes Google to pick the wrong language version for 35% of queries, splitting ranking signals between duplicates.",
  "impact": "high",
  "effort": "low",
  "priority_score": 85,
  "category": "technical",
  "timeline": "short-term",
  "rationale": "Hreflang issues directly cause ranking signal dilution across language variants. Fixing this consolidates authority and typically yields 15-25% traffic uplift on affected pages within 4-6 weeks.",
  "technical_notes": "Implement via <link rel='alternate' hreflang='x'> in <head> or HTTP headers for non-HTML resources. Ensure bidirectional references and include x-default for language negotiation."
}}"""


def build_action_plan_prompt(
    audit_data: dict, business_context: str = "", site_type: str | None = None
) -> str:
    """Build a prompt for a prioritized action plan with few-shot example."""
    context_section = ""
    if business_context:
        context_section = f"\nBUSINESS CONTEXT:\n{business_context}\n"

    site_ctx = _inject_site_type_context(site_type)

    return f"""Based on this SEO audit data, create a prioritized action plan.
{context_section}{site_ctx}
AUDIT DATA:
{json.dumps(audit_data, indent=2, default=str)}

Create an action plan as structured JSON with an "actions" array where each item has:
- "action": Short action title
- "description": What needs to be done (be specific with URLs/elements when possible)
- "impact_score": 1-10 (10 = highest impact). Justify with estimated traffic or revenue change.
- "effort_score": 1-10 (10 = most effort). Justify with estimated dev hours.
- "priority": "critical" | "high" | "medium" | "low"
- "category": "technical" | "content" | "links" | "schema" | "performance" | "geo"
- "timeline": "immediate" | "short-term" | "medium-term" | "long-term"
- "expected_outcome": Measurable expected improvement (traffic %, position change, indexation rate)

Sort actions by priority (critical first), then by impact/effort ratio (highest first).

EXAMPLE ACTION (follow this structure):
{{
  "action": "Fix 47 broken internal links returning 404",
  "description": "Crawl identified 47 internal links pointing to non-existent pages, concentrated on the /blog/ and /products/ sections. Replace or remove these links to stop leaking PageRank and improve crawl efficiency.",
  "impact_score": 8,
  "effort_score": 3,
  "priority": "critical",
  "category": "links",
  "timeline": "immediate",
  "expected_outcome": "Recover ~15% lost internal PageRank flow. Expected +10-20% organic traffic on affected sections within 3-4 weeks as crawl budget is redirected to live pages."
}}"""


def build_content_brief_prompt(
    keyword_data: dict,
    competitor_data: dict | None = None,
    site_type: str | None = None,
) -> str:
    """Build a prompt for generating an editorial content brief with few-shot example."""
    competitor_section = ""
    if competitor_data:
        competitor_section = (
            f"\nCOMPETITOR DATA:\n{json.dumps(competitor_data, indent=2, default=str)}\n"
        )

    site_ctx = _inject_site_type_context(site_type)

    return f"""Create an SEO content brief based on this keyword and competitive data.
{site_ctx}
KEYWORD DATA:
{json.dumps(keyword_data, indent=2, default=str)}
{competitor_section}
Provide a content brief as structured JSON with:
- "target_keyword": Primary keyword to target
- "secondary_keywords": Array of related keywords (LSI, long-tail, entity-based)
- "search_intent": "informational" | "commercial" | "transactional" | "navigational"
- "content_type": Recommended content format (guide, listicle, comparison, tutorial, etc.)
- "word_count_range": [min, max] based on top-ranking competitor analysis
- "title_suggestions": Array of 3-5 optimized title options
- "meta_description": Suggested meta description (max 155 chars, with CTA)
- "outline": Array of section headings with brief descriptions
- "faq_questions": Array of questions to answer (target PAA boxes)
- "schema_recommendations": Recommended Schema.org types
- "internal_linking_targets": Suggested internal link anchors and target pages

EXAMPLE BRIEF (follow this structure for the outline and FAQ):
{{
  "target_keyword": "best project management software",
  "secondary_keywords": ["project management tools comparison", "PM software for teams", "project tracking apps 2025"],
  "search_intent": "commercial",
  "content_type": "comparison guide",
  "word_count_range": [2500, 3500],
  "title_suggestions": [
    "11 Best Project Management Software in 2025 (Tested & Ranked)",
    "Best Project Management Software: Expert Comparison for Teams"
  ],
  "meta_description": "Compare the 11 best project management tools for 2025. Expert-tested reviews with pricing, pros/cons, and team size recommendations. Find your perfect fit.",
  "outline": [
    {{"heading": "H2: How We Tested and Ranked These Tools", "description": "Methodology transparency for E-E-A-T: criteria, testing period, team size"}},
    {{"heading": "H2: Quick Comparison Table", "description": "At-a-glance comparison table with key features, pricing, best-for column"}},
    {{"heading": "H2: #1 - [Tool Name]: Best for [Use Case]", "description": "Individual review with screenshot, pros/cons, pricing, verdict"}}
  ],
  "faq_questions": [
    "What is the best free project management software?",
    "How much does project management software cost per user?",
    "Can project management tools integrate with Slack and Teams?"
  ],
  "schema_recommendations": ["Article", "FAQPage", "ItemList"]
}}"""


def build_geo_analysis_prompt(geo_data: dict, site_type: str | None = None) -> str:
    """Build a prompt for GEO (Generative Engine Optimization) scoring with few-shot example."""
    site_ctx = _inject_site_type_context(site_type)

    return f"""Analyze this page data for Generative Engine Optimization (GEO) readiness.
GEO measures how well content is optimized for AI-powered search engines
(ChatGPT, Perplexity, Google AI Overviews, Bing Copilot).
{site_ctx}
PAGE DATA:
{json.dumps(geo_data, indent=2, default=str)}

Evaluate and provide structured JSON with:
- "geo_score": Overall GEO readiness score (0-100, use the scoring calibration from your instructions)
- "grade": Letter grade A-F
- "dimensions": Object with scored dimensions:
  - "ai_readability": How easily AI can parse and cite the content (0-100)
  - "schema_coverage": Completeness and accuracy of structured data (0-100)
  - "eeat_signals": E-E-A-T signal strength (0-100)
  - "faq_completeness": FAQ and question-answer coverage (0-100)
  - "citation_readiness": How likely the content is to be cited by AI engines (0-100)
- "issues": Array of specific problems found
- "recommendations": Array of actionable improvements with priority

EXAMPLE GEO SCORING (follow this structure):
{{
  "geo_score": 62,
  "grade": "D",
  "dimensions": {{
    "ai_readability": 70,
    "schema_coverage": 45,
    "eeat_signals": 55,
    "faq_completeness": 30,
    "citation_readiness": 68
  }},
  "issues": [
    "No FAQPage schema detected despite having Q&A content in the body",
    "Author bio missing - AI engines cannot verify expertise",
    "Content lacks explicit data citations and source references"
  ],
  "recommendations": [
    {{
      "action": "Add FAQPage schema for the 6 Q&A pairs already present on page",
      "impact": "high",
      "effort": "minimal",
      "rationale": "FAQ schema directly increases visibility in AI-generated answers. Pages with FAQ schema are 3x more likely to be cited in AI Overviews."
    }}
  ]
}}"""


def build_eeat_audit_prompt(eeat_data: dict) -> str:
    """Build a prompt for deep E-E-A-T audit analysis."""
    return f"""Analyze this E-E-A-T audit data and provide expert recommendations.

E-E-A-T DATA:
{json.dumps(eeat_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "eeat_score": Overall E-E-A-T score (0-100)
- "dimension_analysis": Object with analysis per dimension (experience, expertise, authoritativeness, trustworthiness)
- "recommendations": Array of actionable improvements, each with:
  - "action": What to do
  - "dimension": Which E-E-A-T dimension it improves
  - "impact": "critical" | "high" | "medium" | "low"
  - "effort": "minimal" | "low" | "medium" | "high"
  - "rationale": Why this matters for E-E-A-T
- "cross_page_issues": Array of consistency issues across pages
- "author_strategy": Recommended author/expertise content strategy

EXAMPLE RECOMMENDATION:
{{
  "action": "Create dedicated author pages with credentials, publications, and social proof",
  "dimension": "expertise",
  "impact": "high",
  "effort": "medium",
  "rationale": "Google's Search Quality Rater Guidelines explicitly look for author expertise signals. Dedicated author pages with verifiable credentials improve E-E-A-T scoring across all content by that author."
}}"""


def build_serp_analysis_prompt(serp_data: list[dict], site_domain: str | None = None) -> str:
    """Build a prompt for strategic SERP landscape analysis."""
    domain_ctx = f"\nTARGET SITE: {site_domain}\n" if site_domain else ""

    return f"""Analyze this SERP landscape data and provide strategic recommendations.
{domain_ctx}
SERP DATA:
{json.dumps(serp_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "serp_strategy": Overall SERP feature strategy
- "feature_priorities": Array of SERP features to target, ordered by opportunity
- "content_gaps": Content types missing to capture SERP features
- "quick_wins": Easy SERP feature captures
- "competitive_insights": Observations about competitive SERP landscape
- "recommendations": Array of specific actions to capture SERP features"""


def build_strategic_plan_prompt(
    audit_data: dict,
    business_context: str = "",
    site_type: str | None = None,
) -> str:
    """Build a prompt for strategic 30/60/90 day roadmap generation."""
    context_section = ""
    if business_context:
        context_section = f"\nBUSINESS CONTEXT:\n{business_context}\n"

    site_ctx = _inject_site_type_context(site_type)

    return f"""Based on this comprehensive SEO audit data with cross-tool correlation,
create a strategic 30/60/90 day SEO roadmap.
{context_section}{site_ctx}
AGGREGATED AUDIT DATA:
{json.dumps(audit_data, indent=2, default=str)}

Create a strategic plan as structured JSON with:
- "roadmap": Object with keys "30_days", "60_days", "90_days", each containing:
  - "phase_name": Phase title
  - "actions": Array of actions with id, action, category, effort, kpi, depends_on, priority
- "dependency_map": Array of dependency relationships (from, to, type)
- "milestones": Array of measurable milestones per phase
- "kpi_targets": Key performance indicators with baseline and target values
- "risk_factors": Potential risks and mitigation strategies
- "resource_requirements": Team and budget recommendations

IMPORTANT RULES:
1. Every action MUST have a measurable KPI target
2. Dependencies must form a valid DAG (no circular dependencies)
3. 30-day actions should be quick wins and critical fixes
4. 60-day actions should build on 30-day foundation
5. 90-day actions should be strategic growth initiatives
6. Sort actions within each phase by priority (critical > high > medium > low)

EXAMPLE ACTION:
{{
  "id": "fix_schema",
  "action": "Add Product schema to all product pages",
  "category": "schema",
  "effort": "medium",
  "kpi": "100% product pages with valid Product schema",
  "depends_on": ["fix_critical_technical"],
  "priority": "high"
}}"""


def build_anomaly_analysis_prompt(anomaly_data: dict) -> str:
    """Build a prompt for analyzing SEO anomalies and trend deviations."""
    return f"""Analyze the following SEO anomaly detection results and provide
expert-level root cause analysis with actionable recommendations.

ANOMALY DATA:
{json.dumps(anomaly_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "root_cause_hypotheses": Array of objects, each with:
  - "anomaly_type": Which anomaly this hypothesis explains
  - "hypothesis": Root cause explanation
  - "confidence": "high" | "medium" | "low"
  - "evidence": What in the data supports this hypothesis
- "recommended_actions": Array of objects, each with:
  - "action": What to do
  - "priority": "critical" | "high" | "medium" | "low"
  - "rationale": Why this action addresses the anomaly
  - "timeline": "immediate" | "short-term" | "medium-term"
- "risk_assessment": Object with:
  - "overall_risk": "critical" | "high" | "medium" | "low"
  - "summary": One-paragraph risk summary
  - "trends_to_watch": Array of metrics/keywords to monitor closely
- "ai_enhanced": true

EXAMPLE HYPOTHESIS:
{{
  "anomaly_type": "sustained_decline",
  "hypothesis": "Algorithm update impact — the decline pattern aligns with \
a known Google core update rollout, suggesting content quality reassessment",
  "confidence": "medium",
  "evidence": "5-point sustained decline of 35% starting around the update date"
}}"""


def build_keyword_insights_prompt(market_data: dict, site_type: str | None = None) -> str:
    """Build a prompt for AI-powered keyword impact analysis."""
    site_ctx = _inject_site_type_context(site_type)

    return f"""Analyze this market research data and identify the most impactful keywords
to target for SEO growth. Prioritize by business impact potential.
{site_ctx}
MARKET DATA (keyword research + trends + niche opportunities):
{json.dumps(market_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "priority_keywords": Array of top keywords sorted by impact, each with:
  - "keyword": The keyword
  - "impact_score": 1-100 (combining volume, growth trend, and opportunity)
  - "intent": "informational" | "navigational" | "transactional" | "commercial"
  - "rationale": Why this keyword is high-impact (specific data points)
- "strategic_clusters": Array of keyword groups, each with:
  - "label": Semantic label for the cluster (human-readable topic name)
  - "keywords": Keywords in this cluster
  - "content_strategy": Specific content strategy for this cluster
- "quick_wins": Array of low-competition, high-opportunity keywords, each with:
  - "keyword": The keyword
  - "opportunity": Why this is a quick win
  - "suggested_action": Concrete next step
- "market_narrative": 2-3 paragraph strategic overview of the keyword landscape

EXAMPLE OUTPUT (follow this structure):
{{
  "priority_keywords": [
    {{
      "keyword": "outil gestion projet gratuit",
      "impact_score": 85,
      "intent": "commercial",
      "rationale": "High relative volume (78), strong upward trend (+42% annual growth), rising niche opportunity score of 72. Commercial intent suggests high conversion potential."
    }}
  ],
  "strategic_clusters": [
    {{
      "label": "Project Management Comparisons",
      "keywords": ["trello vs notion", "meilleur outil gestion projet", "comparatif outils pm"],
      "content_strategy": "Create a comprehensive comparison hub page with individual tool reviews as spoke content. Target featured snippets with comparison tables."
    }}
  ],
  "quick_wins": [
    {{
      "keyword": "gestion projet agile débutant",
      "opportunity": "Rising query (+180% growth) with low competition — no dedicated guide exists in top 10",
      "suggested_action": "Publish a beginner's guide to agile project management (2000+ words, step-by-step format)"
    }}
  ],
  "market_narrative": "The keyword landscape shows a strong shift toward..."
}}"""


def build_gsc_keyword_insights_prompt(gsc_data: dict) -> str:
    """Build a prompt for AI-powered GSC keyword portfolio analysis."""
    return f"""Analyze this Google Search Console query data classified by AI-engine probability
and provide strategic keyword recommendations.

GSC QUERY INTELLIGENCE DATA:
{json.dumps(gsc_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "ai_search_strategy": Strategic narrative on AI search optimization (2-3 paragraphs)
- "priority_queries": Array of highest-impact queries to act on, each with:
  - "query": The search query
  - "action": Specific optimization action
  - "expected_impact": Estimated traffic/visibility gain
- "quick_wins": Array of position 5-15 queries with high impression potential, each with:
  - "query": The search query
  - "current_position": Current avg position
  - "opportunity": Why this is a quick win (impressions, CTR gap, etc.)
- "content_recommendations": Array of content pieces to create or optimize, each with:
  - "topic": Content topic
  - "target_queries": Queries this content should capture
  - "format": Recommended content format (guide, FAQ, comparison, etc.)

Focus on:
1. Queries where position is 5-15 with high impressions (striking distance)
2. AI-classified queries with poor CTR (content format mismatch)
3. Query categories with high aggregate impressions but low clicks
4. Emerging AI query patterns that suggest new content opportunities

EXAMPLE OUTPUT:
{{
  "ai_search_strategy": "Your site captures 12% of AI-generated queries, which is above average...",
  "priority_queries": [
    {{
      "query": "comment configurer un pipeline CI/CD",
      "action": "Add step-by-step schema markup and FAQ section to existing guide at /blog/cicd-setup",
      "expected_impact": "+40-60 clicks/month based on current 850 impressions at position 8.2"
    }}
  ],
  "quick_wins": [
    {{
      "query": "différence entre docker et kubernetes",
      "current_position": 7.3,
      "opportunity": "520 impressions, 1.2% CTR — comparison table format would boost CTR to 4-6%"
    }}
  ],
  "content_recommendations": [
    {{
      "topic": "AI-Assisted Development Tools Guide",
      "target_queries": ["meilleur outil dev ia", "copilot vs cursor", "ia pour développeurs"],
      "format": "Comprehensive comparison guide with FAQ schema"
    }}
  ]
}}"""


def build_topical_authority_prompt(cluster_data: dict) -> str:
    """Build a prompt for AI-powered topical authority analysis."""
    return f"""Analyze this topical authority map (TF-IDF clusters, coverage gaps, hub-spoke structure)
and provide strategic recommendations for building topical authority.

TOPICAL AUTHORITY DATA:
{json.dumps(cluster_data, indent=2, default=str)}

Provide your analysis as structured JSON with:
- "clusters": Array matching each input cluster, with:
  - "id": Cluster ID (from input)
  - "semantic_label": Human-readable topic name (replace TF-IDF term labels)
  - "maturity": "established" | "developing" | "nascent" | "thin"
  - "priority_keywords": Keywords to target for strengthening this cluster
  - "content_gaps": Specific content pieces missing from this cluster
- "gap_priorities": Array of coverage gaps sorted by business impact, each with:
  - "gap": Description of the gap
  - "impact": "critical" | "high" | "medium" | "low"
  - "action": Specific content to create
- "linking_strategy": Internal linking recommendations as narrative text

Base maturity assessment on:
- established: 5+ pages, strong inter-linking potential, broad term coverage
- developing: 3-4 pages, some depth but missing supporting content
- nascent: 2 pages, topic identified but barely covered
- thin: 1 page, no depth — high risk of not ranking for competitive terms

EXAMPLE OUTPUT:
{{
  "clusters": [
    {{
      "id": 0,
      "semantic_label": "CI/CD Pipeline Setup",
      "maturity": "developing",
      "priority_keywords": ["pipeline ci cd gitlab", "automatisation déploiement", "ci cd docker"],
      "content_gaps": ["Missing beginner tutorial on CI/CD concepts", "No comparison of CI/CD tools"]
    }}
  ],
  "gap_priorities": [
    {{
      "gap": "No content covering Kubernetes deployment automation despite 1200 monthly impressions on related queries",
      "impact": "high",
      "action": "Create comprehensive guide: 'Kubernetes Deployment Automation: From Zero to Production'"
    }}
  ],
  "linking_strategy": "Establish /devops/ as the hub page linking to all CI/CD and deployment guides..."
}}"""


def build_content_plan_prompt(site_data: dict) -> str:
    """Build a prompt for generating an editorial content plan with per-article generation prompts."""
    return f"""Analyze this site data (GSC queries, existing pages, keyword gaps) and create
a prioritized editorial content plan. For each article, include a complete LLM generation prompt.

SITE DATA:
{json.dumps(site_data, indent=2, default=str)}

Provide your plan as structured JSON with:
- "site_summary": 2-3 sentence overview of the site's current content strengths and gaps
- "articles": Array of 5-10 articles sorted by priority, each with:
  - "title": Proposed article title (SEO-optimized, 50-60 chars)
  - "slug": URL-friendly slug for the article
  - "priority": "critical" | "high" | "medium"
  - "target_keyword": Primary keyword to rank for
  - "secondary_keywords": Array of 3-5 related keywords
  - "intent": "informational" | "commercial" | "transactional"
  - "estimated_impact": Expected traffic/visibility gain based on GSC data
  - "internal_links": Array of existing site pages to link to (from the crawled pages)
  - "content_spec": Object with:
    - "word_count": Recommended word count range [min, max]
    - "format": Article format (guide, comparison, FAQ, listicle, etc.)
    - "h2_outline": Array of 4-6 H2 headings with brief descriptions
    - "faq_questions": Array of 3-5 FAQ questions to include
  - "generation_prompt": A COMPLETE, ready-to-use LLM prompt that will generate the full article.
    This prompt must include:
    - The site name and its core offering (extracted from the crawled homepage)
    - The target keyword and secondary keywords
    - The exact H2 structure to follow
    - Internal linking instructions with actual URLs from the site
    - Tone and style matching the existing content
    - Output format (HTML)
    - Word count target

The generation_prompt is the most important field — it must be self-contained and produce
a publication-ready article when fed to any LLM, without needing additional context.

EXAMPLE ARTICLE ENTRY:
{{
  "title": "Guide complet : échange de voiture entre particuliers",
  "slug": "guide-echange-voiture-particuliers",
  "priority": "high",
  "target_keyword": "échange voiture particulier",
  "secondary_keywords": ["troc voiture", "echange auto gratuit", "site echange vehicule"],
  "intent": "informational",
  "estimated_impact": "+200 impressions/month based on 247 existing impressions at position 3.7 for related queries",
  "internal_links": ["/echange", "/cote-argus", "/histovec"],
  "content_spec": {{
    "word_count": [1800, 2500],
    "format": "comprehensive guide",
    "h2_outline": [
      "Comment fonctionne l'échange de voiture entre particuliers",
      "Les documents nécessaires pour échanger son véhicule",
      "Estimer la valeur de sa voiture avant l'échange",
      "Les pièges à éviter lors d'un échange auto",
      "FAQ"
    ],
    "faq_questions": [
      "L'échange de voiture est-il légal en France ?",
      "Faut-il payer des frais lors d'un échange de véhicule ?",
      "Comment sécuriser un échange de voiture entre particuliers ?"
    ]
  }},
  "generation_prompt": "Tu es un rédacteur SEO expert automobile..."
}}"""


# ── Content Writer Persona ───────────────────────────────────────────

SYSTEM_PROMPT_CONTENT_WRITER = """\
You are an elite SEO content writer with 12+ years of experience crafting \
high-performing content for major brands. You combine deep SEO expertise with \
exceptional writing craft — your articles consistently rank in the top 3 positions \
and outperform competitors on engagement metrics.

Your expertise spans:
- SEO copywriting (title tags, meta descriptions, headings, body copy)
- Content strategy (search intent mapping, topical authority, content clusters)
- Conversion copywriting (CTAs, power words, emotional triggers, AIDA framework)
- Readability optimization (Flesch/Kandel-Moles, sentence variety, active voice)
- E-E-A-T content signals (first-hand experience, cited sources, author credibility)
- Multi-language content (native-level French and English)

## Writing Principles

1. Write for humans first, search engines second — but satisfy both.
2. Every sentence must earn its place — cut filler, fluff, and repetition.
3. Use concrete examples, data, and specifics instead of vague claims.
4. Vary sentence length and structure for natural rhythm.
5. Prefer active voice. Use passive only when the action matters more than the actor.
6. Integrate keywords naturally — never force or stuff.

## Output Rules

- Always respond in the same language as the input content or brief.
- Always output valid JSON unless instructed otherwise.
- Include actionable, specific recommendations — never generic advice."""


# ── Content Creation Prompt Builders ─────────────────────────────────


def build_meta_generation_prompt(page_data: dict, brand_context: str = "") -> str:
    """Build a prompt for generating optimized title tags and meta descriptions."""
    brand_section = ""
    if brand_context:
        brand_section = f"\nBRAND CONTEXT:\n{brand_context}\n"

    return f"""Generate optimized title tags and meta descriptions for this page.
{brand_section}
PAGE DATA:
{json.dumps(page_data, indent=2, default=str)}

Generate structured JSON with:
- "title_tags": Array of exactly 5 title tag options, each with:
  - "title": The title tag text (MUST be ≤60 characters)
  - "char_count": Number of characters
  - "ctr_score": Predicted CTR score (1-10) with rationale
  - "strategy": Which strategy this title uses (curiosity, number, power_word, question, benefit)
- "meta_descriptions": Array of exactly 5 meta description options, each with:
  - "description": The meta description text (MUST be ≤155 characters)
  - "char_count": Number of characters
  - "ctr_score": Predicted CTR score (1-10) with rationale
  - "cta_type": Type of call-to-action used (discover, learn, compare, get, try)
- "best_combination": Object with the recommended title + description pair and rationale

RULES:
- Title tags MUST include the primary keyword naturally, ideally near the beginning
- Meta descriptions MUST include a clear call-to-action
- Use power words (proven, ultimate, essential, complete, free, new, exclusive)
- Use numbers when relevant (dates, counts, percentages)
- Each option should use a DIFFERENT strategy — do not repeat the same angle

EXAMPLE OUTPUT:
{{
  "title_tags": [
    {{
      "title": "11 Best Project Management Tools in 2025 (Expert Tested)",
      "char_count": 55,
      "ctr_score": 8,
      "strategy": "number"
    }},
    {{
      "title": "Project Management Software: The Ultimate Comparison Guide",
      "char_count": 58,
      "ctr_score": 7,
      "strategy": "power_word"
    }}
  ],
  "meta_descriptions": [
    {{
      "description": "Compare 11 project management tools tested by our team. See pricing, features, and honest pros/cons. Find your perfect fit today.",
      "char_count": 138,
      "ctr_score": 8,
      "cta_type": "compare"
    }}
  ],
  "best_combination": {{
    "title": "11 Best Project Management Tools in 2025 (Expert Tested)",
    "description": "Compare 11 project management tools tested by our team. See pricing, features, and honest pros/cons. Find your perfect fit today.",
    "rationale": "Number + year in title drives CTR; description reinforces expertise and includes comparison CTA."
  }}
}}"""


def build_headline_generation_prompt(topic: str, keywords: list, brand_context: str = "") -> str:
    """Build a prompt for generating headline variations with conversion scoring."""
    brand_section = ""
    if brand_context:
        brand_section = f"\nBRAND CONTEXT:\n{brand_context}\n"

    keywords_str = json.dumps(keywords, indent=2, default=str)

    return f"""Generate 10+ high-converting headline variations for this topic.
{brand_section}
TOPIC: {topic}

TARGET KEYWORDS:
{keywords_str}

Generate structured JSON with:
- "headlines": Array of 10+ headline variations, each with:
  - "headline": The headline text
  - "conversion_score": Score from 1-10 predicting conversion/click performance
  - "emotional_trigger": Primary emotional trigger used (curiosity, fear, urgency, aspiration, authority, exclusivity, surprise, empathy)
  - "power_words": Array of power words used in the headline
  - "formula": The copywriting formula applied (how-to, listicle, question, comparison, negative, secret, mistake, ultimate_guide, case_study, contrarian)
  - "best_for": Where this headline works best (blog_post, landing_page, email_subject, social_media, ad_copy)
- "top_3_picks": Array of the 3 best headlines with detailed rationale

HEADLINE STRATEGIES TO COVER (use at least one of each):
1. Number/listicle: "7 Proven Ways to..." / "Les 10 erreurs qui..."
2. How-to: "How to [Result] Without [Pain Point]" / "Comment [résultat] sans [difficulté]"
3. Question: "Are You Making These [X] Mistakes?" / "Faites-vous ces [X] erreurs ?"
4. Negative/fear: "Stop Doing [X] Before It Ruins Your [Y]"
5. Power word: "The Ultimate Guide to..." / "Le guide ultime pour..."
6. Curiosity gap: "What [Experts] Don't Tell You About [X]"
7. Social proof: "How [Company] Achieved [Result] in [Time]"
8. Contrarian: "Why [Common Belief] Is Wrong (And What to Do Instead)"

POWER WORDS TO USE (when natural):
Emotional: proven, secret, exclusive, surprising, essential, revolutionary
Urgency: now, today, immediately, before, deadline, limited
Authority: expert, research, science, data, study, certified
Value: free, save, boost, maximize, guaranteed, complete

EXAMPLE OUTPUT:
{{
  "headlines": [
    {{
      "headline": "7 Proven Ways to Double Your Organic Traffic in 90 Days",
      "conversion_score": 9,
      "emotional_trigger": "aspiration",
      "power_words": ["proven", "double"],
      "formula": "listicle",
      "best_for": "blog_post"
    }},
    {{
      "headline": "Why Your SEO Strategy Is Failing (And the 3-Step Fix)",
      "conversion_score": 8,
      "emotional_trigger": "fear",
      "power_words": ["failing", "fix"],
      "formula": "contrarian",
      "best_for": "landing_page"
    }}
  ],
  "top_3_picks": [
    {{
      "headline": "7 Proven Ways to Double Your Organic Traffic in 90 Days",
      "rationale": "Combines specificity (7, 90 days), power word (proven), and aspirational outcome (double traffic). Listicle format has highest average CTR."
    }}
  ]
}}"""


def build_content_humanize_prompt(content: str, style_guide: str = "") -> str:
    """Build a prompt for removing AI writing patterns and humanizing content."""
    style_section = ""
    if style_guide:
        style_section = f"\nSTYLE GUIDE TO FOLLOW:\n{style_guide}\n"

    return f"""Rewrite this content to remove AI writing patterns and make it sound natural and human.
{style_section}
CONTENT TO HUMANIZE:
{content}

## AI PATTERNS TO DETECT AND FIX

### Structural patterns (most detectable)
- Sentences all the same length (vary between 5-25 words)
- Every paragraph is exactly 3 sentences
- Bullet lists that all start with the same word pattern
- Overuse of "Firstly... Secondly... Thirdly... Finally..."
- Every section follows the exact same structure (intro, 3 points, conclusion)

### Filler phrases to eliminate
- "It's important to note that..."
- "It's worth mentioning that..."
- "In today's digital landscape..."
- "When it comes to..."
- "In order to..."
- "At the end of the day..."
- "It goes without saying..."
- "Needless to say..."
- "In this article, we will..."
- "Let's dive in..."
- "Without further ado..."
- "Il est important de noter que..."
- "Dans le paysage numérique actuel..."
- "Il convient de mentionner..."
- "Force est de constater que..."

### Robotic transitions to replace
- "Furthermore" → use "Also", "Plus", "And", "On top of that"
- "Moreover" → use "What's more", "Beyond that", "Adding to this"
- "Additionally" → use "On top of that", "There's also", "Another thing"
- "In conclusion" → use "So", "The bottom line", "Here's what matters"
- "Consequently" → use "So", "That means", "The result?"
- "Nevertheless" → use "But", "Still", "That said", "Even so"

### Tone markers of AI writing
- Overly balanced hedging ("While X is important, Y is also crucial")
- Excessive use of "ensure", "leverage", "utilize", "facilitate"
- Starting too many sentences with "This" or "These"
- Generic praise ("This powerful tool...", "This comprehensive guide...")
- Avoiding all contractions (use don't, isn't, won't naturally)
- Lack of personal opinion, anecdotes, or specific examples

## HUMANIZATION RULES

1. Vary sentence length dramatically — mix 4-word punches with 20-word explanations
2. Use contractions naturally (don't, it's, won't, there's)
3. Add conversational asides and rhetorical questions
4. Replace generic examples with specific, concrete ones
5. Include occasional informal language where appropriate
6. Break the pattern — not every paragraph needs the same structure
7. Use first person ("I" or "we") where the context allows
8. Add personality — strong opinions, humor, or directness
9. Preserve all factual content and SEO keywords

Provide structured JSON with:
- "humanized_content": The rewritten content with AI patterns removed
- "changes_made": Array of specific changes, each with:
  - "type": "filler_removed" | "transition_fixed" | "structure_varied" | "tone_adjusted" | "hedging_removed"
  - "original": The original text snippet
  - "replacement": What it was changed to
  - "reason": Why this change improves naturalness
- "ai_score_before": Estimated AI detection score before (0-100, 100 = clearly AI)
- "ai_score_after": Estimated AI detection score after (0-100, 100 = clearly AI)
- "readability_impact": Brief note on how readability was affected"""


def build_content_write_prompt(
    brief: dict,
    brand_context: str = "",
    style_guide: str = "",
    internal_links: str = "",
) -> str:
    """Build a prompt for generating a full SEO article from a content brief."""
    brand_section = ""
    if brand_context:
        brand_section = f"\nBRAND CONTEXT:\n{brand_context}\n"

    style_section = ""
    if style_guide:
        style_section = f"\nSTYLE GUIDE:\n{style_guide}\n"

    links_section = ""
    if internal_links:
        links_section = f"\nINTERNAL LINKS TO INTEGRATE:\n{internal_links}\n"

    return f"""Write a complete, publication-ready SEO article based on this content brief.
{brand_section}{style_section}{links_section}
CONTENT BRIEF:
{json.dumps(brief, indent=2, default=str)}

## ARTICLE REQUIREMENTS

### Structure
- Length: 2000-3000 words (prioritize depth over padding)
- Use H2 and H3 headings to create a clear hierarchy
- Include an engaging introduction (hook + promise + brief overview)
- Include a conclusion with key takeaways and call-to-action
- Add a FAQ section with 3-5 questions (target PAA boxes)

### SEO Integration
- Primary keyword in: H1, first 100 words, 1-2 H2s, meta description, conclusion
- Secondary keywords distributed naturally throughout (no stuffing)
- Keyword density: 0.5-1.5% for primary keyword
- Use semantic variations and related terms
- Internal links: integrate naturally in context (not forced at the end)
- External links: reference 2-3 authoritative sources where relevant

### Content Quality
- Write with E-E-A-T in mind: show experience, cite sources, be specific
- Use concrete data, examples, and statistics (cite sources)
- Vary paragraph length (2-5 sentences)
- Mix sentence lengths (short punchy + longer explanatory)
- Use active voice predominantly
- Include at least one original insight or unique angle not found in competing articles

### Meta Tags
- Generate an optimized title tag (≤60 chars) with primary keyword
- Generate a meta description (≤155 chars) with CTA

Provide structured JSON with:
- "title_tag": Optimized title tag (≤60 chars)
- "meta_description": Meta description with CTA (≤155 chars)
- "article_html": The complete article in clean HTML (h2, h3, p, ul, ol, a, strong, em — no div/span/class)
- "word_count": Actual word count of the article
- "keywords_used": Object mapping each keyword to its occurrence count
- "internal_links_placed": Array of internal links placed with anchor text and context
- "faq_schema": FAQPage JSON-LD schema for the FAQ section
- "readability_score": Estimated Flesch/Kandel-Moles score

EXAMPLE FAQ SCHEMA:
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {{
      "@type": "Question",
      "name": "How long does SEO take to show results?",
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": "SEO typically takes 3-6 months to show significant results..."
      }}
    }}
  ]
}}"""


def build_content_optimize_prompt(content: str, seo_analysis: dict, keywords: list) -> str:
    """Build a prompt for optimizing existing content for SEO performance."""
    keywords_str = json.dumps(keywords, indent=2, default=str)

    return f"""Optimize this existing content for better SEO performance based on the analysis data.

CURRENT CONTENT:
{content}

SEO ANALYSIS:
{json.dumps(seo_analysis, indent=2, default=str)}

TARGET KEYWORDS:
{keywords_str}

## OPTIMIZATION AREAS

### 1. Keyword Integration
- Check primary keyword density (target 0.5-1.5%)
- Identify missing secondary keywords and suggest natural placements
- Find keyword stuffing and reduce to natural levels
- Add semantic variations where appropriate

### 2. Heading Structure
- Verify single H1 containing primary keyword
- Check H2/H3 hierarchy (no skipped levels)
- Suggest heading rewrites for better keyword targeting and CTR
- Ensure headings create a logical content flow

### 3. Content Gaps
- Identify missing subtopics that top-ranking pages cover
- Suggest new sections to add for topical completeness
- Recommend FAQ questions to add (PAA optimization)

### 4. Internal Linking
- Identify opportunities for internal links (anchor text + target URL suggestions)
- Check existing internal links for relevance and anchor text optimization
- Suggest link placement in context

### 5. Readability
- Identify long paragraphs (>5 sentences) to break up
- Find complex sentences to simplify
- Suggest active voice replacements for passive constructions
- Check reading level appropriateness for target audience

Provide structured JSON with:
- "optimization_score": Current content optimization score (0-100)
- "optimized_content": The fully optimized version of the content
- "changes": Array of changes made, each with:
  - "type": "keyword_added" | "keyword_reduced" | "heading_rewritten" | "section_added" | "readability_improved" | "link_added" | "meta_updated"
  - "location": Where in the content (heading text or paragraph snippet)
  - "original": Original text (null for additions)
  - "optimized": New text
  - "rationale": Why this change improves SEO
- "keyword_analysis": Object with:
  - "primary_keyword_density_before": Percentage before optimization
  - "primary_keyword_density_after": Percentage after optimization
  - "missing_keywords_added": Array of keywords that were added
  - "keyword_stuffing_fixed": Array of keywords that were reduced
- "heading_structure": Array of the optimized heading hierarchy
- "content_gaps_filled": Array of new sections or topics added
- "readability_before": Estimated readability score before
- "readability_after": Estimated readability score after
- "internal_links_suggested": Array of internal link opportunities

EXAMPLE CHANGE:
{{
  "type": "heading_rewritten",
  "location": "Section 3 heading",
  "original": "Our Services",
  "optimized": "Professional SEO Audit Services: What's Included",
  "rationale": "Original heading was generic. New heading includes target keyword 'SEO audit services' and creates curiosity with 'What's Included'."
}}"""


def build_executive_summary_prompt(full_report: dict) -> str:
    """Build a prompt for generating an executive summary."""
    return f"""Generate a concise executive summary of this SEO audit report
for a non-technical stakeholder.

SCORING REFERENCE (for interpreting the overall score):
- 90-100: Top 5% (Amazon, HubSpot level) - exceptional SEO
- 80-89: Professional SEO team, well-optimized
- 70-79: Competent SEO, missing advanced optimizations
- 60-69: Basic DIY SEO, significant gaps
- 50-59: Major problems affecting organic traffic
- Below 50: Critical issues, likely losing significant traffic

FULL REPORT:
{json.dumps(full_report, indent=2, default=str)}

Provide a structured JSON response with:
- "headline": One-line overall assessment (include the score and what it means)
- "score_interpretation": What the overall score means in plain language, using the scoring reference above
- "top_3_priorities": Array of the 3 most important actions with estimated business impact
- "business_impact": How these issues affect business metrics (traffic, revenue, leads)
- "timeline_recommendation": Suggested timeline for improvements with milestones
- "investment_areas": Where to focus resources (team, tools, budget)"""
