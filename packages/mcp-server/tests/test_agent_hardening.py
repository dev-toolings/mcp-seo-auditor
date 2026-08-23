from types import SimpleNamespace

import pytest
from pydantic import BaseModel, SecretStr
from starlette.testclient import TestClient

from app.core.config import settings
from app.models.report import AuditReport, AuditType
from app.repositories.report_repository import ReportRepository
from app.services.llm.provider_factory import LLMProviderFactory
from app.services.sitemap_parser import SitemapParserService
from seo_server import service_context
from seo_server.server import (
    _http_app_with_health,
    _require_http_configuration,
    _run_http_with_health,
    mcp,
)
from seo_server.service_context import ServiceContext


class _Issue(BaseModel):
    code: str


@pytest.mark.asyncio
async def test_report_repository_serializes_pydantic_issues(tmp_path):
    repository = ReportRepository(str(tmp_path / "reports.db"))
    report = AuditReport(
        audit_type=AuditType.FULL,
        issues=[_Issue(code="missing_title")],
        recommendations=[_Issue(code="add_title")],
    )
    await repository.save(report)
    restored = await repository.get(report.audit_id)
    assert restored and restored.issues == [{"code": "missing_title"}]
    await repository.close()


def test_http_transport_refuses_missing_auth(monkeypatch):
    monkeypatch.setattr(settings, "MCP_AUTH_TOKEN", SecretStr(""))
    monkeypatch.setattr(settings, "ALLOW_UNAUTHENTICATED_HTTP", False)
    with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
        _run_http_with_health(object(), "127.0.0.1", 8020)


def test_http_preflight_reports_authenticated_mode(monkeypatch):
    monkeypatch.setattr(settings, "MCP_AUTH_TOKEN", SecretStr("configured"))
    monkeypatch.setattr(settings, "ALLOW_UNAUTHENTICATED_HTTP", False)

    assert _require_http_configuration() == {
        "authenticated": True,
        "development_override": False,
    }


def test_http_parent_runs_fastmcp_lifespan(monkeypatch):
    monkeypatch.setattr(settings, "SEO_AGENT_ENABLED", False)
    service_context.ctx = None
    with TestClient(_http_app_with_health(mcp)) as client:
        assert service_context.ctx is not None
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "tools": 15, "prompts": 50}


def test_llm_auto_selection_skips_unconfigured_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "configured")
    selected = []

    def fake_create(config):
        selected.append(config.provider)
        return SimpleNamespace(config=config)

    monkeypatch.setattr(LLMProviderFactory, "create", staticmethod(fake_create))
    context = ServiceContext()
    context._init_llm_sync()
    assert selected == ["openai"]
    assert context.llm_provider.config.provider == "openai"


@pytest.mark.asyncio
async def test_private_child_sitemap_is_blocked_before_fetch():
    parser = SitemapParserService()

    class NeverCalledClient:
        async def get(self, *args, **kwargs):
            raise AssertionError("private child must not be fetched")

    urls, warnings = await parser._resolve_index(
        NeverCalledClient(),
        ["http://127.0.0.1/private-sitemap.xml"],
        seen=set(),
        depth=1,
        max_depth=3,
    )
    assert urls == []
    assert warnings and "Blocked unsafe child sitemap" in warnings[0]
