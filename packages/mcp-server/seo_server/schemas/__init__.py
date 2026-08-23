"""Pydantic input models for all MCP tools."""

from seo_server.schemas.agent import SeoAgentInput
from seo_server.schemas.analyze import SeoAnalyzeInput
from seo_server.schemas.audit import SeoAuditInput
from seo_server.schemas.crawl import SeoCrawlInput
from seo_server.schemas.fix import SeoFixInput
from seo_server.schemas.geo import SeoGeoInput
from seo_server.schemas.gsc_analytics import GscAnalyticsInput
from seo_server.schemas.gsc_manage import GscManageInput
from seo_server.schemas.logs import SeoLogsInput
from seo_server.schemas.market import SeoMarketInput
from seo_server.schemas.monitor import SeoMonitorInput
from seo_server.schemas.serp import SeoSerpInput
from seo_server.schemas.site import SeoSiteInput
from seo_server.schemas.strategy import SeoStrategyInput

__all__ = [
    "SeoAnalyzeInput",
    "SeoAgentInput",
    "SeoAuditInput",
    "SeoCrawlInput",
    "SeoFixInput",
    "SeoGeoInput",
    "GscAnalyticsInput",
    "GscManageInput",
    "SeoLogsInput",
    "SeoMarketInput",
    "SeoMonitorInput",
    "SeoSerpInput",
    "SeoSiteInput",
    "SeoStrategyInput",
]
