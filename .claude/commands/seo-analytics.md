Analyse croisee GSC + GA4 pour : **$ARGUMENTS**

Utilise le domaine ou l'URL fourni pour croiser les donnees Google Search Console (notre MCP seo-auditor) et Google Analytics 4 (MCP externe ga4, si configure).

## Phase 1 — Donnees GA4

Si le MCP GA4 est disponible :
1. Appelle `get_traffic_sources` pour les sources de trafic (28 derniers jours)
2. Appelle `get_page_views` pour les pages les plus vues
3. Appelle `run_report` avec les dimensions `pagePath`, `sessionSource` et les metriques `sessions`, `engagementRate`, `conversions` sur 28 jours

Si le MCP GA4 n'est PAS configure :
- Indique : "GA4 non configure. Voir `docs/GA4_SETUP.md` pour l'installation du MCP GA4."
- Continue avec les donnees GSC uniquement.

## Phase 2 — Donnees GSC

Appelle les tools seo-auditor :
1. `gsc_analytics(action="query", site_url="$ARGUMENTS", days=28)` — top queries (clics, impressions, CTR, position)
2. `gsc_analytics(action="ai_queries", site_url="$ARGUMENTS")` — queries liees aux moteurs IA (si disponible)

## Phase 3 — Analyse croisee

Si les deux sources sont disponibles, identifie :
- **Pages a fort trafic GA4 mais faible CTR GSC** : le contenu attire du trafic direct/referral mais n'est pas optimise pour la recherche
- **Pages a forte impression GSC mais peu de sessions GA4** : bon positionnement mais probleme de CTR ou de taux de rebond
- **Sources de trafic principales** et leur correlation avec les performances organiques
- **Pages en croissance** vs **en declin** dans les deux sources
- **Opportunites de conversion** : pages avec bon trafic organique mais faible engagement GA4

## Phase 4 — Rapport unifie

Presente un rapport structure :

### Vue d'ensemble
- Trafic organique (GSC) vs trafic total (GA4)
- Top 10 pages par performance croisee
- Top 10 queries GSC avec correlation GA4

### Opportunites identifiees
Classees par priorite (impact estime) :
1. Quick wins CTR
2. Pages a optimiser pour le SEO
3. Contenu a creer (gaps)

### Recommandations
3-5 actions concretes avec impact estime.

## Prochaines etapes

Demande a l'utilisateur s'il souhaite :
- Approfondir une page specifique avec `/seo-audit-content [url]`
- Identifier les quick wins avec `seo_strategy(action="quick_wins", site_url="$ARGUMENTS")`
- Optimiser les pages prioritaires avec `/seo-optimize [url]`
