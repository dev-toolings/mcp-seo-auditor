# Installation SEO Auditor — Guide complet

Guide d'installation de SEO Auditor : MCP server Python + Google Search Console.

---

## 1. Pre-requis

| Outil      | Version    | Verification                |
|------------|------------|-----------------------------|
| Python     | 3.11+      | `python3 --version`         |
| Git        | any        | `git --version`             |
| Navigateur | Chrome/FF  | pour OAuth GSC (optionnel)  |

---

## 2. Cloner et installer le MCP server

```bash
git clone https://github.com/dev-toolings/mcp-seo-auditor.git
cd mcp-seo-auditor

# Virtualenv + deps Python
cd packages/mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download fr_core_news_sm

# Verifier
make mcp-test
```

---

## 3. Configurer l'environnement

```bash
cp .env.example .env
```

Editer `.env` — les variables essentielles :

```env
# Site cible par defaut
DEFAULT_SITEMAP_URL=https://monsite.fr/sitemap.xml
DEFAULT_BASE_URL=https://monsite.fr

# LLM (optionnel — active les outils AI)
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-xxx
LLM_MODEL=claude-sonnet-4-20250514

# GSC (optionnel — voir section 5)
GOOGLE_CREDENTIALS_PATH=credentials/google-credentials.json
```

---

## 4. Connecter a Claude Code

Ajouter dans `.mcp.json` (racine du projet ou `~/.claude/claude_code_config.json`) :

```json
{
  "mcpServers": {
    "seo-auditor": {
      "command": "/chemin/absolu/packages/mcp-server/.venv/bin/python",
      "args": ["-m", "seo_server.server"],
      "cwd": "/chemin/absolu/packages/mcp-server"
    }
  }
}
```

> Remplacer `/chemin/absolu/` par le vrai chemin du repo.

Verifier dans Claude Code : les outils `seo_audit`, `seo_analyze`, `gsc_manage`, etc. doivent apparaitre.

---

## 5. Google Search Console (optionnel)

GSC permet d'acceder aux donnees de performance reelles (clics, impressions, CTR, position).

### Deux modes d'authentification

| Mode              | Usage                          | Recommandation         |
|-------------------|--------------------------------|------------------------|
| **Service Account** | Serveur, CLI, Docker, headless | **Recommande**         |
| **OAuth 2.0**     | Dev local avec navigateur      | Fallback si SA bloque  |

> Le service account est plus fiable : pas de navigateur requis, pas de token a renouveler manuellement.

---

### 5A. Service Account (recommande)

#### Etape 1 — Creer un projet Google Cloud (si pas deja fait)

1. Ouvrir https://console.cloud.google.com/projectcreate
2. Nom : `seo-auditor` (ou existant)
3. Creer

#### Etape 2 — Activer l'API Search Console

1. Ouvrir https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
2. Selectionner le bon projet en haut
3. Cliquer **Activer** (Enable)

> **IMPORTANT** : l'API doit etre activee dans le meme projet que le service account.
> Si le message d'erreur mentionne un project ID different, verifier le selecteur de projet.

#### Etape 3 — Creer le Service Account

1. Ouvrir https://console.cloud.google.com/iam-admin/serviceaccounts
2. **+ Creer un compte de service**
3. Nom : `seo-auditor-gsc`
4. Cliquer **Creer et continuer** → passer les roles → **OK**
5. Dans la liste, cliquer sur le compte cree
6. Onglet **Cles** → **Ajouter une cle** → **Creer une cle** → **JSON**
7. Le fichier `.json` se telecharge

#### Etape 4 — Placer le fichier credentials

```bash
# Le dossier credentials/ est deja gitignore
mkdir -p packages/mcp-server/credentials

# Copier et renommer le fichier telecharge
cp ~/Downloads/<nom-du-fichier>.json packages/mcp-server/credentials/google-credentials.json
```

Le fichier doit ressembler a :

```json
{
  "type": "service_account",
  "project_id": "mon-projet-123",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "seo-auditor-gsc@mon-projet-123.iam.gserviceaccount.com",
  "client_id": "...",
  ...
}
```

#### Etape 5 — Ajouter le service account a GSC

1. Ouvrir https://search.google.com/search-console
2. Selectionner la propriete cible (ex: `iautos.fr`)
3. **Settings** → **Users and permissions** → **Add user**
4. Coller l'email du `client_email` du JSON (ex: `seo-auditor-gsc@mon-projet.iam.gserviceaccount.com`)
5. Permission : **Full**
6. **Add**

#### Etape 6 — Configurer .env

```env
GOOGLE_CREDENTIALS_PATH=credentials/google-credentials.json
```

#### Etape 7 — Tester

```bash
# Via Claude Code — lister les sites accessibles
# Utiliser l'outil : gsc_manage(action="sites", sub_action="list")
```

Si tout est OK, la reponse liste les proprietes GSC accessibles au service account.

---

### 5B. OAuth 2.0 (alternative)

A utiliser si le service account pose probleme ou pour un usage dev local rapide.

#### Etape 1 — Creer les identifiants OAuth

1. Meme projet Google Cloud (API deja activee)
2. Ouvrir https://console.cloud.google.com/apis/credentials
3. **+ Creer des identifiants** → **ID client OAuth**
4. Type : **Application de bureau**
5. Telecharger le JSON immediatement (visible une seule fois)

#### Etape 2 — Configurer l'ecran de consentement

1. Ouvrir https://console.cloud.google.com/apis/credentials/consent
2. Remplir nom + emails
3. Audience : **Externe**, laisser en mode **Test**
4. Data Access → ajouter le scope : `https://www.googleapis.com/auth/webmasters`
5. Utilisateurs test → ajouter votre email Gmail

#### Etape 3 — Placer et configurer

```bash
cp ~/Downloads/client_secret_*.json packages/mcp-server/credentials/client_secret.json
```

```env
GSC_OAUTH_CLIENT_SECRETS_FILE=credentials/client_secret.json
GSC_OAUTH_TOKEN_FILE=credentials/token.json
```

Ajouter dans `.mcp.json` :

```json
{
  "mcpServers": {
    "seo-auditor": {
      "command": "...",
      "args": ["..."],
      "cwd": "...",
      "env": {
        "GSC_OAUTH_CLIENT_SECRETS_FILE": "/chemin/absolu/credentials/client_secret.json"
      }
    }
  }
}
```

#### Etape 4 — Premier lancement

Au premier appel d'un outil GSC, le navigateur s'ouvre pour l'autorisation.
Le token est sauvegarde dans `credentials/token.json` (renouvele automatiquement).

> Si le navigateur ne s'ouvre pas (SSH, headless), essayer :
> `BROWSER=xdg-open python -m seo_server.server`

---

## 6. Transport HTTP (optionnel)

En plus du transport stdio utilise par Claude Code, le serveur expose un
transport `streamable-http` pour tout client MCP distant :

```bash
cd packages/mcp-server
python -m seo_server.server --transport http
# Ecoute sur http://localhost:8020
```

> Il n'y a plus de dashboard React dans ce depot : il n'apportait rien qu'un
> client MCP ne fasse deja, et n'a jamais ete fonctionnel en production.
> Utiliser Claude Code (stdio) ou n'importe quel client MCP via `--transport http`.

---

## 7. Verification complete

```
┌─────────────────────────────────────────────────────────────┐
│                    Checklist installation                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [ ] Python 3.11+ installe                                  │
│  [ ] .venv cree + deps installees                           │
│  [ ] make mcp-test passe                                    │
│  [ ] .env configure (DEFAULT_BASE_URL au minimum)           │
│  [ ] .mcp.json pointe vers le bon venv                      │
│  [ ] Outils visibles dans Claude Code                       │
│                                                             │
│  GSC (optionnel) :                                          │
│  [ ] API Search Console activee dans Google Cloud           │
│  [ ] credentials/google-credentials.json present            │
│  [ ] Service account ajoute dans GSC (Full permission)      │
│  [ ] gsc_manage(action="sites") retourne les proprietes     │
│                                                             │
│  LLM (optionnel) :                                          │
│  [ ] LLM_PROVIDER + LLM_API_KEY dans .env                  │
│                                                             │
│  Transport HTTP (optionnel) :                               │
│  [ ] MCP server en mode HTTP (--transport http)             │
│  [ ] http://localhost:8020 repond                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Troubleshooting

### "API has not been used in project X"

L'API Search Console n'est pas activee dans le bon projet Google Cloud.

```
→ Ouvrir https://console.cloud.google.com/apis/library/searchconsole.googleapis.com
→ Verifier que le project_id en haut correspond a celui du service account JSON
→ Cliquer Enable
→ Attendre 1-2 minutes
```

### "Permission denied" / "Forbidden"

Le service account n'a pas acces a la propriete GSC.

```
→ GSC > Settings > Users and permissions
→ Verifier que le client_email du SA est liste avec permission "Full"
```

### "Invalid credentials" / "File not found"

Le chemin vers le JSON est incorrect.

```
→ Verifier GOOGLE_CREDENTIALS_PATH dans .env
→ Le chemin est relatif a packages/mcp-server/
→ Par defaut : credentials/google-credentials.json
```

### Navigateur ne s'ouvre pas (OAuth)

Environnement headless (SSH, WSL, Docker).

```
→ Option 1 : BROWSER=xdg-open python -m seo_server.server
→ Option 2 : passer au service account (recommande)
```

### "Access blocked: app not verified" (OAuth)

Email pas dans les utilisateurs test.

```
→ Google Cloud Console > APIs & Services > OAuth consent screen
→ Test users > ajouter votre email
```

### Client OAuth supprime

Google supprime les clients OAuth inactifs depuis 6 mois (depuis juin 2025).

```
→ Recreer les identifiants OAuth
→ Ou passer au service account (pas d'expiration)
```

---

## 9. Variables d'environnement (reference)

| Variable                       | Defaut                                 | Description                          |
|--------------------------------|----------------------------------------|--------------------------------------|
| `DEFAULT_SITEMAP_URL`          | —                                      | Sitemap cible par defaut             |
| `DEFAULT_BASE_URL`             | —                                      | URL de base pour le crawl            |
| `LLM_PROVIDER`                 | —                                      | `anthropic` / `openai` / `ollama`    |
| `LLM_API_KEY`                  | —                                      | Cle API du provider LLM              |
| `LLM_MODEL`                    | —                                      | Modele LLM                           |
| `GOOGLE_CREDENTIALS_PATH`      | `credentials/google-credentials.json`  | JSON service account GSC             |
| `GSC_OAUTH_CLIENT_SECRETS_FILE`| —                                      | JSON client OAuth GSC                |
| `GSC_OAUTH_TOKEN_FILE`         | `token.json`                           | Token OAuth (auto-genere)            |
| `GSC_SKIP_OAUTH`               | `false`                                | Force le mode service account        |
| `GSC_REQUESTS_PER_MINUTE`      | `50`                                   | Rate limit standard (max 60)         |
| `GSC_INSPECTION_RPM`           | `8`                                    | Rate limit inspection (max 10)       |
| `CHROME_DEVTOOLS_ENABLED`      | `true`                                 | Active l'integration Chrome DevTools |
| `CRAWLER_TIMEOUT`              | `30`                                   | Timeout crawl (secondes)             |
| `CRAWLER_MAX_CONCURRENT`       | `10`                                   | Crawls paralleles max                |
| `SIMILARITY_THRESHOLD`         | `0.7`                                  | Seuil de cannibalisation             |
| `API_PORT`                     | `8020`                                 | Port du serveur HTTP                 |

---

## 10. Cout & Quotas

| Service                | Cout              |
|------------------------|--------------------|
| Google Cloud Project   | Gratuit            |
| Search Console API     | Gratuit            |
| MCP Server             | Gratuit (self-host)|
| **Total**              | **0 EUR**          |

> Les couts LLM (Anthropic/OpenAI) sont a part et dependent de l'usage.

### Quotas GSC API

| Limite                                 | Valeur       |
|----------------------------------------|--------------|
| Queries per day                        | 100 000 000  |
| Requests per minute per user           | 60           |
| Queries per minute per user            | 1 200        |
| Low rate requests per minute (inspect) | 10           |

Le MCP server applique un rate limiting automatique (sliding window) :
- Appels standard : **50 RPM** par defaut (marge sous le max de 60)
- URL Inspection : **8 RPM** par defaut (marge sous le max de 10)

Configurable dans `.env` :

```env
GSC_REQUESTS_PER_MINUTE=50
GSC_INSPECTION_RPM=8
```

Detail complet : [`packages/mcp-server/docs/GSC_QUOTAS.md`](packages/mcp-server/docs/GSC_QUOTAS.md)
