# Google Search Console API — Quotas & Rate Limits

Source : https://developers.google.com/webmaster-tools/limits

## Quotas officiels (juin 2025)

| Limite                                    | Valeur          |
|-------------------------------------------|-----------------|
| Queries per day                           | 100 000 000     |
| Requests per minute (global)              | 60              |
| Requests per minute per user              | 60              |
| Queries per minute per user               | 1 200           |
| Low rate user request limit per minute    | 10              |

### Qu'est-ce que "low rate" ?

Les endpoints a quota reduit (10 RPM) :
- **URL Inspection** (`urlInspection.index.inspect`)
- **Sites add/delete** (`sites.add`, `sites.delete`)

Les endpoints standard (60 RPM) :
- `searchanalytics.query` (performance, top pages, queries, cannibalization)
- `sitemaps.list`, `sitemaps.get`, `sitemaps.submit`
- `sites.list`, `sites.get`

## Implementation dans le MCP server

Le service `GoogleSearchConsoleService` utilise un rate limiter async sliding-window :

| Limiter               | Defaut | Variable .env          | Endpoints                    |
|-----------------------|--------|------------------------|------------------------------|
| `_rate_limiter`       | 50 RPM | `GSC_REQUESTS_PER_MINUTE` | Tous les appels standard  |
| `_inspection_limiter` | 8 RPM  | `GSC_INSPECTION_RPM`      | inspect_url, batch_inspect |

Les valeurs par defaut sont en dessous des limites officielles (marge de securite).

### Comportement

- Sliding window de 60 secondes
- Quand la limite est atteinte, le prochain appel attend (`asyncio.sleep`)
- Pas de rejet — les requetes sont mises en file d'attente
- Log `DEBUG` quand un sleep est declenche
- Le retry existant (`tenacity`, 3 tentatives, backoff exponentiel) gere les erreurs 429 residuelles

### Exemple : batch inspection de 20 URLs

Avec le limiter a 8 RPM :
- URLs 1-8 : executees immediatement (~1s chacune)
- URLs 9-16 : en attente, executees a partir de ~60s
- URLs 17-20 : executees a partir de ~120s
- Temps total : ~2.5 min (vs crash 429 sans limiter)

## Tuning

Pour augmenter les limites (si le projet Google Cloud a un quota eleve) :

```env
GSC_REQUESTS_PER_MINUTE=60
GSC_INSPECTION_RPM=10
```

Pour reduire (si plusieurs instances partagent le meme service account) :

```env
GSC_REQUESTS_PER_MINUTE=25
GSC_INSPECTION_RPM=4
```
