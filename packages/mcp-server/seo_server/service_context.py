"""Service context — lazy-loaded singleton holding all service instances.

Uses a registry pattern: simple services are declared in _SERVICE_REGISTRY
and auto-instantiated on first access via __getattr__. Services with complex
init logic are explicit @property methods.
"""

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Set by initialize() at server startup (lifespan), before any tool runs.
# Typed as ServiceContext so callers get attribute checking; the None sentinel
# before initialization is intentional (hence the targeted ignore).
ctx: "ServiceContext" = None  # type: ignore[assignment]

# (module_path, class_name) — services instantiated with no args
_SIMPLE_SERVICES: dict[str, tuple[str, str]] = {
    "sitemap_parser": ("app.services.sitemap_parser", "SitemapParserService"),
    "sitemap_analyzer": ("app.services.sitemap_analyzer", "SitemapAnalyzerService"),
    "crawler": ("app.services.crawler_service", "CrawlerService"),
    "content_validator": ("app.services.content_validator", "ContentValidatorService"),
    "keyword_extractor": ("app.services.keyword_extractor", "KeywordExtractorService"),
    "cannibalization_detector": (
        "app.services.cannibalization_detector",
        "CannibalizationDetectorService",
    ),
    "gsc": ("app.services.google_search_console", "GoogleSearchConsoleService"),
    "structured_data_validator": (
        "app.services.structured_data_validator",
        "StructuredDataValidatorService",
    ),
    "internal_links_analyzer": (
        "app.services.internal_links_analyzer",
        "InternalLinksAnalyzerService",
    ),
    "technical_seo_checker": ("app.services.technical_seo_checker", "TechnicalSEOCheckerService"),
    "cwv_service": ("app.services.core_web_vitals", "CoreWebVitalsService"),
    "serp_landscape_service": ("app.services.serp_landscape", "SERPLandscapeService"),
    "eeat_service": ("app.services.eeat_audit_service", "EEATAuditService"),
    "indexation_leak_detector": (
        "app.services.indexation_leak_detector",
        "IndexationLeakDetectorService",
    ),
    "log_analyzer": ("app.services.log_analyzer", "LogAnalyzerService"),
    "keyword_research": ("app.services.market.keyword_research", "KeywordResearchService"),
    "trend_analysis": ("app.services.market.trend_analysis", "TrendAnalysisService"),
    "competitor_analyzer": ("app.services.market.competitor_analyzer", "CompetitorAnalyzerService"),
    "niche_finder": ("app.services.market.niche_finder", "NicheFinderService"),
    "saas_viability": ("app.services.market.saas_viability", "SaaSViabilityService"),
}


class ServiceContext:
    """Holds all service instances used by tool handlers.

    Simple zero-arg services are resolved from _SIMPLE_SERVICES via __getattr__.
    Services with dependencies or special init are explicit properties below.
    """

    def __init__(self):
        self._instances: dict[str, object] = {}
        self._llm_provider = None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._instances:
            return self._instances[name]
        if name in _SIMPLE_SERVICES:
            module_path, class_name = _SIMPLE_SERVICES[name]
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
            instance = cls()
            self._instances[name] = instance
            return instance
        raise AttributeError(f"ServiceContext has no service '{name}'")

    # ─── LLM provider (special init) ─────────────────

    @property
    def llm_provider(self):
        if self._llm_provider is None:
            self._init_llm_sync()
        return self._llm_provider

    def _init_llm_sync(self):
        from app.core.config import settings
        from app.services.llm.base_provider import LLMConfig
        from app.services.llm.provider_factory import LLMProviderFactory

        if settings.LLM_PROVIDER:
            config = LLMConfig(
                provider=settings.LLM_PROVIDER,
                model=settings.LLM_MODEL,
                api_key=settings.LLM_API_KEY.get_secret_value(),
                base_url=settings.LLM_BASE_URL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            try:
                self._llm_provider = LLMProviderFactory.create(config)
            except Exception as e:
                logger.warning("Failed to initialize LLM provider: %s", e)

        if not self._llm_provider:
            # Provider construction alone does not prove availability: API
            # providers happily construct without a key. Prefer configured
            # environment credentials synchronously; Ollama remains opt-in.
            import os

            candidates = (
                ("anthropic", os.environ.get("ANTHROPIC_API_KEY", "")),
                ("openai", os.environ.get("OPENAI_API_KEY", "")),
            )
            for name, api_key in candidates:
                if not api_key:
                    continue
                try:
                    self._llm_provider = LLMProviderFactory.create(
                        LLMConfig(provider=name, api_key=api_key)
                    )
                    logger.info("Auto-selected LLM provider: %s", name)
                    break
                except Exception:
                    continue

        llm_status = (
            f"LLM: {self._llm_provider.config.provider}/{self._llm_provider.config.model}"
            if self._llm_provider
            else "LLM: disabled (deterministic mode)"
        )
        logger.info("LLM initialized. %s", llm_status)

    # ─── Services with dependencies ──────────────────

    @property
    def ai_analyzer(self):
        if "ai_analyzer" not in self._instances:
            from app.services.ai.ai_analyzer import AIAnalyzer

            self._instances["ai_analyzer"] = AIAnalyzer(self.llm_provider)
        return self._instances["ai_analyzer"]

    @property
    def geo_analyzer(self):
        if "geo_analyzer" not in self._instances:
            from app.services.geo.geo_analyzer import GEOAnalyzer

            self._instances["geo_analyzer"] = GEOAnalyzer(self.llm_provider)
        return self._instances["geo_analyzer"]

    @property
    def llms_txt_checker(self):
        if "llms_txt_checker" not in self._instances:
            from app.services.geo.llms_txt_checker import LLMsTxtChecker

            self._instances["llms_txt_checker"] = LLMsTxtChecker()
        return self._instances["llms_txt_checker"]

    @property
    def full_audit(self):
        if "full_audit" not in self._instances:
            from app.services.ai.audit_orchestrator import AuditOrchestrator
            from app.services.ai.full_audit import FullAuditService

            orchestrator = AuditOrchestrator(self)
            self._instances["full_audit"] = FullAuditService(
                orchestrator, self.geo_analyzer, self.ai_analyzer
            )
        return self._instances["full_audit"]

    @property
    def action_plan(self):
        if "action_plan" not in self._instances:
            from app.services.ai.action_plan import ActionPlanService

            self._instances["action_plan"] = ActionPlanService(self.ai_analyzer)
        return self._instances["action_plan"]

    @property
    def content_brief(self):
        if "content_brief" not in self._instances:
            from app.services.ai.content_brief import ContentBriefService

            self._instances["content_brief"] = ContentBriefService(
                self.crawler, self.structured_data_validator, self.ai_analyzer
            )
        return self._instances["content_brief"]

    @property
    def competitor_gap(self):
        if "competitor_gap" not in self._instances:
            from app.services.ai.competitor_gap import CompetitorGapService

            self._instances["competitor_gap"] = CompetitorGapService(
                self.sitemap_parser,
                self.ai_analyzer,
                self.competitor_analyzer,
                self.trend_analysis,
            )
        return self._instances["competitor_gap"]

    @property
    def anomaly_detector(self):
        if "anomaly_detector" not in self._instances:
            from app.services.ai.anomaly_detector import AnomalyDetectorService

            self._instances["anomaly_detector"] = AnomalyDetectorService(
                self.gsc, self.ai_analyzer, self.crawl_repository
            )
        return self._instances["anomaly_detector"]

    @property
    def strategic_plan(self):
        if "strategic_plan" not in self._instances:
            from app.services.ai.strategic_plan import StrategicPlanService

            self._instances["strategic_plan"] = StrategicPlanService(self.ai_analyzer)
        return self._instances["strategic_plan"]

    @property
    def ai_query_intelligence(self):
        if "ai_query_intelligence" not in self._instances:
            from app.services.ai.ai_query_intelligence import AIQueryIntelligenceService

            self._instances["ai_query_intelligence"] = AIQueryIntelligenceService(
                self.gsc, self.ai_analyzer
            )
        return self._instances["ai_query_intelligence"]

    @property
    def serp_analyzer(self):
        if "serp_analyzer" not in self._instances:
            from app.services.serp.serp_analyzer import SERPAnalyzerService

            try:
                from app.services.serp.serp_scraper import SERPScraper

                serp_scraper = SERPScraper()
            except Exception as e:
                logger.warning("SERPScraper unavailable: %s", e)
                serp_scraper = None
            self._instances["serp_analyzer"] = SERPAnalyzerService(serp_scraper)
        return self._instances["serp_analyzer"]

    @property
    def topical_authority(self):
        if "topical_authority" not in self._instances:
            from app.services.ai.topical_authority import TopicalAuthorityService

            self._instances["topical_authority"] = TopicalAuthorityService(
                self.gsc, self.ai_analyzer
            )
        return self._instances["topical_authority"]

    @property
    def priorities_service(self):
        if "priorities_service" not in self._instances:
            from app.services.ai.priorities import PrioritiesService

            self._instances["priorities_service"] = PrioritiesService(self.ai_analyzer, self.gsc)
        return self._instances["priorities_service"]

    @property
    def schema_generator(self):
        if "schema_generator" not in self._instances:
            from app.services.schema_generator import SchemaGeneratorService

            self._instances["schema_generator"] = SchemaGeneratorService(
                self.crawler, self.ai_analyzer
            )
        return self._instances["schema_generator"]

    @property
    def migration_planner(self):
        if "migration_planner" not in self._instances:
            from app.services.migration_planner import MigrationPlannerService

            self._instances["migration_planner"] = MigrationPlannerService(
                self.sitemap_parser, self.gsc
            )
        return self._instances["migration_planner"]

    @property
    def dataforseo_client(self):
        if "dataforseo_client" not in self._instances:
            from app.core.config import settings
            from app.services.dataforseo.client import DataForSEOClient

            self._instances["dataforseo_client"] = DataForSEOClient(
                login=settings.DATAFORSEO_LOGIN,
                password=settings.DATAFORSEO_PASSWORD.get_secret_value(),
                base_url=settings.DATAFORSEO_BASE_URL,
            )
        return self._instances["dataforseo_client"]

    @property
    def volume_calibrator(self):
        if "volume_calibrator" not in self._instances:
            from app.services.market.volume_calibrator import VolumeCalibratorService

            self._instances["volume_calibrator"] = VolumeCalibratorService(
                self.gsc, self.trend_analysis
            )
        return self._instances["volume_calibrator"]

    @property
    def editorial_context(self):
        if "editorial_context" not in self._instances:
            from app.core.config import settings
            from app.services.editorial.context import EditorialContextService

            self._instances["editorial_context"] = EditorialContextService(
                settings.EDITORIAL_CONTEXT_DIR
            )
        return self._instances["editorial_context"]

    @property
    def content_writer(self):
        if "content_writer" not in self._instances:
            from app.services.ai.content_writer import ContentWriterService

            self._instances["content_writer"] = ContentWriterService(
                self.ai_analyzer, self.editorial_context
            )
        return self._instances["content_writer"]

    @property
    def content_optimizer(self):
        if "content_optimizer" not in self._instances:
            from app.services.ai.content_optimizer import ContentOptimizerService

            self._instances["content_optimizer"] = ContentOptimizerService(
                self.ai_analyzer, self.editorial_context
            )
        return self._instances["content_optimizer"]

    @property
    def meta_generator(self):
        if "meta_generator" not in self._instances:
            from app.services.ai.meta_generator import MetaGeneratorService

            self._instances["meta_generator"] = MetaGeneratorService(
                self.ai_analyzer, self.editorial_context
            )
        return self._instances["meta_generator"]

    # ─── Repositories ────────────────────────────────

    @property
    def crawl_repository(self):
        if "crawl_repository" not in self._instances:
            from app.repositories.crawl_repository import CrawlRepository

            self._instances["crawl_repository"] = CrawlRepository()
        return self._instances["crawl_repository"]

    @property
    def report_repository(self):
        if "report_repository" not in self._instances:
            from app.core.config import settings
            from app.repositories.report_repository import ReportRepository

            self._instances["report_repository"] = ReportRepository(
                db_path=settings.SQLITE_DB_PATH,
                retention_hours=settings.REPORT_RETENTION_HOURS,
            )
        return self._instances["report_repository"]

    @property
    def agent_supervisor(self):
        if "agent_supervisor" not in self._instances:
            from app.services.agent.supervisor import SEOAgentSupervisor

            self._instances["agent_supervisor"] = SEOAgentSupervisor(self)
        return self._instances["agent_supervisor"]

    @property
    def skill_lifecycle(self):
        if "skill_lifecycle" not in self._instances:
            from app.services.agent.skill_lifecycle import SkillLifecycleService

            self._instances["skill_lifecycle"] = SkillLifecycleService()
        return self._instances["skill_lifecycle"]

    # ─── Lifecycle ───────────────────────────────────

    async def shutdown(self):
        serp = self._instances.get("serp_analyzer")
        if serp and hasattr(serp, "serp_scraper"):
            scraper = serp.serp_scraper
            if scraper and hasattr(scraper, "close"):
                await scraper.close()
        crawler = self._instances.get("crawler")
        if crawler:
            await crawler.close()
        report_repo = self._instances.get("report_repository")
        if report_repo and hasattr(report_repo, "close"):
            await report_repo.close()
        crawl_repo = self._instances.get("crawl_repository")
        if crawl_repo and hasattr(crawl_repo, "close"):
            await crawl_repo.close()
        agent_supervisor = self._instances.get("agent_supervisor")
        if agent_supervisor:
            await agent_supervisor.shutdown()


def initialize():
    global ctx
    ctx = ServiceContext()
    return ctx
