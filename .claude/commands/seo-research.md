Effectue une recherche SEO approfondie sur le mot-cle ou sujet suivant : **$ARGUMENTS**

## Etapes

1. Appelle `seo_content(action="research", target_keyword="$ARGUMENTS", language="fr")` pour generer un brief de contenu complet.

2. Si GSC est configure, appelle aussi `gsc_analytics(action="query", site_url="...", query_filter="$ARGUMENTS", days=90)` pour obtenir les donnees de performance reelles (impressions, clics, CTR, position moyenne).

3. Synthetise un rapport de recherche complet :
   - **Intention de recherche** : informationnelle, navigationnelle, transactionnelle ou commerciale
   - **Analyse du mot-cle** : volume estime, difficulte, variations longue traine
   - **Paysage concurrentiel** : ce que les top resultats couvrent
   - **Opportunites** : angles non couverts, questions sans reponse
   - **Donnees GSC** (si disponibles) : position actuelle, CTR, tendance
   - **Recommandation** : angle editorial suggere, format (guide, liste, comparatif...), longueur cible

4. Si GSC n'est pas configure, indique-le et base l'analyse sur le brief uniquement.

## Prochaines etapes

Demande a l'utilisateur s'il souhaite :
- `/seo-write $ARGUMENTS` pour rediger un article base sur cette recherche
- `/seo-meta $ARGUMENTS` pour generer des meta tags optimises
- Approfondir un aspect specifique de la recherche
