# Production Deployment

## Prerequisites

- Docker and Docker Compose v2+
- An Anthropic API key (`sk-ant-...`)
- (Optional) Google credentials JSON for GSC integration
- (Optional) A domain name with DNS pointing to your server

## Quick Start

```bash
cd deploy-prod/

# 1. Create your environment file
cp .env.production.example .env.production
# Edit .env.production with your API keys
# Replace MCP_AUTH_TOKEN with a long random value; HTTP refuses to start without it.

# 2. (Optional) Add Google credentials
mkdir -p credentials/
cp /path/to/google-credentials.json credentials/

# 3. Build and start
docker compose -f docker-compose.prod.yml up --build -d
```

The MCP endpoint will be available at `http://localhost/mcp/` (port 80). This
deployment serves the MCP API only — there is no web frontend.

## Configuration

| Variable | Service | Description |
|---|---|---|
| `LLM_PROVIDER` | mcp-server | `anthropic`, `openai`, or `ollama` |
| `MCP_AUTH_TOKEN` | mcp-server | Bearer token required by the remote MCP endpoint |
| `LLM_MODEL` | mcp-server | Model name (e.g. `claude-sonnet-4-20250514`) |
| `LLM_API_KEY` | mcp-server | API key for the LLM provider |
| `LOG_LEVEL` | mcp-server | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |
| `LOG_JSON` | mcp-server | `true` for structured JSON logs (default: `true`) |
| `DOMAIN` | caddy | Your domain (default: `localhost`) |

## Volume Mounts

| Volume | Purpose |
|---|---|
| `mcp-data` | SQLite database persistence (`/app/data/`) |
| `caddy-data` | TLS certificates (auto-managed by Caddy) |
| `caddy-config` | Caddy configuration state |
| `./credentials` | Google credentials (read-only bind mount) |

## Custom Domain with HTTPS

1. Set `DOMAIN=yourdomain.com` in `.env.production`
2. Ensure ports 80 and 443 are open and DNS A record points to your server
3. Restart: `docker compose -f docker-compose.prod.yml up -d`

Caddy automatically provisions and renews TLS certificates via Let's Encrypt.

## Commands

```bash
# View logs
docker compose -f docker-compose.prod.yml logs -f

# Restart a single service
docker compose -f docker-compose.prod.yml restart mcp-server

# Stop everything
docker compose -f docker-compose.prod.yml down

# Rebuild after code changes
docker compose -f docker-compose.prod.yml up --build -d
```
