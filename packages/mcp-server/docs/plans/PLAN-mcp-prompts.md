# Plan: 50 MCP Prompts SEO — ChatSEO Integration

## Context

**Spec**: Integrate 50 SEO prompts (from ChatSEO document) as native MCP prompts via FastMCP 3.0 `@mcp.prompt()`. Currently 0 prompts registered, 10 tools, 14 tool modules.

**Codebase findings**:
- `server.py` has `_register_tools()` pattern — prompts need identical `_register_prompts()`
- FastMCP 3.0 `@mcp.prompt(name=..., description=..., tags=...)` accepts `str` or `list[dict]` return
- Tools follow action-router pattern in `seo_server/tools/`, import `mcp` from `server.py`
- 6 `.claude/commands/` exist as Claude Code-specific workflows — these are complementary, not overlapping
- `PromptArgument(name, description, required)` auto-inferred from function signature

**Files in scope**: 12 new files, 1 modified (`server.py`)

---

## Architecture

```
seo_server/
├── server.py                  # MODIFIED: + _register_prompts()
└── prompts/                   # NEW: 10 domain modules + __init__.py
    ├── __init__.py            # register all prompt modules
    ├── keywords.py            # Prompts 1-5    — keyword research
    ├── analytics.py           # Prompts 6-10   — GSC performance
    ├── competitors.py         # Prompts 11-15  — competitive analysis
    ├── content.py             # Prompts 16-20  — content optimization
    ├── technical.py           # Prompts 21-25  — technical SEO
    ├── linking.py             # Prompts 26-30  — internal linking
    ├── geo.py                 # Prompts 31-35  — AI search / GEO
    ├── local_seo.py           # Prompts 36-40  — local SEO
    ├── ecommerce.py           # Prompts 41-45  — e-commerce SEO
    └── reporting.py           # Prompts 46-50  — reporting & planning
```

### Key Decisions

#### Decision: Pure template prompts vs tool-orchestrating prompts
**Options**: A) Return plain text prompt B) Return prompt + tool usage hints C) Return prompt that calls tools internally
**Pick**: B — template with tool hints
**Why**: MCP prompts are message templates, not executors. Adding tool usage hints (`Use gsc_analytics(action="query")...`) guides the LLM without coupling prompts to tool internals. This matches how `.claude/commands/` work today.
**One-way door?**: No — prompts can evolve to add/remove hints freely.

#### Decision: Prompt naming convention
**Options**: A) `seo_prompt_1` B) `seo_quick_wins` C) `chatgpt_seo_1`
**Pick**: B — semantic names with `seo_` prefix
**Why**: Consistent with tool naming (`seo_audit`, `seo_analyze`). Discoverable via `prompts/list`. Names like `seo_quick_wins`, `seo_competitor_keywords` are self-documenting.
**One-way door?**: No — names can be aliased or renamed.

#### Decision: Tags for categorization
**Options**: A) No tags B) Category tags (`keywords`, `analytics`, etc.)
**Pick**: B — use FastMCP `tags` parameter
**Why**: FastMCP 3.0 supports `tags: set[str]` on prompts. Clients can filter by tag. Maps directly to the 10 thematic categories.
**One-way door?**: No.

#### Decision: Parameter types
**Options**: A) All prompts take `site_url: str` B) Each prompt has specific params C) Mix of common + specific
**Pick**: C — common params (`site_url`, `competitor_url`) + prompt-specific params (optional)
**Why**: Some prompts need a URL, others need a keyword, some need both. Forcing a single param creates awkward UX. FastMCP auto-infers `PromptArgument` from function signature.
**One-way door?**: No.

---

## Waves

### Wave 1 (parallel) — Foundation + First 2 Modules

#### M1: Prompt infrastructure
- **Goal**: `_register_prompts()` works in `server.py`, `seo_server/prompts/__init__.py` imports modules
- **Files owned**: `seo_server/server.py`, `seo_server/prompts/__init__.py`
- **Tasks**:
  - [ ] Create `seo_server/prompts/__init__.py` with import pattern matching `tools/__init__.py`
  - [ ] Add `_register_prompts()` in `seo_server/server.py` (import `seo_server.prompts`)
  - [ ] Call `_register_prompts()` after `_register_tools()`
  - [ ] Add `--test` mode to also list prompts count
- **Tests**: `python -m seo_server.server --test` shows "N prompts available"
- **Done when**: prompt registration infrastructure works, 0 prompts registered (modules empty)

#### M2: keywords.py — Prompts 1-5
- **Goal**: 5 keyword research prompts registered and discoverable
- **Files owned**: `seo_server/prompts/keywords.py`
- **Tasks**:
  - [ ] `seo_quick_wins(site_url: str)` — #1: Quick win keywords (pos 4-20, high impressions)
  - [ ] `seo_competitor_keywords(site_url: str, competitor_url: str)` — #2: Competitor keyword gaps
  - [ ] `seo_longtail_suggestions(site_url: str)` — #3: Long-tail variations from top 10
  - [ ] `seo_keyword_clusters(site_url: str)` — #4: Group keywords by intent + clusters
  - [ ] `seo_seasonal_keywords(site_url: str, niche: str)` — #5: Seasonal keyword opportunities
  - [ ] Each prompt returns a structured message with tool usage hints
- **Tests**: `prompts/list` returns 5 prompts with tag `keywords`
- **Done when**: 5 prompts accessible, each with correct params and tool hints

#### M3: analytics.py — Prompts 6-10
- **Goal**: 5 GSC analytics prompts registered
- **Files owned**: `seo_server/prompts/analytics.py`
- **Tasks**:
  - [ ] `seo_gsc_review(site_url: str, days: int = 90)` — #6: GSC 3-month review
  - [ ] `seo_traffic_drop(site_url: str)` — #7: Traffic drop diagnosis
  - [ ] `seo_ctr_optimization(site_url: str)` — #8: Low CTR / high impressions pages
  - [ ] `seo_ranking_stability(site_url: str)` — #9: Unstable ranking keywords
  - [ ] `seo_intent_alignment(site_url: str)` — #10: Query-content intent alignment
  - [ ] Each prompt references `gsc_analytics` tool with appropriate actions
- **Tests**: `prompts/list` returns 10 prompts total (5 keywords + 5 analytics)
- **Done when**: 10 prompts total registered

### Wave 2 (parallel, after Wave 1) — 4 Domain Modules

#### M4: competitors.py — Prompts 11-15
- **Goal**: 5 competitive analysis prompts
- **Files owned**: `seo_server/prompts/competitors.py`
- **Tasks**:
  - [ ] `seo_competitor_compare(site_url: str, competitor_url: str)` — #11
  - [ ] `seo_competitor_content(competitor_url: str)` — #12
  - [ ] `seo_competitor_backlinks(site_url: str, competitor_url: str)` — #13
  - [ ] `seo_serp_features(site_url: str)` — #14
  - [ ] `seo_competitor_weaknesses(competitor_url: str)` — #15
- **Tests**: 15 prompts total
- **Done when**: competitor prompts registered with correct params

#### M5: content.py — Prompts 16-20
- **Goal**: 5 content optimization prompts
- **Files owned**: `seo_server/prompts/content.py`
- **Tasks**:
  - [ ] `seo_content_freshness(site_url: str)` — #16
  - [ ] `seo_cannibalization(site_url: str)` — #17
  - [ ] `seo_thin_content(site_url: str)` — #18
  - [ ] `seo_featured_snippet(url: str)` — #19
  - [ ] `seo_content_improve(url: str)` — #20
- **Tests**: 20 prompts total
- **Done when**: content prompts registered

#### M6: technical.py — Prompts 21-25
- **Goal**: 5 technical SEO prompts
- **Files owned**: `seo_server/prompts/technical.py`
- **Tasks**:
  - [ ] `seo_technical_audit(site_url: str)` — #21
  - [ ] `seo_indexation_status(site_url: str)` — #22
  - [ ] `seo_site_structure(site_url: str)` — #23
  - [ ] `seo_schema_markup(site_url: str)` — #24
  - [ ] `seo_mobile_performance(site_url: str)` — #25
- **Tests**: 25 prompts total
- **Done when**: technical prompts registered

#### M7: linking.py — Prompts 26-30
- **Goal**: 5 internal linking prompts
- **Files owned**: `seo_server/prompts/linking.py`
- **Tasks**:
  - [ ] `seo_internal_links_audit(site_url: str)` — #26
  - [ ] `seo_orphan_pages(site_url: str)` — #27
  - [ ] `seo_hub_spoke(url: str)` — #28
  - [ ] `seo_anchor_text_review(site_url: str)` — #29
  - [ ] `seo_link_equity_map(site_url: str)` — #30
- **Tests**: 30 prompts total
- **Done when**: linking prompts registered

### Wave 3 (parallel, after Wave 2) — 3 Domain Modules

#### M8: geo.py — Prompts 31-35
- **Goal**: 5 AI search / GEO prompts
- **Files owned**: `seo_server/prompts/geo.py`
- **Tasks**:
  - [ ] `seo_ai_readiness(url: str)` — #31
  - [ ] `seo_entity_associations(site_url: str)` — #32
  - [ ] `seo_ai_citation_potential(site_url: str)` — #33
  - [ ] `seo_faq_ai_optimization(url: str)` — #34
  - [ ] `seo_brand_mentions(site_url: str, brand: str)` — #35
- **Tests**: 35 prompts total
- **Done when**: GEO prompts registered

#### M9: local_seo.py — Prompts 36-40
- **Goal**: 5 local SEO prompts
- **Files owned**: `seo_server/prompts/local_seo.py`
- **Tasks**:
  - [ ] `seo_local_opportunities(site_url: str, location: str)` — #36
  - [ ] `seo_local_competitors(site_url: str, location: str)` — #37
  - [ ] `seo_local_content(site_url: str, location: str)` — #38
  - [ ] `seo_reviews_audit(site_url: str)` — #39
  - [ ] `seo_multi_location(site_url: str)` — #40
- **Tests**: 40 prompts total
- **Done when**: local SEO prompts registered

#### M10: ecommerce.py — Prompts 41-45
- **Goal**: 5 e-commerce SEO prompts
- **Files owned**: `seo_server/prompts/ecommerce.py`
- **Tasks**:
  - [ ] `seo_product_pages(site_url: str)` — #41
  - [ ] `seo_category_pages(site_url: str)` — #42
  - [ ] `seo_faceted_navigation(site_url: str)` — #43
  - [ ] `seo_product_schema(site_url: str)` — #44
  - [ ] `seo_out_of_stock(site_url: str)` — #45
- **Tests**: 45 prompts total
- **Done when**: e-commerce prompts registered

### Wave 4 (after Wave 3) — Reporting + Final Validation

#### M11: reporting.py — Prompts 46-50
- **Goal**: 5 reporting & planning prompts
- **Files owned**: `seo_server/prompts/reporting.py`
- **Tasks**:
  - [ ] `seo_monthly_report(site_url: str)` — #46
  - [ ] `seo_goal_tracking(site_url: str, goal: str)` — #47
  - [ ] `seo_traffic_value(site_url: str)` — #48
  - [ ] `seo_ranking_velocity(site_url: str)` — #49
  - [ ] `seo_90day_plan(site_url: str)` — #50
- **Tests**: 50 prompts total
- **Done when**: all 50 prompts registered

#### M12: Final validation + CLAUDE.md update
- **Goal**: All 50 prompts pass validation, docs updated
- **Files owned**: `CLAUDE.md`
- **Tasks**:
  - [ ] Run `python -m seo_server.server --test` — verify "50 prompts available"
  - [ ] Run `ruff check seo_server/prompts/` — no lint errors
  - [ ] Run `ruff format seo_server/prompts/` — formatted
  - [ ] Update `CLAUDE.md` Architecture section to include `prompts/` directory
  - [ ] Update MCP Tools table to mention "50 MCP prompts" available
- **Tests**: full lint + test pass, docs accurate
- **Done when**: CLAUDE.md reflects new architecture, all quality gates green

---

## must_haves Verification

| must_have Truth | Verified by | Milestone |
|----------------|-------------|-----------|
| 50 prompts registered in MCP server | `python -m seo_server.server --test` | M12 |
| Each prompt has name, description, tags | `prompts/list` output | M2-M11 |
| Each prompt has typed parameters | FastMCP auto-inference | M2-M11 |
| Each prompt includes tool usage hints | Manual review of prompt content | M2-M11 |
| Prompts organized in 10 thematic modules | File structure | M2-M11 |
| Registration follows existing tool pattern | Code review | M1 |
| No lint/format errors | `ruff check` + `ruff format` | M12 |
| CLAUDE.md updated | File content | M12 |

## Deviation Rules

| Level | Trigger | Permission |
|-------|---------|-----------|
| 1. Bug in existing code | Blocks progress | Auto-fix, note in plan |
| 2. FastMCP API different than expected | Wrong signature | Auto-fix, note in plan |
| 3. Blocking dependency | Import cycle, etc. | Auto-fix, note in plan |
| 4. Architecture change | Different prompt pattern needed | **STOP — ask user** |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FastMCP prompt API edge cases | L | L | Tested in Wave 1 with 5 prompts first |
| Prompt naming collision with tools | L | M | All prompts use `seo_` prefix but distinct names |
| Too many prompts cluttering `prompts/list` | M | L | Tags allow filtering by category |
| Prompt text quality (French) | M | M | Each prompt adapted from validated ChatSEO doc |

## Scope Summary

| Wave | Milestones | New Files | Modified Files | Complexity |
|------|-----------|-----------|----------------|-----------|
| 1 | M1, M2, M3 | 3 | 1 (server.py) | S |
| 2 | M4, M5, M6, M7 | 4 | 0 | S |
| 3 | M8, M9, M10 | 3 | 0 | S |
| 4 | M11, M12 | 1 | 1 (CLAUDE.md) | S |
| **Total** | **12** | **11 new** | **2 modified** | **S** |

Estimated: 50 prompt functions across 10 modules + infrastructure. Each prompt is ~10-15 lines. Total new code: ~700-800 lines.
