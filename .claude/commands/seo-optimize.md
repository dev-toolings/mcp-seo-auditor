Optimise le contenu SEO de la page suivante : **$ARGUMENTS**

## Workflow d'optimisation

### Phase 1 — Analyse
Lance les analyses en parallele :
- `seo_analyze(action="content", url="$ARGUMENTS")` — qualite du contenu, lisibilite, mots-cles
- `seo_analyze(action="technical", url="$ARGUMENTS")` — aspects techniques (meta, headings, images)

### Phase 2 — Optimisation
A partir des resultats d'analyse, appelle `seo_content(action="optimize", content="<contenu extrait>", target_keyword="<mot-cle principal detecte>")` pour generer une version optimisee.

### Phase 3 — Comparaison
Presente un rapport avant/apres :
- **Score avant** vs **Score apres**
- **Changements effectues** : liste detaillee (titres, mots-cles, structure, liens, lisibilite)
- **Version optimisee** du contenu

### Phase 4 — Meta tags
Propose de generer des meta tags optimises : `seo_content(action="meta", target_url="$ARGUMENTS")`.

## Prochaines etapes

Demande a l'utilisateur :
- S'il veut appliquer les changements
- S'il souhaite aussi un audit E-E-A-T via `/seo-audit-content $ARGUMENTS`
- S'il veut humaniser le contenu optimise
