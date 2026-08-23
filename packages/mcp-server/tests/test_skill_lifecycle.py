import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.models.skill_manifest import ManagedSkill, SkillManifest
from app.services.agent import config as agent_config
from app.services.agent.cli_runner import AgentCLIRunner
from app.services.agent.config import AgentRuntimeConfig, detect_runtime_config
from app.services.agent.skill_lifecycle import SkillLifecycleError, SkillLifecycleService
from seo_server.schemas.agent import SeoAgentInput


def _manifest(instructions: str = "Inspect the exact project policy.", *, prune: bool = False):
    return SkillManifest(
        skills=[
            ManagedSkill(
                name="seo-policy",
                description="Review project-specific SEO policy and constraints.",
                instructions=instructions,
                files={"references/checks.md": "# Checks\n\nVerify canonical URLs.\n"},
            )
        ],
        prune=prune,
    )


def test_skill_lifecycle_create_update_and_prune(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    monkeypatch.setattr(settings, "SEO_AGENT_SKILL_ROOTS", str(root))
    monkeypatch.setattr(settings, "SEO_AGENT_ENABLED", True)
    service = SkillLifecycleService()

    create = service.plan(_manifest())
    assert [(item.action, item.name) for item in create.operations] == [("create", "seo-policy")]
    service.apply(create.manifest, create.plan_hash)
    skill = root / "seo-policy"
    assert (skill / "SKILL.md").is_file()
    assert (skill / ".mcp-seo-auditor-managed.json").is_file()
    assert service.plan(_manifest()).operations[0].action == "unchanged"

    update = service.plan(_manifest("Use the current policy and cite exact evidence."))
    assert update.operations[0].action == "update"
    service.apply(update.manifest, update.plan_hash)
    assert "cite exact evidence" in (skill / "SKILL.md").read_text()

    manual = root / "manual-skill"
    manual.mkdir()
    (manual / "SKILL.md").write_text("manual")
    prune = service.plan(SkillManifest(skills=[], prune=True))
    assert [(item.action, item.name) for item in prune.operations] == [("delete", "seo-policy")]
    service.apply(prune.manifest, prune.plan_hash)
    assert not skill.exists()
    assert manual.exists()


def test_skill_lifecycle_refuses_unmanaged_collision(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    target = root / "seo-policy"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("manual")
    monkeypatch.setattr(settings, "SEO_AGENT_SKILL_ROOTS", str(root))
    with pytest.raises(SkillLifecycleError, match="unmanaged"):
        SkillLifecycleService().plan(_manifest())


def test_skill_lifecycle_refuses_symlinked_target(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "seo-policy").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(settings, "SEO_AGENT_SKILL_ROOTS", str(root))

    with pytest.raises(SkillLifecycleError, match="unsafe skill target"):
        SkillLifecycleService().plan(_manifest())


def test_skill_lifecycle_rejects_stale_hash(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    monkeypatch.setattr(settings, "SEO_AGENT_SKILL_ROOTS", str(root))
    monkeypatch.setattr(settings, "SEO_AGENT_ENABLED", True)
    service = SkillLifecycleService()
    plan = service.plan(_manifest())
    with pytest.raises(SkillLifecycleError, match="hash changed"):
        service.apply(_manifest("different"), plan.plan_hash)
    assert not (root / "seo-policy").exists()


def test_skill_manifest_rejects_resource_traversal():
    with pytest.raises(ValidationError, match="unsafe skill resource"):
        ManagedSkill(
            name="unsafe",
            description="Unsafe resource path used for validation.",
            instructions="Do work.",
            files={"references/../../escape": "bad"},
        )


def test_runtime_auto_detection_prefers_codex(monkeypatch):
    monkeypatch.setattr(settings, "SEO_AGENT_PROVIDER", "auto")
    monkeypatch.setattr(settings, "SEO_AGENT_PROVIDER_ORDER", "codex,claude,grok")
    monkeypatch.setattr(settings, "SEO_AGENT_MODEL", "defined-model")
    monkeypatch.setattr(
        agent_config.shutil,
        "which",
        lambda name: "/usr/bin/codex" if name == "codex" else None,
    )
    runtime = detect_runtime_config()
    assert runtime.provider == "codex"
    assert runtime.model == "defined-model"
    assert runtime.sandbox is False


@pytest.mark.parametrize(
    ("available", "expected"),
    [({"claude"}, "claude"), ({"grok"}, "grok")],
)
def test_runtime_auto_detection_falls_back_in_order(monkeypatch, available, expected):
    monkeypatch.setattr(settings, "SEO_AGENT_PROVIDER", "auto")
    monkeypatch.setattr(settings, "SEO_AGENT_PROVIDER_ORDER", "codex,claude,grok")
    monkeypatch.setattr(settings, "SEO_AGENT_MODEL", "")
    monkeypatch.setattr(
        agent_config.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in available else None,
    )
    assert detect_runtime_config().provider == expected


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("codex", ["exec", "--ephemeral", "--sandbox", "read-only"]),
        ("claude", ["-p", "--no-session-persistence"]),
        ("grok", ["--permission-mode", "plan", "--disable-web-search"]),
    ],
)
def test_builtin_provider_commands_are_non_interactive(tmp_path, provider, expected):
    runtime = AgentRuntimeConfig(
        version=1,
        provider=provider,
        argv=[f"/usr/bin/{provider}"],
        model="defined-model",
        sandbox=False,
    )
    argv = AgentCLIRunner(runtime)._provider_argv("return json", tmp_path, writable=False)
    for token in expected:
        assert token in argv
    assert "defined-model" in argv


def test_agent_result_decoder_accepts_markdown_fence():
    result = AgentCLIRunner._decode_result('```json\n{"version": 1}\n```')
    assert result == {"version": 1}


def test_agent_skill_actions_validate_required_fields():
    assert SeoAgentInput(action="runtime").action == "runtime"
    with pytest.raises(ValidationError, match="manifest and plan_hash"):
        SeoAgentInput(action="skills_apply")
