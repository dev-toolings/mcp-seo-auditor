# Plan: "Le Frankenstein" — SEO Machine Fusion

**Source**: `docs/brainstorms/BRAINSTORM-seomachine-fusion.md`
**Date**: 2026-04-10
**Scope**: Absorber les meilleures capacites de seomachine dans seo-auditor

## Architecture

```
                     Claude Code user
                           |
              +------------+------------+
              |                         |
       Slash Commands              MCP stdio
    (.claude/commands/)                 |
       workflows                  seo_server/
       orchestration              tools/ (11 tools)
              |                         |
              +-----> seo_content <-----+   (NEW tool)
              +-----> seo_strategy <----+   (enrichi)
                           |
                    app/services/
                    +-- ai/content_writer.py      (NEW)
                    +-- ai/content_optimizer.py   (NEW)
                    +-- ai/meta_generator.py      (NEW)
                    +-- editorial/context.py      (NEW)
                    +-- llm/prompt_templates.py   (enrichi)
```

## Key Decisions

### Decision: Nouveau tool `seo_content` vs. enrichir `seo_strategy`
**Options**: A) Tout dans seo_strategy  B) Nouveau tool seo_content  C) Split les deux
**Pick**: C — actions analytiques (content_brief, content_plan) restent dans seo_strategy, actions generatives (write, optimize, meta, humanize) dans seo_content
**Why**: seo_strategy fait de l'analyse et du planning. La generation de contenu est un use case different avec des inputs differents (brand context, style guide). Separer evite un tool a 10+ actions.
**One-way door?**: Non — on peut fusionner/splitter plus tard.

### Decision: Brand context — fichiers ou SQLite
**Options**: A) Fichiers markdown dans `context/`  B) SQLite  C) Env vars
**Pick**: A — fichiers markdown dans un repertoire configurable via `EDITORIAL_CONTEXT_DIR`
**Why**: Meme approche que seomachine. Les fichiers sont editables par l'utilisateur, versionnables, lisibles. SQLite serait over-engineering pour du texte statique.
**One-way door?**: Non — migrer vers SQLite plus tard si besoin.

### Decision: Slash commands — MCP-first ou prompt-only
**Options**: A) Prompts purs (comme seomachine)  B) Prompts qui appellent nos MCP tools
**Pick**: B — les slash commands sont des orchestrateurs qui appellent les tools MCP
**Why**: Les tools MCP font le travail lourd (crawl, LLM, analytics). Les slash commands enchainent les appels avec du contexte utilisateur. Pas de duplication de logique.
**One-way door?**: Non.

### Decision: DataForSEO / GA4 — maintenant ou plus tard
**Options**: A) Wave 1  B) Wave 3  C) Jamais
**Pick**: B — Wave 4, optionnel
**Why**: Les data sources tierces ajoutent de la valeur mais sont complexes. Le content pipeline apporte plus de valeur immediate. On les decouple.
**One-way door?**: Non.

### Decision: GA4 — service interne ou MCP externe
**Options**: A) Coder un GA4AnalyticsService interne  B) Utiliser un MCP GA4 externe  C) Les deux
**Pick**: B — utiliser `Shin-sibainu/ga4-mcp-server` (TypeScript, 20 tools, MIT, gcloud auth ou service account)
**Why**: Un MCP GA4 dédié existe déjà avec 20 tools (traffic, sources, device, geo, funnel, realtime, comparisons). Le coder nous-mêmes serait du NIH. On configure le MCP externe comme on fait pour `chrome-devtools`. Les slash commands peuvent orchestrer les deux MCP.
**Ref**: https://github.com/Shin-sibainu/ga4-mcp-server (TypeScript, Node 18+, stdio)
**Alternative**: https://github.com/gomarble-ai/google-analytics-mcp-server (Python, FastMCP, OAuth, 13 stars)
**One-way door?**: Non — on peut toujours internaliser plus tard si le MCP externe ne suffit pas.

---

## Waves

### Wave 1 (parallel) — Prompts + Editorial Context + Schema fondations

**Theme**: Poser les fondations — prompts seomachine, systeme de contexte editorial, schema du nouveau tool.

#### M1: Prompt Templates enrichis
- **Goal**: Les meilleurs prompts de seomachine sont disponibles dans notre systeme LLM
- **Files owned**:
  - `app/services/llm/prompt_templates.py` (modified)
- **Tasks**:
  - [ ] Ajouter `build_meta_generation_prompt(page_data, brand_context)` — genere 5 title + 5 descriptions avec scoring CTR
  - [ ] Ajouter `build_headline_generation_prompt(topic, keywords, brand_context)` — 10+ variations avec conversion scoring
  - [ ] Ajouter `build_content_humanize_prompt(content, style_guide)` — suppression patterns IA, ton naturel
  - [ ] Ajouter `build_content_write_prompt(brief, brand_context, style_guide, internal_links)` — generation article 2000-3000 mots
  - [ ] Ajouter `build_content_optimize_prompt(content, seo_analysis, keywords)` — pass d'optimisation SEO
  - [ ] Ajouter `SYSTEM_PROMPT_CONTENT_WRITER` — persona distinct du SEO analyst (ecrivain, pas auditeur)
- **Tests**: `tests/test_prompt_templates_content.py` — chaque builder retourne un string non-vide, contient les sections attendues, injecte le brand context si fourni
- **Done when**: 6 nouveaux builders disponibles, tous testes

#### M2: Editorial Context System
- **Goal**: Le systeme charge et expose le contexte editorial (brand voice, style guide, internal links) depuis des fichiers markdown
- **Files owned**:
  - `app/services/editorial/__init__.py` (new)
  - `app/services/editorial/context.py` (new)
  - `app/core/config.py` (modified — ajout `EDITORIAL_CONTEXT_DIR`)
  - `context/` directory templates (new)
- **Tasks**:
  - [ ] Ajouter `EDITORIAL_CONTEXT_DIR: str = ""` dans `Settings` (`app/core/config.py`)
  - [ ] Creer `EditorialContextService` dans `app/services/editorial/context.py`:
    - `load() -> EditorialContext` — charge tous les fichiers du repertoire
    - `get_brand_voice() -> str` — contenu de `brand-voice.md`
    - `get_style_guide() -> str` — contenu de `style-guide.md`
    - `get_internal_links() -> str` — contenu de `internal-links-map.md`
    - `get_target_keywords() -> str` — contenu de `target-keywords.md`
    - `get_full_context() -> dict` — tout agrege
  - [ ] Creer templates vides dans `context/` : `brand-voice.md`, `style-guide.md`, `internal-links-map.md`, `target-keywords.md`, `competitor-analysis.md`
  - [ ] Ajouter le service dans `service_context.py` : `self._editorial_context = None` + lazy property
- **Tests**: `tests/test_editorial_context.py` — charge depuis un tmpdir, gere fichiers manquants gracieusement, retourne `""` si `EDITORIAL_CONTEXT_DIR` non configure
- **Done when**: `svc.ctx.editorial_context.get_full_context()` retourne un dict avec le contenu des fichiers

#### M3: Schema `seo_content` + Action Router skeleton
- **Goal**: Le schema d'input et le squelette du tool sont prets (actions retournent des stubs)
- **Files owned**:
  - `seo_server/schemas/content.py` (new)
  - `seo_server/tools/content.py` (new — skeleton only)
- **Tasks**:
  - [ ] Creer `SeoContentInput(MCPInput)` dans `seo_server/schemas/content.py`:
    - `action: Literal["write", "optimize", "meta", "humanize", "research"]`
    - `target_url: SafeUrl | None = None`
    - `target_keyword: str = ""`
    - `content: str = ""` (pour optimize/humanize — texte a traiter)
    - `language: str = "fr"`
    - `tone: str = ""` (override du brand voice)
    - `word_count: int = 2500`
  - [ ] Creer `seo_server/tools/content.py` avec `@mcp.tool(name="seo_content")` + action router (`if/elif` sur action). Chaque branche retourne `{"status": "not_implemented", "action": action}` pour l'instant.
- **Tests**: `tests/test_content_schema.py` — validation des inputs, coercion JSON string, actions invalides rejetees
- **Done when**: `seo_content` est enregistre comme tool MCP, le schema valide, les actions retournent des stubs

---

### Wave 2 (after Wave 1) — Content Services + Tool wiring

**Theme**: Implementer les services de contenu et les brancher sur le tool `seo_content`.

#### M4: ContentWriter + ContentOptimizer services
- **Goal**: Les services de generation et d'optimisation de contenu fonctionnent avec le LLM
- **Files owned**:
  - `app/services/ai/content_writer.py` (new)
  - `app/services/ai/content_optimizer.py` (new)
  - `seo_server/service_context.py` (modified — ajout 2 services)
- **Tasks**:
  - [ ] Creer `ContentWriterService(ai_analyzer, editorial_context)` dans `content_writer.py`:
    - `async write(target_keyword, target_url, language, tone, word_count) -> dict` — charge le brief existant via `content_brief.generate()`, injecte brand context + style guide + internal links, appelle LLM via `build_content_write_prompt()`, retourne `{"article": str, "meta": dict, "word_count": int, "ai_enhanced": bool}`
    - `async humanize(content, style_guide_override) -> dict` — passe de desAIification via `build_content_humanize_prompt()`
    - Fallback deterministe : retourne le brief structure si LLM indisponible
  - [ ] Creer `ContentOptimizerService(ai_analyzer, editorial_context)` dans `content_optimizer.py`:
    - `async optimize(content, keywords, seo_analysis) -> dict` — analyse le contenu, applique les recommandations SEO via `build_content_optimize_prompt()`, retourne `{"optimized_content": str, "changes": list, "score_before": float, "score_after": float}`
    - Utilise `TokenBudget.prepare_audit_data()` pour le contenu long
  - [ ] Enregistrer les deux services dans `service_context.py` avec lazy init
- **Tests**: `tests/test_content_writer.py`, `tests/test_content_optimizer.py` — test mode deterministe (sans LLM), structure des retours, gestion content vide/long
- **Done when**: `svc.ctx.content_writer.write(...)` et `svc.ctx.content_optimizer.optimize(...)` retournent des resultats structures

#### M5: MetaGenerator service
- **Goal**: Generation de meta titles + descriptions avec scoring, inspires de seomachine Meta Creator
- **Files owned**:
  - `app/services/ai/meta_generator.py` (new)
- **Tasks**:
  - [ ] Creer `MetaGeneratorService(ai_analyzer, editorial_context)` dans `meta_generator.py`:
    - `async generate_meta(target_url, target_keyword, page_data) -> dict` — genere 5 titles (max 60 chars) + 5 descriptions (max 155 chars) avec CTR scoring via `build_meta_generation_prompt()`
    - `async generate_headlines(topic, keywords) -> dict` — 10+ headline variations avec conversion scoring via `build_headline_generation_prompt()`
    - Fallback deterministe : templates basiques avec keyword insertion
  - [ ] Enregistrer dans `service_context.py`
- **Tests**: `tests/test_meta_generator.py` — fallback deterministe, structure des retours, limites de longueur respectees
- **Done when**: Meta generation fonctionnelle avec et sans LLM

#### M6: Wire tool `seo_content` actions
- **Goal**: Toutes les actions du tool sont branchees sur les vrais services
- **Files owned**:
  - `seo_server/tools/content.py` (modified — remplacer stubs)
- **Tasks**:
  - [ ] Action `write` : appelle `svc.ctx.content_writer.write()` avec les params de l'input
  - [ ] Action `optimize` : appelle `svc.ctx.content_optimizer.optimize()`, utilise `svc.ctx.crawler` pour analyser `target_url` si fourni
  - [ ] Action `meta` : appelle `svc.ctx.meta_generator.generate_meta()`, crawl `target_url` pour les page_data
  - [ ] Action `humanize` : appelle `svc.ctx.content_writer.humanize()`
  - [ ] Action `research` : redirige vers `svc.ctx.content_brief.generate()` (deja existant) enrichi du editorial context
  - [ ] Ajouter `headlines` comme action bonus : `svc.ctx.meta_generator.generate_headlines()`
  - [ ] Mettre a jour le `Literal` dans le schema pour inclure `headlines`
- **Tests**: `tests/test_tool_content.py` — test d'integration du tool complet, chaque action retourne le bon format
- **Done when**: `seo_content(action="write", target_keyword="...")` retourne un article complet

---

### Wave 3 (after Wave 2) — Slash Commands + Strategy enrichment

**Theme**: Workflows editoriaux via slash commands, enrichissement de seo_strategy.

#### M7: Slash Commands editoriaux
- **Goal**: Les workflows seomachine sont disponibles comme slash commands Claude Code
- **Files owned**:
  - `.claude/commands/seo-write.md` (new)
  - `.claude/commands/seo-research.md` (new)
  - `.claude/commands/seo-optimize.md` (new)
  - `.claude/commands/seo-audit-content.md` (new)
  - `.claude/commands/seo-meta.md` (new)
- **Tasks**:
  - [ ] `/seo-research [keyword]` — appelle `seo_content(action="research")` + `gsc_analytics(action="query")` pour le keyword, synthetise un brief complet
  - [ ] `/seo-write [keyword]` — enchaine: research brief → `seo_content(action="write")` → `seo_analyze(action="content")` pour scorer → affiche article + score
  - [ ] `/seo-optimize [url]` — enchaine: `seo_analyze(action="content")` + `seo_analyze(action="technical")` → `seo_content(action="optimize")` avec les findings → affiche diff
  - [ ] `/seo-audit-content [url]` — equivalent de `/analyze-existing` de seomachine: crawl + content analysis + meta analysis + readability + recommendations
  - [ ] `/seo-meta [url] [keyword]` — appelle `seo_content(action="meta")` + `seo_content(action="headlines")`, presente les variations avec scores
- **Tests**: Verification manuelle (les slash commands sont des prompts, pas du code testable unitairement). Documenter les exemples d'usage.
- **Done when**: Les 5 slash commands sont fonctionnelles et documentees

#### M8: Enrichir `seo_strategy` avec actions seomachine
- **Goal**: seo_strategy gagne les actions `priorities` et `quick_wins` inspirees de seomachine
- **Files owned**:
  - `seo_server/tools/strategy.py` (modified)
  - `seo_server/schemas/strategy.py` (modified)
  - `app/services/ai/priorities.py` (new)
- **Tasks**:
  - [ ] Creer `PrioritiesService(ai_analyzer, gsc_service)` dans `priorities.py`:
    - `async quick_wins(site_url) -> dict` — identifie les pages position 11-20 (striking distance), CTR faible, contenu declinant. Inspire de `research_quick_wins.py` de seomachine
    - `async priority_matrix(site_url) -> dict` — matrice effort/impact pour les actions SEO. Inspire de `research_priorities_comprehensive.py`
  - [ ] Ajouter `"priorities"` et `"quick_wins"` au `Literal` de `SeoStrategyInput`
  - [ ] Brancher les nouvelles actions dans le router de `strategy.py`
  - [ ] Enregistrer `PrioritiesService` dans `service_context.py`
- **Tests**: `tests/test_priorities.py` — quick wins avec mock GSC data, priority matrix structure
- **Done when**: `seo_strategy(action="quick_wins", site_url="...")` retourne des opportunites classees

---

### Wave 4 (optional, after Wave 3) — Data Sources externes

**Theme**: GA4 + DataForSEO comme services optionnels.

#### M9: GA4 via MCP externe (optional)
- **Goal**: Donnees GA4 accessibles via un MCP server externe (comme chrome-devtools)
- **Files owned**:
  - `.claude/settings.json` ou `claude_desktop_config.json` (modified — ajout MCP ga4)
  - `.claude/commands/seo-analytics.md` (new — slash command orchestrant GSC + GA4)
  - `docs/GA4_SETUP.md` (new — guide d'installation)
- **Ref**: [Shin-sibainu/ga4-mcp-server](https://github.com/Shin-sibainu/ga4-mcp-server) — 20 tools, TypeScript, stdio, MIT
- **Alternative**: [gomarble-ai/google-analytics-mcp-server](https://github.com/gomarble-ai/google-analytics-mcp-server) — Python, FastMCP, OAuth, 13 stars
- **Tasks**:
  - [ ] Documenter l'installation du MCP GA4 externe (`bun install`, `gcloud auth`, config MCP)
  - [ ] Ajouter la config MCP dans les settings Claude Code (meme pattern que chrome-devtools)
  - [ ] Creer slash command `/seo-analytics [url]` qui orchestre `gsc_analytics` (notre MCP) + tools GA4 (MCP externe) pour une vue unifiee
  - [ ] Tester l'integration end-to-end avec un GA4 property de test
- **Tests**: Test d'integration manuelle (MCP externe = pas de tests unitaires internes)
- **Done when**: `/seo-analytics` retourne des donnees croisees GSC + GA4

#### M10: DataForSEO Service (optional)
- **Goal**: Donnees competitives reelles via DataForSEO API
- **Files owned**:
  - `app/services/dataforseo/__init__.py` (new)
  - `app/services/dataforseo/client.py` (new)
  - `app/core/config.py` (modified — ajout `DATAFORSEO_*` vars)
  - `seo_server/tools/market.py` (modified — enrichir avec donnees reelles)
  - `seo_server/tools/serp.py` (modified — enrichir live SERP)
- **Tasks**:
  - [ ] Ajouter `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` dans Settings
  - [ ] Creer `DataForSEOClient` : keyword volumes, SERP features, competitor rankings
  - [ ] Enrichir `seo_market` et `seo_serp` avec les donnees DataForSEO quand disponibles
  - [ ] Fallback sur le comportement actuel si pas configure
- **Tests**: Tests avec mock API responses
- **Done when**: `seo_serp(action="live")` utilise DataForSEO si configure

---

## must_haves Verification

| Truth | Verified by | Milestone |
|---|---|---|
| Les prompts seomachine sont integres dans notre LLM stack | `tests/test_prompt_templates_content.py` | M1 |
| Le brand context est chargeable depuis des fichiers | `tests/test_editorial_context.py` | M2 |
| `seo_content` est un tool MCP fonctionnel | `tests/test_content_schema.py` | M3 |
| On peut generer un article SEO complet via MCP | `tests/test_tool_content.py` action=write | M6 |
| On peut optimiser du contenu existant via MCP | `tests/test_tool_content.py` action=optimize | M6 |
| On peut generer des meta tags avec scoring | `tests/test_meta_generator.py` | M5 |
| Les workflows editoriaux sont disponibles en slash commands | Verification manuelle | M7 |
| quick_wins identifie les opportunites striking distance | `tests/test_priorities.py` | M8 |
| GA4 est accessible via MCP externe + slash command | Test integration manuelle | M9 |
| DataForSEO est integrable optionnellement | `tests/test_dataforseo.py` | M10 |

## Deviation Rules

| Level | Trigger | Permission |
|---|---|---|
| 1. Bug in existing code | Blocks progress | Auto-fix, note in plan |
| 2. Missing validation/security | Critical gap | Auto-fix, note in plan |
| 3. Blocking dependency | Can't continue | Auto-fix, note in plan |
| 4. Architecture change | Structural shift | **STOP — ask user** |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Token budget insuffisant pour articles 3000 mots | M | M | `max_tokens` override comme `generate_content_plan`, chunking si necessaire |
| Brand context trop volumineux pour le prompt | L | M | Truncate avec `TokenBudget`, extraire les sections pertinentes |
| Qualite des articles generes insuffisante | M | H | Prompts iteratifs, scoring auto via `seo_analyze`, humanize pass |
| GA4 MCP externe instable | M | L | Wave 4, optionnel, alternative gomarble-ai si besoin |
| DataForSEO cout API | M | L | Optionnel, caching agressif |

## Scope Summary

| Wave | Milestones | New Files | Modified Files | Complexity |
|---|---|---|---|---|
| 1 | M1, M2, M3 | 6 | 2 | S |
| 2 | M4, M5, M6 | 3 | 2 | M |
| 3 | M7, M8 | 6 | 3 | M |
| 4 | M9, M10 | 3 | 1 | M |
| **Total** | **10** | **18 files** | **8 files** | |

## Confidence: 88%

Plan solide pour les Waves 1-3. La Wave 4 (GA4/DataForSEO) a plus d'inconnues (APIs tierces, auth) mais est optionnelle et decouplable.

Incertitudes restantes:
- Qualite des articles generes (iteratif, pas planifiable)
- Token budget pour contenu long (testable rapidement en Wave 2)

**Dis "go" pour lancer la Wave 1.**
