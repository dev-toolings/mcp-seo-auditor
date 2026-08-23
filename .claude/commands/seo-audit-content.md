Effectue un audit de contenu approfondi de : **$ARGUMENTS**

## Audit multi-dimensionnel

Lance toutes les analyses en parallele :

1. `seo_analyze(action="content", url="$ARGUMENTS")` — qualite editoriale, lisibilite, densite de mots-cles
2. `seo_analyze(action="structured_data", url="$ARGUMENTS")` — schema markup JSON-LD
3. `seo_analyze(action="eeat", url="$ARGUMENTS")` — signaux E-E-A-T (Experience, Expertise, Autorite, Fiabilite)

## Rapport de sante du contenu

Synthetise un rapport complet avec :

### 1. Score global (/100)
Moyenne ponderee des dimensions analysees.

### 2. Qualite du contenu
- Nombre de mots et adequation au sujet
- Score de lisibilite (Flesch/Kandel-Moles)
- Densite et placement des mots-cles
- Structure des titres (H1/H2/H3)
- Qualite des liens internes et externes

### 3. Signaux E-E-A-T
- Experience : temoignages, exemples concrets
- Expertise : profondeur du contenu, sources citees
- Autorite : auteur identifie, credentials
- Fiabilite : transparence, exactitude, mises a jour

### 4. Donnees structurees
- Schemas presents vs recommandes
- Erreurs de validation
- Eligibilite aux rich snippets

### 5. Recommandations prioritaires
Liste classee par impact (critique, important, mineur) avec actions concretes.

## Prochaines etapes

Demande a l'utilisateur s'il souhaite :
- Optimiser le contenu avec `/seo-optimize $ARGUMENTS`
- Generer de nouveaux meta tags avec `/seo-meta $ARGUMENTS`
- Auditer d'autres pages du site
