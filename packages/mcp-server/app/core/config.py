"""Application configuration and settings."""

import os

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    # Default targets
    DEFAULT_SITEMAP_URL: str = "http://localhost:3000/sitemap.xml"
    DEFAULT_BASE_URL: str = "http://localhost:3000"

    # Security — allow localhost/private IPs (dev only, NEVER in production)
    ALLOW_LOCAL_URLS: bool = False

    # Remote MCP transport. HTTP refuses to start without a token unless the
    # operator explicitly opts into an insecure development-only mode.
    MCP_AUTH_TOKEN: SecretStr = SecretStr("")
    ALLOW_UNAUTHENTICATED_HTTP: bool = False

    # Autonomous SEO agent (disabled by default).
    SEO_AGENT_ENABLED: bool = False
    SEO_AGENT_PROVIDER: str = "auto"
    SEO_AGENT_PROVIDER_ORDER: str = "codex,claude,grok"
    SEO_AGENT_MODEL: str = ""
    SEO_AGENT_ALLOWED_ROOTS: str = ""
    SEO_AGENT_RUNTIME_CONFIG: str = ""
    SEO_AGENT_WORKTREE_ROOT: str = "data/agent-worktrees"
    SEO_AGENT_ARTIFACT_ROOT: str = "data/agent-runs"
    SEO_AGENT_MAX_CONCURRENT_RUNS: int = 2
    SEO_AGENT_MAX_FILES: int = 50
    SEO_AGENT_MAX_DIFF_LINES: int = 5000
    SEO_AGENT_MAX_RUN_MINUTES: int = 60
    SEO_AGENT_MAX_REPAIR_CYCLES: int = 2
    SEO_AGENT_MAX_CLI_SECONDS: int = 1800

    # Declarative Codex skill lifecycle. Roots must be explicitly authorized;
    # the first root is used when a tool call omits skill_root.
    SEO_AGENT_SKILL_ROOTS: str = ""

    # Logging / Observability
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_JSON: bool = True  # False = human-readable text (local debugging)

    # Crawler Settings
    CRAWLER_TIMEOUT: int = 30
    CRAWLER_MAX_CONCURRENT: int = 10
    CRAWLER_USER_AGENT: str = "SEOAuditor/2.0"

    # Content Analysis
    MIN_CONTENT_WORDS: int = 100
    THIN_CONTENT_THRESHOLD: int = 50

    # Cannibalization Detection
    SIMILARITY_THRESHOLD: float = 0.7
    MIN_KEYWORD_FREQUENCY: int = 2

    # Report Storage
    REPORT_RETENTION_HOURS: int = 24

    # Google Search Console (optional)
    GOOGLE_CREDENTIALS_PATH: str = "credentials/google-credentials.json"
    GSC_REQUESTS_PER_MINUTE: int = 50
    GSC_INSPECTION_RPM: int = 8
    GSC_DAILY_QUOTA: int = 100_000_000

    # PageSpeed Insights (optional)
    PAGESPEED_API_KEY: SecretStr = SecretStr("")

    # LLM Configuration (optional)
    LLM_PROVIDER: str = ""  # "anthropic", "openai", "ollama", "" = disabled
    LLM_MODEL: str = ""
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_BASE_URL: str = ""
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # SQLite Database
    SQLITE_DB_PATH: str = "data/seo_auditor.db"

    # Editorial Context
    EDITORIAL_CONTEXT_DIR: str = ""

    # Chrome DevTools Configuration (for local audits)
    CHROME_DEVTOOLS_ENABLED: bool = True
    CHROME_DEVTOOLS_HEADLESS: bool = True
    CHROME_DEVTOOLS_VIEWPORT_WIDTH: int = 1920
    CHROME_DEVTOOLS_VIEWPORT_HEIGHT: int = 1080
    CHROME_DEVTOOLS_EMULATE_MOBILE: bool = False
    CHROME_DEVTOOLS_NETWORK_THROTTLE: str | None = (
        None  # "No emulation", "Offline", "Slow 3G", "Fast 3G", "Slow 4G", "Fast 4G"
    )
    CHROME_DEVTOOLS_CPU_THROTTLE: int | None = None  # 1-20

    # Browser Rendering (agent-browser)
    BROWSER_HEADLESS: bool = True
    BROWSER_TIMEOUT: int = 60
    BROWSER_IDLE_TIMEOUT: int = 300
    BROWSER_MAX_CONCURRENT: int = 3
    BROWSER_CDP: str = ""
    BROWSER_AGENT_PATH: str = "agent-browser"

    # DataForSEO (optional — keyword volumes, SERP data, keyword suggestions)
    # Billed per request: the resilience knobs below cap spend and protect the
    # quota. Retries only fire on transient errors, never on a 4xx that would
    # be re-billed for the same failure.
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: SecretStr = SecretStr("")
    DATAFORSEO_BASE_URL: str = "https://api.dataforseo.com"
    DATAFORSEO_TIMEOUT: int = 30
    DATAFORSEO_MAX_RETRIES: int = 3
    DATAFORSEO_REQUESTS_PER_MINUTE: int = 120
    DATAFORSEO_MAX_CONCURRENT: int = 5
    DATAFORSEO_CACHE_TTL: int = 3600  # seconds; 0 disables the response cache
    DATAFORSEO_CACHE_MAX_ENTRIES: int = 512

    # Rapid URL Indexer (optional — pay-per-success bulk Google indexer for
    # regular pages, where the Google Indexing API does not apply)
    RAPID_URL_INDEXER_API_KEY: SecretStr = SecretStr("")
    RAPID_URL_INDEXER_BASE_URL: str = "https://rapidurlindexer.com/wp-json"

    model_config = SettingsConfigDict(
        env_file=os.environ.get("SEO_AUDITOR_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
