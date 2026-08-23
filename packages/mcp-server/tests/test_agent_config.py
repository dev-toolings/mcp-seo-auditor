import json

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.models.agent_run import AgentAction, AgentPlan, AgentRun, AgentRunState, Finding
from app.services.agent.config import (
    AgentRuntimeConfig,
    ProjectPolicy,
    load_project_policy,
    load_runtime_config,
)
from app.services.agent.supervisor import SEOAgentSupervisor

POLICY = """
version = 1

[site]
base_url = "https://example.com"
sitemap_url = "https://example.com/sitemap.xml"
language = "fr"

[workspace]
allow = ["src/**", "app/**"]
deny = [".env*", "**/.env*"]

[validation]
commands = [["bun", "run", "lint"], ["bun", "test"]]

[preview]
command = ["bun", "run", "dev", "--", "--port", "{port}"]
url_template = "http://127.0.0.1:{port}"

[git]
base_branch = "main"

[limits]
max_files = 20
max_diff_lines = 2000
"""


def test_project_policy_loads(tmp_path):
    (tmp_path / ".seo-agent.toml").write_text(POLICY)
    policy = load_project_policy(tmp_path)
    assert policy.site.language == "fr"
    assert policy.validation.commands[0] == ["bun", "run", "lint"]


def test_operator_limits_cap_project_policy(tmp_path, monkeypatch):
    (tmp_path / ".seo-agent.toml").write_text(POLICY)
    monkeypatch.setattr(settings, "SEO_AGENT_MAX_FILES", 7)
    monkeypatch.setattr(settings, "SEO_AGENT_MAX_DIFF_LINES", 500)
    policy = load_project_policy(tmp_path)
    assert policy.limits.max_files == 7
    assert policy.limits.max_diff_lines == 500


def test_project_policy_rejects_npm():
    data = {
        "version": 1,
        "site": {"base_url": "https://x.test", "sitemap_url": "https://x.test/s.xml"},
        "workspace": {"allow": ["src/**"]},
        "validation": {"commands": [["npm", "test"]]},
        "preview": {"command": ["bun", "dev", "{port}"]},
    }
    with pytest.raises(ValidationError, match="direct argv"):
        ProjectPolicy.model_validate(data)


def test_project_policy_rejects_shell_command():
    data = {
        "version": 1,
        "site": {"base_url": "https://x.test", "sitemap_url": "https://x.test/s.xml"},
        "workspace": {"allow": ["src/**"]},
        "validation": {"commands": [["sh", "-c", "touch ../escaped"]]},
        "preview": {"command": ["bun", "dev", "{port}"]},
    }
    with pytest.raises(ValidationError, match="direct argv"):
        ProjectPolicy.model_validate(data)


def test_runtime_command_rejects_shell_separator():
    with pytest.raises(ValidationError, match="shell separators"):
        AgentRuntimeConfig(version=1, argv=["agent; rm"])


def test_runtime_config_is_operator_owned(tmp_path, monkeypatch):
    path = tmp_path / "runtime.toml"
    path.write_text('version=1\nargv=["fake-agent", "{prompt_file}"]\nprompt_mode="file"\n')
    monkeypatch.setattr(settings, "SEO_AGENT_RUNTIME_CONFIG", str(path))
    runtime = load_runtime_config()
    assert runtime.argv[0] == "fake-agent"


def test_plan_hash_is_stable_and_changes_with_plan():
    action = AgentAction(
        action_id="A-1",
        finding_ids=["F-1"],
        title="Fix title",
        change_type="metadata",
        risk="low",
        rationale="Missing title",
        expected_result="Title present",
    )
    plan = AgentPlan(summary="SEO fixes", actions=[action])
    first = SEOAgentSupervisor._plan_hash(plan)
    second = SEOAgentSupervisor._plan_hash(AgentPlan.model_validate_json(plan.model_dump_json()))
    assert first == second
    plan.summary = "Different"
    assert SEOAgentSupervisor._plan_hash(plan) != first


def test_agent_run_json_round_trip(tmp_path):
    run = AgentRun(
        workspace_path=str(tmp_path),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
        state=AgentRunState.AWAITING_APPROVAL,
        findings=[
            Finding(
                finding_id="F-1",
                claim="Missing title",
                status="observed",
                severity="high",
                confidence=1,
                recommendation="Add it",
                verification="Title exists",
            )
        ],
    )
    restored = AgentRun.model_validate_json(run.model_dump_json())
    assert json.loads(restored.model_dump_json())["findings"][0]["finding_id"] == "F-1"
