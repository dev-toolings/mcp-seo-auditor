Genere des meta tags et titres optimises pour : **$ARGUMENTS**

## Generation

Lance en parallele :

1. `seo_content(action="meta", target_keyword="$ARGUMENTS")` — 5 title tags + 5 meta descriptions avec scoring CTR
2. `seo_content(action="headlines", target_keyword="$ARGUMENTS")` — 10+ variations de titres avec scoring de conversion

Si `$ARGUMENTS` est une URL, utilise-la comme `target_url` pour analyser la page existante. Sinon, traite-la comme un mot-cle.

## Presentation

### Title tags
Presente les 5 propositions dans un tableau :
| # | Title | Longueur | Score CTR | Strategie |
Mets en evidence le meilleur choix.

### Meta descriptions
Meme format tableau avec les 5 propositions.

### Headlines (titres d'article)
Presente les 10+ variations avec :
- Score de conversion (1-10)
- Declencheur emotionnel utilise
- Formule de copywriting (how-to, listicle, question, etc.)
- Usage recommande (blog, landing page, email, social)

### Meilleure combinaison
Recommande la combinaison title + description optimale avec justification.

## Prochaines etapes

Demande a l'utilisateur :
- Quelle combinaison il prefere
- S'il veut rediger un article avec le titre choisi via `/seo-write`
- S'il veut tester d'autres mots-cles
