# Brainstorm: Refacto seo-auditor + seomachine fusion

**Date**: 2026-04-10
**Trigger**: Analyse de [TheCraigHewitt/seomachine](https://github.com/TheCraigHewitt/seomachine) — workspace Claude Code orienté content SEO

## Context

**seo-auditor**: 10 tools MCP, ~19k lines, architecture mature (DI, async, multi-LLM). Fort sur audit technique, analytics GSC, AI strategy.

**seomachine**: 24+ slash commands, 10 agents spécialisés, 7 scripts research, système de contexte éditorial (brand voice, style guide), WordPress publishing, GA4 + DataForSEO. Fort sur content creation workflow.

**Gap principal**: seo-auditor n'a pas de pipeline éditorial (création -> optimisation -> publication), pas de GA4, pas de DataForSEO, pas de contexte de marque.

**Overlap**: content brief, competitor gap, SERP analysis, keyword clustering existent des deux côtés.

## Options

### 1. "The Ghost Ship" — Ne rien faire (Completeness: 2/10, Effort: 0)
Garder les deux projets séparés. Zéro risque, mais pas de pipeline intégré.

### 2. "Le Pilleur" — Cherry-pick les prompts (Completeness: 4/10, Effort: S)
Extraire les meilleurs prompts de seomachine (Editor, Meta Creator, Headline Generator) et les ajouter comme templates dans `prompt_templates.py`. Enrichir `seo_strategy` avec de nouvelles actions.

### 3. "Le Scribe" — Nouveau tool `seo_content` (Completeness: 6/10, Effort: M)
11ème tool MCP avec actions: research, write, optimize, meta, humanize. ContentService qui orchestre LLM calls avec système de contexte éditorial (brand voice, style guide depuis config).

### 4. "L'Aspirateur" — Absorber les data sources (Completeness: 7/10, Effort: L)
Intégrer GA4 et DataForSEO comme nouveaux services. GA4 rejoint GSC dans un tool analytics unifié. DataForSEO alimente seo_market et seo_serp avec données compétitives réelles. Ajouter les 7 scripts research comme services.

### 5. "Le Centaure" — Fusion complète (Completeness: 9/10, Effort: XL)
Tout: seo_content, GA4/DataForSEO, contexte éditorial en SQLite, WordPress publisher, seo_editorial orchestrateur, EditorialRepository. Risque de bloat.

### 6. "Le Parasite" — Slash commands Claude Code (Completeness: 5/10, Effort: M)
Workflows éditoriaux comme slash commands dans `.claude/commands/` qui appellent les tools MCP en chaîne. Zero changement au serveur. Lock-in Claude Code.

### 7. "Le Frankenstein" — Hybrid MCP + slash commands (Completeness: 8/10, Effort: L) **[RECOMMENDED]**
Capabilities brutes (content gen, GA4, DataForSEO, research) = services/actions MCP. Workflows éditoriaux = slash commands Claude Code orchestrant les tools MCP. Séparation propre capabilities vs. workflows.

## Tradeoff Matrix

| Critère | Ghost Ship | Pilleur | Scribe | Aspirateur | Centaure | Parasite | Frankenstein |
|---|---|---|---|---|---|---|---|
| Complexité | 0 | XS | M | L | XL | M | L |
| Time to MVP | — | 1j | 3-5j | 5-7j | 3-4 sem | 2-3j | 7-10j |
| Maintenabilité | OK | OK | OK | Moyen | Faible | OK | Moyen |
| Impact utilisateur | 0 | Faible | Moyen | Fort | Tres fort | Moyen | Fort |
| Reversibilité | OK | OK | OK | OK | Risque | OK | OK |
| Completeness | 2/10 | 4/10 | 6/10 | 7/10 | 9/10 | 5/10 | 8/10 |

## Patterns

1. Les prompts sont la vraie valeur de seomachine — pas le code Python
2. Separation capabilities (MCP) vs. workflows (slash commands) est la bonne architecture
3. GA4 + DataForSEO apportent plus de valeur que le content generation seul
4. Le contexte éditorial (brand voice, style guide) est transversal

## Recommendation: "Le Frankenstein" en 3 waves

### Wave 1 (S) — Cherry-pick prompts
- Enrichir `prompt_templates.py` avec les meilleurs prompts seomachine
- Ajouter actions `meta_generate`, `headline_generate`, `content_humanize` sur `seo_strategy`

### Wave 2 (M) — Tool `seo_content` + slash commands
- Nouveau tool MCP `seo_content` (research, write, optimize, meta, humanize)
- ContentService avec brand context system
- Slash commands Claude Code pour workflows éditoriaux

### Wave 3 (L) — Data sources
- GA4 service (optionnel, service account)
- DataForSEO service (optionnel, API key)
- Research analytics services (quick wins, trending, topic clusters)

## Next Steps

- `/spec refacto-frankenstein` pour spécifier wave 1+2
- `/plan refacto-frankenstein` pour le plan d'implémentation
