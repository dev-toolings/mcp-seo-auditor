# Multi-stage Dockerfile for SEO Auditor
# Optimized for SEO analysis with spaCy NLP

# ═══════════════════════════════════════════════════════════════
# Stage 1: Base Image with system dependencies
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Network tools
    curl \
    # XML parsing
    libxml2 \
    libxslt1.1 \
    # Build tools (for lxml)
    gcc \
    g++ \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app


# ═══════════════════════════════════════════════════════════════
# Stage 2: Development
# ═══════════════════════════════════════════════════════════════
FROM base AS development

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy French model
RUN python -m spacy download fr_core_news_sm

# Create data directory
RUN mkdir -p /app/data

# MCP stdio server (no HTTP port needed)
CMD ["python", "-m", "seo_server.server"]


# ═══════════════════════════════════════════════════════════════
# Stage 3: Production
# ═══════════════════════════════════════════════════════════════
FROM base AS production

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    python -m spacy download fr_core_news_sm

# Copy application code
COPY app/ ./app/
COPY seo_server/ ./seo_server/

# Create data directory and set permissions
RUN mkdir -p /app/data

# Create non-root user
RUN useradd -m -u 1001 auditor && \
    chown -R auditor:auditor /app

USER auditor

# MCP stdio server (no HTTP port needed)
CMD ["python", "-m", "seo_server.server"]


# ═══════════════════════════════════════════════════════════════
# Stage 4: Production + Browser (agent-browser)
# ═══════════════════════════════════════════════════════════════
FROM production AS browser

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates unzip nodejs \
    libxcb-shm0 libx11-xcb1 libx11-6 libxcb1 libxext6 libxrandr2 \
    libxcomposite1 libxcursor1 libxdamage1 libxfixes3 libxi6 \
    libgtk-3-0t64 libpangocairo-1.0-0 libpango-1.0-0 libatk1.0-0t64 \
    libcairo-gobject2 libcairo2 libgdk-pixbuf-2.0-0 libxrender1 \
    libasound2t64 libfreetype6 libfontconfig1 libdbus-1-3 libnss3 \
    libnss3-tools libnspr4 libatk-bridge2.0-0t64 libdrm2 libxkbcommon0 \
    libatspi2.0-0t64 libcups2t64 libxshmfence1 libgbm1 \
    fonts-noto-color-emoji fonts-noto-cjk fonts-freefont-ttf && \
    export BUN_INSTALL="/opt/bun" && \
    curl -fsSL https://bun.sh/install | bash && \
    chmod -R 755 /opt/bun && \
    /opt/bun/bin/bun install -g agent-browser && \
    /opt/bun/bin/agent-browser install && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/bun/bin:$PATH"

USER auditor

CMD ["python", "-m", "seo_server.server"]
