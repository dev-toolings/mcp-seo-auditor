# Indexation : Google Indexing API et pages classiques

> Comment (re)faire indexer des URLs par Google depuis le MCP.
> - `gsc_manage action="index"` : **Google Indexing API** (officiel, JobPosting/BroadcastEvent uniquement)
> - `gsc_manage action="sitemaps" sub_action="submit"` : **pages classiques** (sitemap `<lastmod>` à jour)
> - `gsc_manage action="inspect"` : vérifier l'indexation réelle
>
> Dernière mise à jour : 13-09-2026

---

## Sommaire

1. [Vue d'ensemble : quelle méthode selon le besoin](#1--vue-densemble--quelle-méthode-selon-le-besoin)
2. [Ce qui marche vraiment (état 2026 + recherche)](#2--ce-qui-marche-vraiment-état-2026--recherche)
3. [À quoi sert l'Indexing API (et sa limite)](#3--à-quoi-sert-lindexing-api-et-sa-limite)
4. [Coût et quotas](#4--coût-et-quotas)
5. [Étape 1 : activer l'API (Google Cloud Console)](#5--étape-1--activer-lapi-google-cloud-console)
6. [Étape 2 : service account *Owner* (Search Console)](#6--étape-2--service-account-owner-search-console)
7. [Utilisation](#7--utilisation)
8. [Comportement vérifié sur page classique](#8--comportement-vérifié-sur-page-classique)
9. [Dépannage](#9--dépannage)
10. [Bonnes pratiques](#10--bonnes-pratiques)
11. [Référence rapide](#11--référence-rapide)
12. [Sources](#12--sources)

---

## 1 — Vue d'ensemble : quelle méthode selon le besoin

| Besoin | Méthode | Dans le MCP ? |
|--------|---------|---------------|
| Page **JobPosting / BroadcastEvent** | Google Indexing API | ✅ `action="index"` |
| **1 page classique** déjà connue | Bouton « Demander indexation » (UI GSC) | ❌ manuel (pas d'API) |
| **Pages classiques** nouvelles ou modifiées | Sitemap `<lastmod>` à jour + resoumission + liens internes | ✅ `action="sitemaps" sub_action="submit"` |
| Vérifier l'état d'indexation | URL Inspection API (lecture seule) | ✅ `action="inspect"` |
| Couverture **Bing / Yandex** | IndexNow | ❌ (non implémenté, Google ne le supporte pas) |

---

## 2 — Ce qui marche vraiment (état 2026 + recherche)

Synthèse de la recherche menée le 22-06-2026 (sources en §12) :

- **Google Indexing API ≠ « indexer n'importe quelle page ».** Officiellement limitée à
  `JobPosting` et `BroadcastEvent`. Sur une page classique, Google renvoie `200` mais
  **ignore** la demande (vérifié, voir §8).
- **Pire : ça peut nuire.** Notifier des pages non-emploi signale du contenu « éphémère ».
  Une agence (MiroMind) a vu, après **arrêt** de cet usage, ses impressions doubler
  (~3 000 → 6 000) et ses clics +300 %. John Mueller (Google) : « les spammeurs en abusent,
  tenez-vous-en aux cas d'usage documentés ».
- **IndexNow n'atteint pas Google** (Bing, Yandex, Naver, Seznam seulement).
- **Le bouton « Demander indexation »** de GSC marche sur toute page mais **n'a pas d'API**
  publique (non automatisable proprement).
- **Pour les pages classiques, la voie officielle reste le sitemap** : `<lastmod>` exact,
  resoumis après chaque déploiement, et un maillage interne vers les nouvelles pages. Une page
  « Explorée, actuellement non indexée » relève de la qualité ou du maillage, pas de la
  soumission.

---

## 3 — À quoi sert l'Indexing API (et sa limite)

Envoie à Google « cette URL a changé/été supprimée » via `urlNotifications:publish`.

> ⚠️ **Officiellement réservé** aux pages `JobPosting` et `BroadcastEvent`. Pour le reste,
> Google accepte l'appel (200) mais ne fait rien de mesurable. N'utilise cette action que si
> tu as réellement ces types de pages.

## 4 — Coût et quotas

Gratuit. Quotas par projet GCP :

| Quota | Limite |
|-------|--------|
| Publish / jour | **200 URLs** |
| Read / minute (getMetadata) | 60 |
| Requests / minute | 380 |

## 5 — Étape 1 : activer l'API (Google Cloud Console)

1. [console.cloud.google.com](https://console.cloud.google.com) → projet **`marine-might-440018-f9`**.
2. **APIs & Services → Library** → **« Web Search Indexing API »** → **Enable**.

## 6 — Étape 2 : service account *Owner* (Search Console)

> Rôle **Owner / Propriétaire** requis (≠ Full user). Sur une propriété domaine, utiliser le
> propriétaire **délégué** si « Owner » n'est pas proposé.

1. [Search Console](https://search.google.com/search-console) → propriété → **⚙ Paramètres → Utilisateurs et autorisations**.
2. *Ajouter un utilisateur* → email du SA → **Propriétaire**.
   *(Sinon : Paramètres → Validation de la propriété → Propriétaires → ajouter un propriétaire délégué.)*

```
seo-auditor-gsc@marine-might-440018-f9.iam.gserviceaccount.com
```

> Côté MCP : rien à configurer, le code réutilise la clé SA (`GOOGLE_CREDENTIALS_PATH`) et
> demande le scope `…/auth/indexing` automatiquement.

## 7 — Utilisation

```jsonc
// notifier une page (defaults: sub_action=notify, index_type=URL_UPDATED)
{ "action": "index", "page_url": "https://exemple.fr/offre-emploi", "index_type": "URL_UPDATED" }

// suppression
{ "action": "index", "page_url": "https://exemple.fr/vieille-offre", "index_type": "URL_DELETED" }

// lot (≤ 200/jour)
{ "action": "index", "urls": ["https://exemple.fr/a", "https://exemple.fr/b"] }

// statut d'une notification
{ "action": "index", "sub_action": "status", "page_url": "https://exemple.fr/offre-emploi" }

// pages classiques : resoumettre le sitemap, puis vérifier
{ "action": "sitemaps", "sub_action": "submit", "site_url": "sc-domain:exemple.fr",
  "sitemap_url": "https://exemple.fr/sitemap.xml" }
{ "action": "inspect", "site_url": "sc-domain:exemple.fr",
  "urls": ["https://exemple.fr/a", "https://exemple.fr/b"] }
```

## 8 — Comportement vérifié sur page classique

Test live du 22-06-2026 sur `https://iautos.fr/flouter-plaque-immatriculation/obligatoire`
(page d'article classique) :

- `publish` → HTTP **200** mais `urlNotificationMetadata` **vide** (pas de `notifyTime`).
- `getMetadata` (sub_action `status`) → **404 « Requested entity was not found »**.

→ Google a **accepté mais ignoré**. C'est le comportement attendu pour une page non
JobPosting/BroadcastEvent. **Conclusion : pour ces pages, passer par le sitemap** (ou le
bouton GSC).

---

## 9 — Dépannage

| Symptôme | Cause | Correctif |
|----------|-------|-----------|
| `success: true` + `notify_time` renseigné | enregistré (JobPosting/BroadcastEvent) | aucun |
| `success: true` mais `notify_time: null` + `status` 404 | page classique → Google ignore (vérifié) | resoumettre le sitemap ou bouton GSC |
| `403 PERMISSION_DENIED` | SA pas *Owner* / API désactivée | refaire §5 / §6 |
| `429` | quota 200/j atteint | attendre le reset |
| « requires a service account key » | mode OAuth seul | définir `GOOGLE_CREDENTIALS_PATH` |

## 10 — Bonnes pratiques

- **Choisir la bonne méthode** : `action="index"` seulement pour JobPosting/BroadcastEvent ;
  sinon sitemap.
- **Ne pas spammer** : 1 notification par URL réellement nouvelle/modifiée.
- **Resoumettre le sitemap** (`action="sitemaps" sub_action="submit"`) après chaque
  déploiement : le signal de fraîcheur le plus légitime et gratuit.
- **Mesurer** avec `inspect` (GSC) quelques jours après, pour vérifier l'indexation réelle.

## 11 — Référence rapide

```
GOOGLE INDEXING API (JobPosting/BroadcastEvent) :
  Activer  : Cloud Console (projet marine-might-440018-f9) → Web Search Indexing API → Enable
  Accès    : GSC → SA en Propriétaire (seo-auditor-gsc@marine-might-440018-f9.iam.gserviceaccount.com)
  Appel    : gsc_manage { action:"index", page_url:"…" }              quota 200/j

PAGES CLASSIQUES :
  Soumettre: gsc_manage { action:"sitemaps", sub_action:"submit", site_url, sitemap_url }
  Vérifier : gsc_manage { action:"inspect", site_url, urls:[…] }      quota 2000/j
```

## 12 — Sources

- [Google — Indexing API quickstart](https://developers.google.com/search/apis/indexing-api/v3/quickstart)
- [Indexing API for Non-Job Pages: A Risky SEO Strategy (alexanderchukovski.com)](https://www.alexanderchukovski.com/is-it-ok-to-use-the-indexing-api-beyond-jobs/)
- [Sight AI — Getting Indexed Faster By Google (2026)](https://www.trysight.ai/blog/getting-indexed-faster-by-google)
- [CrawlWP — IndexNow vs Google Indexing API vs Sitemaps (2026)](https://crawlwp.com/indexnow-vs-google-indexing-api-vs-sitemaps/)
- [Pressonify — Does Google Support IndexNow in 2026?](https://pressonify.ai/blog/indexnow-instant-indexing-press-releases-2026)

Voir aussi : [`GOOGLE_SEARCH_CONSOLE_SETUP.md`](./GOOGLE_SEARCH_CONSOLE_SETUP.md) ·
[`GSC_QUOTAS.md`](./GSC_QUOTAS.md)
