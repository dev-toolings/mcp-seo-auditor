---
description: Rules for AI-enhanced keyword tools (seo_market/insights, gsc_analytics/ai_queries, seo_site/topical_authority, seo_strategy/content_plan)
paths: "**/*.py"
---

# AI Keyword Intelligence Tools

## Tool patterns

### seo_market action=insights

Aggregates research + trends + niches then runs LLM analysis. Slow (~20s, pytrends rate limiting). Returns `ai_insights` with priority_keywords, strategic_clusters, quick_wins, market_narrative.

### gsc_analytics action=ai_queries

Classifies GSC queries by AI-engine probability, then enriches with LLM. Returns `ai_insights` under the existing analysis result.

### seo_site action=topical_authority

TF-IDF clustering + LLM enrichment for semantic labeling and gap strategy. Returns `ai_insights` under the cluster result.

### seo_strategy action=content_plan

Crawls site + pulls GSC data + generates editorial plan with per-article LLM prompts. Saves full plan (with generation_prompts) to a temp file. Returns lightweight summary + `plan_file` path. Read the file to access individual generation prompts.

## Adding new AI enrichment

Pattern to follow:

1. Add prompt builder in `app/services/llm/prompt_templates.py` (follow existing examples)
2. Add method on `AIAnalyzer` in `app/services/ai/ai_analyzer.py` (Style C: AI-only, `{}` fallback)
3. Wire in the tool handler or service
4. Always use `TokenBudget.prepare_audit_data()` before sending to LLM
5. Always wrap in try/except with `logger.warning` — never crash on LLM failure
6. Set `ai_enhanced: True/False` in result

## MCPInput base class

All MCP tool input schemas inherit from `MCPInput` (in `seo_server/schemas/validators.py`), not `BaseModel`. MCPInput handles JSON string coercion for clients that serialize input as string.
