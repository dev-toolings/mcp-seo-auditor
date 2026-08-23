# Indexation — Google Indexing API & indexation en masse

> Comment (re)faire indexer des URLs par Google depuis le MCP, via l'outil
> `gsc_manage action="index"`. Deux backends :
> - `provider="google"` → **Google Indexing API** (officiel, mais JobPosting/BroadcastEvent uniquement)
> - `provider="rapid"` → **Rapid URL Indexer** (tiers payant, **marche pour les pages classiques**)
>
> Dernière mise à jour : 22-06-2026

---

## Sommaire

1. [Vue d'ensemble — quelle méthode selon le besoin](#1--vue-densemble--quelle-méthode-selon-le-besoin)
2. [Ce qui marche vraiment (état 2026 + recherche)](#2--ce-qui-marche-vraiment-état-2026--recherche)

**Partie A — Google Indexing API** (`provider="google"`)
3. [À quoi ça sert (et la limite)](#3--à-quoi-ça-sert-et-la-limite)
4. [Coût & quotas](#4--coût--quotas)
5. [Étape 1 — Activer l'API (Google Cloud Console)](#5--étape-1--activer-lapi-google-cloud-console)
6. [Étape 2 — Service account *Owner* (Search Console)](#6--étape-2--service-account-owner-search-console)
7. [Utilisation](#7--utilisation-providergoogle)
8. [Comportement vérifié sur page classique](#8--comportement-vérifié-sur-page-classique)

**Partie B — Rapid URL Indexer** (`provider="rapid"`, pages classiques en masse)
9. [Pourquoi un indexeur tiers & comment ça marche](#9--pourquoi-un-indexeur-tiers--comment-ça-marche)
10. [Setup (compte, clé API, variable d'env)](#10--setup-compte-clé-api-variable-denv)
11. [Utilisation via le MCP](#11--utilisation-via-le-mcp-providerrapid)
12. [Coût & remboursement](#12--coût--remboursement)

**Commun**
13. [Dépannage](#13--dépannage)
14. [Bonnes pratiques](#14--bonnes-pratiques)
15. [Référence rapide](#15--référence-rapide)
16. [Sources](#16--sources)

---

## 1 — Vue d'ensemble — quelle méthode selon le besoin

| Besoin | Méthode | Dans le MCP ? |
|--------|---------|---------------|
| Page **JobPosting / BroadcastEvent** | Google Indexing API | ✅ `provider="google"` |
| **1 page classique** déjà connue | Bouton « Demander indexation » (UI GSC) | ❌ manuel (pas d'API) |
| **Pages classiques en masse** sur Google | **Rapid URL Indexer** (tiers, paiement au succès) | ✅ `provider="rapid"` |
| Couverture **Bing / Yandex** en masse | IndexNow | ❌ (non implémenté — Google ne le supporte pas) |
| Fond de roulement | Sitemap `<lastmod>` à jour + liens internes | ✅ `action="sitemaps" sub_action="submit"` |

---

## 2 — Ce qui marche vraiment (état 2026 + recherche)

Synthèse de la recherche menée le 22-06-2026 (sources en §16) :

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
- **La seule voie programmatique fiable pour des pages classiques en masse = un indexeur
  tiers payant** qui utilise plusieurs méthodes (réseaux de liens, crawl tiers…) et facture
  au succès. C'est ce qu'intègre la Partie B.

---

# Partie A — Google Indexing API (`provider="google"`)

## 3 — À quoi ça sert (et la limite)

Envoie à Google « cette URL a changé/été supprimée » via `urlNotifications:publish`.

> ⚠️ **Officiellement réservé** aux pages `JobPosting` et `BroadcastEvent`. Pour le reste,
> Google accepte l'appel (200) mais ne fait rien de mesurable. N'utilise ce provider que si
> tu as réellement ces types de pages.

## 4 — Coût & quotas

Gratuit. Quotas par projet GCP :

| Quota | Limite |
|-------|--------|
| Publish / jour | **200 URLs** |
| Read / minute (getMetadata) | 60 |
| Requests / minute | 380 |

## 5 — Étape 1 — Activer l'API (Google Cloud Console)

1. [console.cloud.google.com](https://console.cloud.google.com) → projet **`marine-might-440018-f9`**.
2. **APIs & Services → Library** → **« Web Search Indexing API »** → **Enable**.

## 6 — Étape 2 — Service account *Owner* (Search Console)

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

## 7 — Utilisation (`provider="google"`)

```jsonc
// notifier une page (defaults: provider=google, sub_action=notify, index_type=URL_UPDATED)
{ "action": "index", "page_url": "https://exemple.fr/offre-emploi", "index_type": "URL_UPDATED" }

// suppression
{ "action": "index", "page_url": "https://exemple.fr/vieille-offre", "index_type": "URL_DELETED" }

// lot (≤ 200/jour)
{ "action": "index", "urls": ["https://exemple.fr/a", "https://exemple.fr/b"] }

// statut d'une notification
{ "action": "index", "sub_action": "status", "page_url": "https://exemple.fr/offre-emploi" }
```

## 8 — Comportement vérifié sur page classique

Test live du 22-06-2026 sur `https://iautos.fr/flouter-plaque-immatriculation/obligatoire`
(page d'article classique) :

- `publish` → HTTP **200** mais `urlNotificationMetadata` **vide** (pas de `notifyTime`).
- `getMetadata` (sub_action `status`) → **404 « Requested entity was not found »**.

→ Google a **accepté mais ignoré**. C'est le comportement attendu pour une page non
JobPosting/BroadcastEvent. **Conclusion : pour ces pages, passer en Partie B** (ou bouton GSC).

---

# Partie B — Rapid URL Indexer (`provider="rapid"`)

## 9 — Pourquoi un indexeur tiers & comment ça marche

Pour des **pages classiques en masse**, l'unique voie programmatique réellement efficace est
un indexeur tiers. [Rapid URL Indexer](https://rapidurlindexer.com) combine plusieurs méthodes
d'indexation (crawl via sites tiers, signaux de liens…), **facture au succès** (~$0.04/URL
indexée) et **rembourse automatiquement** les URLs non indexées sous 14 jours (taux annoncé
~91 %). Le risque financier est donc plafonné.

> Pré-mortem : c'est un **service externe payant** → dépendance + méthodes « grey-hat ». Le
> modèle paiement-au-succès + refund de-risque l'essai. Ne pas y mettre de pages sensibles si
> la conformité l'interdit. Mesurer (rapport par-URL) avant d'industrialiser.

## 10 — Setup (compte, clé API, variable d'env)

1. Créer un compte sur [rapidurlindexer.com](https://rapidurlindexer.com) et **acheter des crédits**.
2. Récupérer la **clé API** dans le dashboard.
3. Définir la variable d'env (à côté des autres secrets, jamais commitée) :

```bash
RAPID_URL_INDEXER_API_KEY=xxxxxxxxxxxxxxxx
# optionnel (défaut déjà correct) :
# RAPID_URL_INDEXER_BASE_URL=https://rapidurlindexer.com/wp-json
```

Sans cette clé, `provider="rapid"` renvoie une erreur propre (jamais de crash).

## 11 — Utilisation via le MCP (`provider="rapid"`)

```jsonc
// 1) soumettre un lot → renvoie project_id  (page_url et/ou urls, jusqu'à 9 999)
{ "action": "index", "provider": "rapid",
  "urls": ["https://iautos.fr/page-a", "https://iautos.fr/page-b"] }
// → { "success": true, "project_id": 123, "submitted": 2 }

// 2) statut du projet (indexed_links / submitted_links)
{ "action": "index", "provider": "rapid", "sub_action": "status", "project_id": 123 }

// 3) rapport par-URL (indexed / not_indexed) — dispo 96h après soumission
{ "action": "index", "provider": "rapid", "sub_action": "report", "project_id": 123 }

// 4) solde de crédits
{ "action": "index", "provider": "rapid", "sub_action": "credits" }
```

`status` du projet : `pending` → `submitted` → `completed` / `failed` / `refunded`.

## 12 — Coût & remboursement

| Mode | Coût | Remboursement |
|------|------|---------------|
| Standard | 1 crédit / URL | URLs non indexées remboursées après 14 j |
| Apex | 3 crédits / URL | 1 crédit remboursé si non indexée sous 14 j |
| Projet `failed` | — | remboursement intégral |

Rate limit API : **100 requêtes/minute**.

---

# Commun

## 13 — Dépannage

**Google (`provider="google"`)**

| Symptôme | Cause | Correctif |
|----------|-------|-----------|
| `success: true` + `notify_time` renseigné | enregistré (JobPosting/BroadcastEvent) | — |
| `success: true` mais `notify_time: null` + `status` 404 | page classique → Google ignore (vérifié) | passer en `provider="rapid"` ou bouton GSC |
| `403 PERMISSION_DENIED` | SA pas *Owner* / API désactivée | refaire §5 / §6 |
| `429` | quota 200/j atteint | attendre le reset |
| « requires a service account key » | mode OAuth seul | définir `GOOGLE_CREDENTIALS_PATH` |

**Rapid (`provider="rapid"`)**

| Symptôme | Cause | Correctif |
|----------|-------|-----------|
| « RAPID_URL_INDEXER_API_KEY not configured » | clé absente | définir la variable (§10) |
| `401` | clé invalide | vérifier la clé du dashboard |
| `403` | crédits insuffisants | recharger des crédits |
| `425` sur `report` | rapport pas prêt | attendre 96h après la soumission |
| `429` | > 100 req/min | espacer les appels |

## 14 — Bonnes pratiques

- **Choisir le bon provider** : `google` seulement pour JobPosting/BroadcastEvent ; sinon `rapid`.
- **Ne pas spammer** : 1 soumission par URL réellement nouvelle/modifiée.
- **Combiner** avec une re-soumission de sitemap (`action="sitemaps" sub_action="submit"`) — le
  signal de fraîcheur le plus légitime et gratuit.
- **Mesurer** : `report` (rapid) ou `inspect` (GSC) pour vérifier l'indexation réelle avant
  d'investir davantage.
- Réserver les gros lots aux **vraies vagues** d'URLs (migration, nouveau cluster de contenu).

## 15 — Référence rapide

```
GOOGLE (JobPosting/BroadcastEvent) :
  Activer  : Cloud Console (projet marine-might-440018-f9) → Web Search Indexing API → Enable
  Accès    : GSC → SA en Propriétaire (seo-auditor-gsc@marine-might-440018-f9.iam.gserviceaccount.com)
  Appel    : gsc_manage { action:"index", page_url:"…" }              quota 200/j

RAPID (pages classiques, en masse) :
  Setup    : compte rapidurlindexer.com + crédits + RAPID_URL_INDEXER_API_KEY
  Soumettre: gsc_manage { action:"index", provider:"rapid", urls:[…] } → project_id
  Vérifier : gsc_manage { action:"index", provider:"rapid", sub_action:"report", project_id }
  Coût     : ~$0.04/URL indexée, refund auto 14j ; max 9 999 URLs/projet, 100 req/min
```

## 16 — Sources

- [Google — Indexing API quickstart](https://developers.google.com/search/apis/indexing-api/v3/quickstart)
- [Indexing API for Non-Job Pages: A Risky SEO Strategy (alexanderchukovski.com)](https://www.alexanderchukovski.com/is-it-ok-to-use-the-indexing-api-beyond-jobs/)
- [Sight AI — Getting Indexed Faster By Google (2026)](https://www.trysight.ai/blog/getting-indexed-faster-by-google)
- [CrawlWP — IndexNow vs Google Indexing API vs Sitemaps (2026)](https://crawlwp.com/indexnow-vs-google-indexing-api-vs-sitemaps/)
- [Pressonify — Does Google Support IndexNow in 2026?](https://pressonify.ai/blog/indexnow-instant-indexing-press-releases-2026)
- [Rapid URL Indexer — RESTful API](https://rapidurlindexer.com/indexing-api/)
- [Rapid URL Indexer vs IndexMeNow](https://rapidurlindexer.com/indexmenow-alternative/)

Voir aussi : [`GOOGLE_SEARCH_CONSOLE_SETUP.md`](./GOOGLE_SEARCH_CONSOLE_SETUP.md) ·
[`GSC_QUOTAS.md`](./GSC_QUOTAS.md)
