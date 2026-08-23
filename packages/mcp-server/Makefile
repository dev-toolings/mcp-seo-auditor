.PHONY: help dev dev-build stop restart logs test test-all test-integration clean mcp-test install run-local

# Colors
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

help: ## Show this help message
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@echo "$(GREEN)  MCP SEO Auditor - SEO Analysis Tools for Claude Code$(NC)"
	@echo "$(BLUE)════════════════════════════════════════════════════════════════$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ═══════════════════════════════════════════════════════════════
# Docker Commands
# ═══════════════════════════════════════════════════════════════

dev: ## Start development server (docker compose up -d)
	@echo "$(GREEN)Starting SEO Auditor MCP server...$(NC)"
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up -d
	@echo "$(GREEN)MCP server started!$(NC)"

dev-build: ## Build and start dev server
	@echo "$(GREEN)Building and starting MCP server...$(NC)"
	@cp -n .env.example .env 2>/dev/null || true
	docker compose up -d --build
	@echo "$(GREEN)MCP server built and started!$(NC)"

stop: ## Stop development server
	@echo "$(YELLOW)Stopping MCP server...$(NC)"
	docker compose down
	@echo "$(GREEN)MCP server stopped$(NC)"

restart: ## Restart development server
	@echo "$(YELLOW)Restarting MCP server...$(NC)"
	docker compose restart
	@echo "$(GREEN)MCP server restarted$(NC)"

logs: ## Show logs (follow mode)
	docker compose logs -f

ps: ## Show running containers
	docker compose ps

shell: ## Open shell in container
	docker compose exec seo-auditor bash

# ═══════════════════════════════════════════════════════════════
# Testing Commands
# ═══════════════════════════════════════════════════════════════

test: ## Run unit tests only (fast, no API calls)
	@echo "$(BLUE)Running unit tests...$(NC)"
	.venv/bin/python -m pytest tests/ -v

test-all: ## Run ALL tests including integration (real API calls)
	@echo "$(BLUE)Running ALL tests (unit + integration)...$(NC)"
	.venv/bin/python -m pytest tests/ -v -m ""

test-integration: ## Run integration tests only (real API calls)
	@echo "$(BLUE)Running integration tests...$(NC)"
	.venv/bin/python -m pytest tests/ -v -m "integration"

test-market: ## Run Market Intelligence tests (real API calls)
	@echo "$(BLUE)Running Market Intelligence tests...$(NC)"
	.venv/bin/python -m pytest tests/test_keyword_research.py tests/test_trend_analysis.py tests/test_competitor_analyzer.py tests/test_niche_finder.py tests/test_saas_viability.py -v -m ""

# ═══════════════════════════════════════════════════════════════
# MCP Commands
# ═══════════════════════════════════════════════════════════════

mcp-test: ## Test MCP server locally
	@echo "$(BLUE)Testing MCP server...$(NC)"
	.venv/bin/python -m seo_server.server --test

# ═══════════════════════════════════════════════════════════════
# Cleanup Commands
# ═══════════════════════════════════════════════════════════════

clean: ## Clean up containers and volumes
	@echo "$(YELLOW)Cleaning up...$(NC)"
	docker compose down -v
	@echo "$(GREEN)Cleanup complete$(NC)"

# ═══════════════════════════════════════════════════════════════
# Local Development (without Docker)
# ═══════════════════════════════════════════════════════════════

install: ## Install Python dependencies locally
	@echo "$(GREEN)Installing dependencies...$(NC)"
	pip install -e ".[dev]"
	python -m spacy download fr_core_news_sm
	@echo "$(GREEN)Dependencies installed$(NC)"

run-local: ## Run MCP server locally (stdio)
	@echo "$(GREEN)Starting MCP server...$(NC)"
	python3 -m seo_server.server

.DEFAULT_GOAL := help
