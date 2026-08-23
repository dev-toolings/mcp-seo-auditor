.PHONY: down status logs install install-service remove mcp-start mcp-stop mcp-restart mcp-logs test doctor

SERVICE_NAME = seo-auditor-mcp
SERVICE_DIR  = $(HOME)/.config/systemd/user
SERVICE_FILE = $(SERVICE_DIR)/$(SERVICE_NAME).service
PROJECT_DIR  = $(shell pwd)
MCP_WORKDIR  = $(PROJECT_DIR)/packages/mcp-server
VENV_DIR    ?= $(MCP_WORKDIR)/.venv
PYTHON       = $(VENV_DIR)/bin/python

# ═══════════════════════════════════════════════════════════════
# Package / Daemon Install / Remove
# ═══════════════════════════════════════════════════════════════

install: ## Create the virtualenv and install the MCP package locally
	@if [ -x "$(PYTHON)" ] && "$(PYTHON)" -m pip --version >/dev/null 2>&1; then \
		echo "Reusing healthy virtualenv: $(VENV_DIR)"; \
	elif command -v uv >/dev/null 2>&1; then \
		uv venv --seed --python python3 "$(VENV_DIR)"; \
	elif command -v virtualenv >/dev/null 2>&1; then \
		virtualenv -p python3 "$(VENV_DIR)"; \
	elif ! python3 -m venv "$(VENV_DIR)"; then \
		echo "Cannot create a virtualenv. Install uv, virtualenv, or the OS python3-venv package." >&2; \
		exit 1; \
	fi
	"$(PYTHON)" -m pip install --upgrade pip
	"$(PYTHON)" -m pip install -e "$(MCP_WORKDIR)[dev]"
	@echo "Installed: $(VENV_DIR)/bin/mcp-seo-auditor"

test: ## Run the local non-integration test suite
	cd "$(MCP_WORKDIR)" && "$(PYTHON)" -m pytest tests -m "not integration"

doctor: ## Verify the installed MCP registry
	"$(VENV_DIR)/bin/mcp-seo-auditor" --doctor

install-service: install ## Install MCP server as system daemon (auto-start on boot)
	@cd "$(MCP_WORKDIR)" && "$(VENV_DIR)/bin/mcp-seo-auditor" --check-http-config
	@mkdir -p $(SERVICE_DIR)
	@echo '[Unit]' > $(SERVICE_FILE)
	@echo 'Description=SEO Auditor MCP Server (streamable-http)' >> $(SERVICE_FILE)
	@echo 'After=network.target' >> $(SERVICE_FILE)
	@echo 'StartLimitIntervalSec=60' >> $(SERVICE_FILE)
	@echo 'StartLimitBurst=3' >> $(SERVICE_FILE)
	@echo '' >> $(SERVICE_FILE)
	@echo '[Service]' >> $(SERVICE_FILE)
	@echo 'Type=simple' >> $(SERVICE_FILE)
	@echo 'WorkingDirectory=$(MCP_WORKDIR)' >> $(SERVICE_FILE)
	@echo 'ExecStart=$(PYTHON) -m seo_server.server --transport http --port 8020' >> $(SERVICE_FILE)
	@echo 'Restart=on-failure' >> $(SERVICE_FILE)
	@echo 'RestartSec=10' >> $(SERVICE_FILE)
	@echo 'Environment=PYTHONUNBUFFERED=1' >> $(SERVICE_FILE)
	@echo 'EnvironmentFile=-$(MCP_WORKDIR)/.env' >> $(SERVICE_FILE)
	@echo 'MemoryMax=512M' >> $(SERVICE_FILE)
	@echo 'MemoryHigh=384M' >> $(SERVICE_FILE)
	@echo '' >> $(SERVICE_FILE)
	@echo '[Install]' >> $(SERVICE_FILE)
	@echo 'WantedBy=default.target' >> $(SERVICE_FILE)
	@systemctl --user daemon-reload
	@systemctl --user enable $(SERVICE_NAME).service
	@if ! loginctl enable-linger $(USER); then \
		echo "Warning: could not enable user lingering; the service may stop after logout." >&2; \
	fi
	@systemctl --user start $(SERVICE_NAME).service
	@echo "Installed and started. MCP server on http://localhost:8020/mcp"

remove: ## Uninstall MCP server daemon completely
	@if systemctl --user is-active --quiet $(SERVICE_NAME).service; then \
		systemctl --user stop $(SERVICE_NAME).service; \
	fi
	@if systemctl --user is-enabled --quiet $(SERVICE_NAME).service; then \
		systemctl --user disable $(SERVICE_NAME).service; \
	fi
	@rm -f $(SERVICE_FILE)
	@systemctl --user daemon-reload
	@echo "Daemon removed."

# ═══════════════════════════════════════════════════════════════
# Daemon Control
# ═══════════════════════════════════════════════════════════════

mcp-start: ## Start MCP daemon
	@systemctl --user start $(SERVICE_NAME).service
	@echo "MCP server started."

mcp-stop: ## Stop MCP daemon
	@systemctl --user stop $(SERVICE_NAME).service
	@echo "MCP server stopped."

mcp-restart: ## Restart MCP daemon (use after code changes)
	@systemctl --user restart $(SERVICE_NAME).service
	@echo "MCP server restarted."

mcp-logs: ## Follow MCP server logs
	@journalctl --user -u $(SERVICE_NAME).service -f

# ═══════════════════════════════════════════════════════════════
# Full Stack
# ═══════════════════════════════════════════════════════════════

down: ## Stop everything
	@$(MAKE) mcp-stop

status: ## Show status of all services
	@echo "=== MCP Server ==="
	@systemctl --user is-active $(SERVICE_NAME).service 2>/dev/null && \
		systemctl --user status $(SERVICE_NAME).service --no-pager 2>&1 | head -8 || \
		echo "Daemon not installed. Run 'make install-service'."
	@echo ""
	@echo "=== Dashboard ==="
	@pgrep -f "src/api/server.ts" > /dev/null 2>&1 && echo "API: running" || echo "API: stopped"
	@pgrep -f "vite" > /dev/null 2>&1 && echo "UI: running" || echo "UI: stopped"

logs: mcp-logs ## Alias for mcp-logs
