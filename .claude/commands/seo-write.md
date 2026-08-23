Redige un article SEO complet et optimise sur : **$ARGUMENTS**

## Workflow editorial

### Phase 1 — Recherche
Appelle `seo_content(action="research", target_keyword="$ARGUMENTS", language="fr")` pour obtenir le brief de contenu.

### Phase 2 — Redaction
Appelle `seo_content(action="write", target_keyword="$ARGUMENTS", language="fr", word_count=2500)` pour generer l'article complet.

### Phase 3 — Evaluation
Evalue l'article genere selon ces criteres :
- Structure (H2/H3 logiques et hierarchiques)
- Integration des mots-cles (densite 0.5-1.5%, placement naturel)
- Maillage interne (liens contextuels)
- Signaux E-E-A-T (expertise, experience, sources)
- Lisibilite (phrases courtes, paragraphes aeres)
- Meta tags (title ≤60 chars, description ≤155 chars)

### Phase 4 — Presentation
Presente :
1. L'article complet en markdown
2. Les meta tags (title + description)
3. Un score SEO estime sur 100
4. Les points forts et axes d'amelioration

## Prochaines etapes

Demande a l'utilisateur s'il souhaite :
- Optimiser davantage avec `/seo-optimize`
- Humaniser le texte via `seo_content(action="humanize")`
- Generer des titres alternatifs avec `/seo-meta $ARGUMENTS`
- Modifier le ton, la longueur ou l'angle
