# Configuration Google Search Console API

> Voir aussi : [`INDEXING_API_SETUP.md`](./INDEXING_API_SETUP.md) pour notifier Google
> des changements d'URL (`gsc_manage action="index"`).

## Cout : GRATUIT

L'API Google Search Console est **100% gratuite**.

- Pas de facturation, pas de carte bancaire
- Quota : ~25 000 requetes/jour

---

## Prerequis

1. Un compte Google
2. Un site verifie dans [Google Search Console](https://search.google.com/search-console)
3. ~10 minutes

---

## Deux modes d'authentification

Le serveur MCP supporte deux modes, testes dans cet ordre :

| Mode | Quand l'utiliser | Variable d'env |
|------|-----------------|----------------|
| **OAuth 2.0** (recommande) | Usage local / dev, compte personnel | `GSC_OAUTH_CLIENT_SECRETS_FILE` |
| **Service Account** | Serveur, CI/CD, Docker | `GOOGLE_CREDENTIALS_PATH` |

> Le mode OAuth est tente en premier. Si il echoue, le service account prend le relais automatiquement.

---

## Option A : OAuth 2.0 (recommande pour dev local)

### Etape 1 — Creer un projet Google Cloud

1. Ouvrir [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate)
2. **Nom du projet** : `seo-auditor` (ou ce que vous voulez)
3. Cliquer **Creer**
4. Selectionner le projet dans le selecteur en haut de page

### Etape 2 — Activer l'API Search Console

1. Ouvrir [console.cloud.google.com/apis/library/searchconsole.googleapis.com](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)
2. Cliquer **Activer**

### Etape 3 — Configurer l'ecran de consentement OAuth

Depuis avril 2025, Google a deplace cette config dans une section dediee **"Google Auth Platform"**.

1. Ouvrir [console.cloud.google.com/apis/credentials/consent](https://console.cloud.google.com/apis/credentials/consent)
   - Ou : menu lateral > **Google Auth Platform** > **Branding**
2. Remplir les champs obligatoires :
   - **Nom de l'application** : `SEO Auditor`
   - **Email d'assistance** : votre email
   - **Email du developpeur** : votre email
3. **Audience** : selectionner **Externe**
4. Laisser l'app en mode **Test** (pas besoin de verification Google pour un usage personnel)
5. Dans l'onglet **Data Access** (ou "Champs d'application") :
   - Ajouter le scope : `https://www.googleapis.com/auth/webmasters`
   - (lecture + ecriture GSC — necessaire pour `gsc_manage`)
6. Dans **Utilisateurs test** : ajouter votre adresse Gmail

> **Ref** : [Configurer l'ecran de consentement](https://developers.google.com/workspace/guides/configure-oauth-consent)

### Etape 4 — Creer les identifiants OAuth

1. Ouvrir [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
2. Cliquer **+ Creer des identifiants** > **ID client OAuth**
3. **Type d'application** : `Application de bureau`
4. **Nom** : `SEO Auditor Local`
5. Cliquer **Creer**
6. **Telecharger immediatement le JSON** (bouton de telechargement dans la popup)

> **Depuis juin 2025** : le secret n'est visible qu'une seule fois a la creation.
> Si vous fermez la popup sans telecharger, il faudra supprimer le client et en recreer un.
>
> **Ref** : [Creer des identifiants](https://developers.google.com/workspace/guides/create-credentials)

### Etape 5 — Placer le fichier et configurer

```bash
# Creer le dossier credentials (deja gitignore)
mkdir -p packages/mcp-server/credentials

# Deplacer et renommer le fichier telecharge
mv ~/Downloads/client_secret_*.json packages/mcp-server/credentials/client_secret.json
```

Ajouter dans votre `.env` :

```env
GSC_OAUTH_CLIENT_SECRETS_FILE=credentials/client_secret.json
GSC_OAUTH_TOKEN_FILE=credentials/token.json
```

### Etape 6 — Premier lancement (autorisation)

Au premier appel d'un outil GSC, le navigateur s'ouvre automatiquement :

1. Connectez-vous avec le compte Google qui a acces a Search Console
2. Acceptez les permissions demandees
3. Le token est sauvegarde dans `credentials/token.json` (renouvele automatiquement ensuite)

> Le flow utilise `InstalledAppFlow.run_local_server()` — redirection sur `http://127.0.0.1` (localhost).
> Pas besoin de configurer d'URI de redirection dans la console.

---

## Option B : Service Account (serveur / Docker)

### Etape 1 & 2 — Projet + API

Identiques a l'option A ci-dessus.

### Etape 3 — Creer un Service Account

1. Ouvrir [console.cloud.google.com/iam-admin/serviceaccounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Cliquer **+ Creer un compte de service**
3. **Nom** : `seo-auditor`
4. **ID** : `seo-auditor` (auto-genere)
5. Cliquer **Creer et continuer** > passer les roles > **OK**
6. Dans la liste, cliquer sur le compte cree
7. Onglet **Cles** > **Ajouter une cle** > **Creer une cle** > **JSON**
8. Le fichier se telecharge automatiquement

```bash
mkdir -p packages/mcp-server/credentials
mv ~/Downloads/seo-auditor-*.json packages/mcp-server/credentials/google-credentials.json
```

### Etape 4 — Donner acces dans Search Console

Le service account a un email du type `seo-auditor@votre-projet.iam.gserviceaccount.com`
(visible dans le JSON sous `client_email`).

1. Ouvrir [search.google.com/search-console](https://search.google.com/search-console)
2. Selectionner votre propriete
3. **Parametres** > **Utilisateurs et autorisations**
4. **Ajouter un utilisateur**
5. Coller l'email du service account
6. Autorisation : **Complete**
7. **Ajouter**

### Etape 5 — Configurer

Dans `.env` :

```env
GOOGLE_CREDENTIALS_PATH=credentials/google-credentials.json
```

Pour Docker, le `docker-compose.yml` monte deja le dossier :

```yaml
volumes:
  - ./credentials:/app/credentials:ro
```

---

## Verification

```bash
cd packages/mcp-server

# Demarrer le serveur HTTP
python -m seo_server.server --transport http

# Dans un autre terminal — lister les sites GSC accessibles
curl -s http://localhost:8020/health | python -m json.tool
```

Reponse attendue :

```json
{
  "status": "healthy",
  "dependencies": {
    "google_search_console": "available"
  }
}
```

Tester avec l'outil MCP `gsc_manage(action="list_sites")` pour voir vos proprietes.

---

## Variables d'environnement (reference)

| Variable | Defaut | Description |
|----------|--------|-------------|
| `GSC_OAUTH_CLIENT_SECRETS_FILE` | — | Chemin vers le `client_secret.json` (OAuth) |
| `GSC_OAUTH_TOKEN_FILE` | `token.json` | Ou stocker le token OAuth (auto-genere) |
| `GSC_SKIP_OAUTH` | `false` | `true` pour forcer le mode service account |
| `GOOGLE_CREDENTIALS_PATH` | `credentials/google-credentials.json` | Chemin vers le JSON service account |

---

## Securite

- **Ne jamais commit** les fichiers de credentials JSON
- Le `.gitignore` exclut deja `credentials/`, `*.credentials.json` et `client_secret_*.json`
- En production : utiliser Docker Secrets, Kubernetes Secrets, ou un secret manager
- **Depuis novembre 2025** : les client secrets OAuth ne sont visibles qu'a la creation — stockez le JSON immediatement

---

## Troubleshooting

### "Permission denied"

Le compte (service account ou OAuth) n'a pas acces a la propriete Search Console.
- Service account : refaire l'etape 4 de l'option B
- OAuth : verifier que vous etes connecte avec le bon compte Google

### "API not enabled"

L'API Search Console n'est pas activee dans le projet.
→ [Activer l'API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)

### "Invalid credentials" / "File not found"

Le fichier JSON est absent ou le chemin est incorrect.
→ Verifier la variable d'env dans `.env`

### "Access blocked: app not verified"

Votre app OAuth est en mode test mais votre email n'est pas dans les utilisateurs test.
→ Ajouter votre email dans [l'ecran de consentement](https://console.cloud.google.com/apis/credentials/consent) > Utilisateurs test

### "Site not found"

L'URL du site ne correspond pas exactement (avec/sans trailing slash, `sc-domain:` vs `https://`).
→ Utiliser `gsc_manage(action="list_sites")` pour voir les URL exactes

### Client OAuth supprime automatiquement

Depuis juin 2025, Google supprime les clients OAuth inactifs depuis 6 mois.
→ Utiliser le MCP au moins une fois par trimestre, ou recreer les identifiants

---

## Liens utiles

| Ressource | URL |
|-----------|-----|
| Google Cloud Console | [console.cloud.google.com](https://console.cloud.google.com/) |
| Creer un projet | [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate) |
| API Search Console (activer) | [console.cloud.google.com/apis/library/searchconsole.googleapis.com](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) |
| Identifiants OAuth | [console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials) |
| Ecran de consentement | [console.cloud.google.com/apis/credentials/consent](https://console.cloud.google.com/apis/credentials/consent) |
| Search Console | [search.google.com/search-console](https://search.google.com/search-console) |
| Doc officielle API | [developers.google.com/webmaster-tools](https://developers.google.com/webmaster-tools/v1/api_reference_index) |
| Autorisation API | [developers.google.com/webmaster-tools/v1/how-tos/authorizing](https://developers.google.com/webmaster-tools/v1/how-tos/authorizing) |
| Quickstart Python | [developers.google.com/webmaster-tools/v1/quickstart/quickstart-python](https://developers.google.com/webmaster-tools/v1/quickstart/quickstart-python) |
| Quotas et limites | [developers.google.com/webmaster-tools/limits](https://developers.google.com/webmaster-tools/limits) |

---

## Resume des couts

| Service | Cout |
|---------|------|
| Google Cloud Project | Gratuit |
| Search Console API | Gratuit |
| Quota API | 25 000 req/jour gratuit |
| **Total** | **0 EUR** |
