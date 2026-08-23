# Configuration Google Analytics 4 (MCP externe)

## Cout : GRATUIT

L'API Google Analytics Data API v1 est **gratuite** avec des quotas genereux.
- Pas de facturation requise
- Quota : 10,000 requetes/jour par projet (largement suffisant)
- Le MCP serveur utilise la meme API que l'interface GA4

---

## Prerequis

1. **Node.js 18+** installe (`node --version`)
2. Un compte Google Cloud
3. Une propriete GA4 avec acces (pas Universal Analytics)
4. ~15 minutes de configuration

---

## Option 1 — Auth gcloud CLI (recommande pour dev local)

La methode la plus simple pour le developpement local :

```bash
# Installer gcloud CLI si pas deja fait
# https://cloud.google.com/sdk/docs/install

# Se connecter avec les scopes Analytics
gcloud auth application-default login \
  --scopes="https://www.googleapis.com/auth/analytics.readonly"
```

Cela cree un fichier de credentials dans `~/.config/gcloud/application_default_credentials.json` que le MCP serveur detecte automatiquement via Application Default Credentials (ADC).

> **Note** : il faut quand meme activer l'API Google Analytics Data (etape 2 ci-dessous).

---

## Option 2 — Service Account (production)

### Etape 1 : Creer un projet Google Cloud

1. Aller sur [Google Cloud Console](https://console.cloud.google.com/)
2. Creer un nouveau projet (ou utiliser celui de GSC si deja configure)
   - Nom : `seo-auditor` (ou le projet existant)
3. Selectionner le projet

### Etape 2 : Activer l'API Google Analytics Data

1. **APIs & Services** > **Bibliotheque**
2. Rechercher **"Google Analytics Data API"**
3. Cliquer dessus puis **Activer**

> Attention : il s'agit de "Google Analytics Data API" (v1), pas "Google Analytics API" (v3/UA).

### Etape 3 : Creer un Service Account

1. **APIs & Services** > **Identifiants**
2. **+ Creer des identifiants** > **Compte de service**
3. Remplir :
   - Nom : `ga4-reader`
   - ID : `ga4-reader`
   - Description : `Lecture GA4 pour SEO Auditor`
4. Cliquer **Creer et continuer** > Passer les roles > **OK**
5. Dans la liste, cliquer sur le service account cree
6. Onglet **Cles** > **Ajouter une cle** > **Creer une cle** > **JSON**
7. Le fichier JSON se telecharge

### Etape 4 : Donner acces au Service Account dans GA4

1. Aller sur [Google Analytics](https://analytics.google.com/)
2. **Administration** (roue dentee en bas a gauche)
3. **Gestion des acces de la propriete**
4. **+** > **Ajouter des utilisateurs**
5. Email : coller l'email du service account (visible dans le JSON sous `client_email`)
6. Role : **Lecteur** (suffisant pour les rapports)
7. **Ajouter**

### Etape 5 : Configurer les credentials

```bash
# Placer le fichier JSON dans un emplacement securise
export GOOGLE_APPLICATION_CREDENTIALS="/chemin/vers/ga4-credentials.json"
```

---

## Installation du MCP serveur GA4

```bash
# Cloner le repo
git clone https://github.com/Shin-sibainu/ga4-mcp-server
cd ga4-mcp-server

# Installer les dependances et build
npm install
npm run build
```

Le binaire sera dans `build/index.js`.

---

## Configuration MCP (Claude Code)

Ajouter le serveur GA4 dans `.claude/settings.json` ou `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "ga4": {
      "command": "node",
      "args": ["/chemin/absolu/vers/ga4-mcp-server/build/index.js"],
      "env": {
        "GA4_PROPERTY_ID": "YOUR_PROPERTY_ID"
      }
    }
  }
}
```

### Trouver votre Property ID GA4

1. Aller sur [Google Analytics](https://analytics.google.com/)
2. **Administration** > **Details de la propriete**
3. Le **Property ID** est un nombre (ex: `123456789`)

> Si vous utilisez un service account, ajoutez aussi `"GOOGLE_APPLICATION_CREDENTIALS": "/chemin/vers/ga4-credentials.json"` dans `env`.

---

## Verification

Une fois le MCP configure, tester dans Claude Code :

```
# Lister les comptes GA4 accessibles
→ appeler list_accounts

# Lancer un rapport basique
→ appeler run_report avec votre property ID
```

Si le MCP est correctement configure, les tools GA4 apparaitront dans la liste des tools disponibles.

---

## Tools disponibles (20 tools)

### Basiques

| Tool | Description |
|------|-------------|
| `list_accounts` | Lister les comptes GA4 accessibles |
| `get_property_details` | Details d'une propriete GA4 |
| `run_report` | Rapport personnalise (dimensions, metriques, filtres) |
| `run_realtime_report` | Rapport temps reel (utilisateurs actifs) |
| `get_metadata` | Metadata disponibles (dimensions et metriques) |

### Analyses avancees

| Tool | Description |
|------|-------------|
| `get_traffic_summary` | Resume du trafic (sessions, users, pageviews) |
| `get_traffic_sources` | Sources de trafic (organic, direct, referral, social) |
| `get_top_pages` | Pages les plus visitees |
| `get_device_breakdown` | Repartition par appareil (desktop, mobile, tablet) |
| `get_geo_breakdown` | Repartition geographique des visiteurs |
| `compare_periods` | Comparaison de periodes (ex: mois vs mois precedent) |
| `get_funnel_analysis` | Analyse d'entonnoir de conversion |
| `get_traffic_trends` | Tendances de trafic sur une periode |
| `get_engagement_metrics` | Metriques d'engagement (duree, taux de rebond, pages/session) |
| `get_search_terms` | Termes de recherche interne du site |
| `get_user_segmentation` | Segmentation utilisateurs (nouveaux vs recurrents) |
| `get_conversion_report` | Rapport de conversions / evenements cles |
| `get_landing_pages` | Pages d'atterrissage principales |
| `get_exit_pages` | Pages de sortie principales |
| `get_event_report` | Rapport d'evenements GA4 |

---

## Alternative Python : gomarble-ai

Si vous preferez un MCP en Python (FastMCP, OAuth) :

- Repo : [gomarble-ai/google-analytics-mcp-server](https://github.com/gomarble-ai/google-analytics-mcp-server)
- Avantages : Python natif, auth OAuth integree, plus leger
- Inconvenient : moins de tools (13 vs 20)

```bash
git clone https://github.com/gomarble-ai/google-analytics-mcp-server
cd google-analytics-mcp-server
pip install -r requirements.txt
```

---

## Utilisation avec seo-auditor

Une fois GA4 configure, le slash command **`/seo-analytics`** croise automatiquement les donnees :

- **GSC** (notre MCP seo-auditor) : impressions, clics, CTR, position moyenne
- **GA4** (MCP externe) : sessions, taux de rebond, conversions, sources de trafic

Cette combinaison permet d'identifier :
- Pages a forte visibilite GSC mais faible engagement GA4
- Pages a fort trafic GA4 mais faible CTR organique
- Opportunites d'optimisation croisees

Voir `/seo-analytics <domaine>` pour lancer une analyse croisee.

---

## Securite

- **NE JAMAIS commit** les fichiers de credentials JSON
- Ajouter au `.gitignore` : `*credentials*.json`
- En production, utiliser des secrets (Docker Secrets, Kubernetes, vault)
- Le role **Lecteur** est suffisant — ne jamais donner un acces Editeur

---

## Troubleshooting

### "Permission denied" ou "403"
→ Le service account n'a pas acces a la propriete GA4. Refaire l'etape 4.

### "API not enabled"
→ Activer "Google Analytics Data API" dans Google Cloud Console (pas "Google Analytics API").

### "Property not found"
→ Verifier le Property ID (nombre, pas le Measurement ID qui commence par G-).

### Le MCP ne repond pas
→ Verifier que `npm run build` a reussi et que le chemin dans `args` est correct.
→ Tester manuellement : `node /chemin/vers/ga4-mcp-server/build/index.js`

---

## Ressources

- [Google Analytics Data API v1 — Documentation](https://developers.google.com/analytics/devguides/reporting/data/v1)
- [Shin-sibainu/ga4-mcp-server — GitHub](https://github.com/Shin-sibainu/ga4-mcp-server)
- [gomarble-ai/google-analytics-mcp-server — GitHub](https://github.com/gomarble-ai/google-analytics-mcp-server)
- [Quotas API GA4](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas)
