# Production Dockerfile for MCP SEO Auditor server

# ═══════════════════════════════════════════════════════════════
# Stage 1: Build ghostchrome from source
# ═══════════════════════════════════════════════════════════════
FROM golang:1.24-alpine AS ghostchrome-builder

RUN apk add --no-cache git
WORKDIR /src
RUN git clone --depth 1 https://github.com/dev-toolings/ghostchrome.git . && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /ghostchrome .

# ═══════════════════════════════════════════════════════════════
# Stage 2: Python base — system dependencies
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS base
# pip >= 26.2.2 ships certifi 2026.10.19 (eMudhra CA compromise, CVE-2026-113470).
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2.2"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libxml2 \
    libxslt1.1 \
    gcc \
    g++ \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ═══════════════════════════════════════════════════════════════
# Stage 3: Production
# ═══════════════════════════════════════════════════════════════
FROM base AS production

# Chromium for ghostchrome CDP fallback (JS-rendered pages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    && rm -rf /var/lib/apt/lists/*

# ghostchrome binary from stage 1
COPY --from=ghostchrome-builder /ghostchrome /usr/local/bin/ghostchrome

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download fr_core_news_sm

# Application code
COPY app/ ./app/
COPY seo_server/ ./seo_server/

# SQLite data directory (volume mount point)
RUN mkdir -p /app/data

# Non-root user
RUN useradd -m -u 1001 auditor && \
    chown -R auditor:auditor /app

USER auditor

ENV BROWSER_AGENT_PATH=ghostchrome

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8020/health || exit 1

CMD ["python", "-m", "seo_server.server", "--transport", "http", "--port", "8020"]
