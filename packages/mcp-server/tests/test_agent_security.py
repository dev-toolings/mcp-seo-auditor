from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.core.safe_http import safe_get
from app.models.agent_run import AgentAction, AgentPlan, AgentRun
from app.services.agent.cli_runner import AgentCLIRunner
from app.services.agent.config import AgentRuntimeConfig, ProjectPolicy
from app.services.agent.supervisor import AgentSupervisorError, SEOAgentSupervisor


@pytest.mark.asyncio
async def test_safe_get_blocks_private_redirect():
    async def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(Exception, match="private|Blocked"):
            await safe_get(client, "https://93.184.216.34/start")


def _policy():
    return ProjectPolicy.model_validate(
        {
            "version": 1,
            "site": {"base_url": "https://x.test", "sitemap_url": "https://x.test/s.xml"},
            "workspace": {"allow": ["src/**"], "deny": [".env*", "**/.env*"]},
            "validation": {"commands": [["bun", "test"]]},
            "preview": {"command": ["bun", "dev", "{port}"]},
        }
    )


@pytest.mark.asyncio
async def test_diff_rejects_denied_path(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    await _git(workspace, "init")
    await _git(workspace, "config", "user.email", "test@example.com")
    await _git(workspace, "config", "user.name", "Test")
    (workspace / ".env.local").write_text("SECRET=x")
    await _git(workspace, "add", ".")
    await _git(workspace, "commit", "-m", "initial")
    (workspace / ".env.local").write_text("SECRET=y")

    supervisor = SEOAgentSupervisor(object())
    supervisor.repository = _NoopRepository()
    run = AgentRun(
        workspace_path=str(workspace),
        worktree_path=str(workspace),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
    )
    Path(run.artifact_path).mkdir()
    with pytest.raises(AgentSupervisorError, match="Denied path"):
        await supervisor._inspect_diff(run, _policy())


def test_sandbox_hides_gh_and_uses_no_shell(tmp_path):
    config = AgentRuntimeConfig(version=1, argv=["/bin/echo", "{prompt}"], sandbox=True)
    runner = AgentCLIRunner(config, _NoopRepository())
    workspace = tmp_path / "work"
    artifacts = tmp_path / "artifacts" / "phase"
    workspace.mkdir()
    (workspace / ".git").write_text("gitdir: /tmp/read-only")
    artifacts.mkdir(parents=True)
    argv = runner._sandbox_argv(["/bin/echo", "ok"], workspace, artifacts, writable=True)
    assert argv[0].endswith("bwrap")
    assert "--bind" in argv
    assert argv.count(str(workspace / ".git")) == 2
    if Path("/usr/bin/gh").exists():
        assert "/usr/bin/gh" in argv


@pytest.mark.asyncio
async def test_fake_cli_runs_in_sandbox_and_returns_json(tmp_path):
    workspace = tmp_path / "work"
    workspace.mkdir()
    artifacts = tmp_path / "artifacts"
    run = AgentRun(
        workspace_path=str(workspace),
        worktree_path=str(workspace),
        artifact_path=str(artifacts),
        base_commit="a" * 40,
        base_branch="main",
    )
    config = AgentRuntimeConfig(
        version=1,
        argv=[
            "python3",
            "-c",
            "__import__('builtins').print(__import__('json').dumps({'phase': 'analyst'}))",
        ],
    )
    result = await AgentCLIRunner(config, _NoopRepository()).run_phase(
        run, "analyst", "inspect", writable=False
    )
    assert result == {"phase": "analyst"}


@pytest.mark.asyncio
async def test_diff_rejects_allowed_path_not_in_approved_plan(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    await _git(workspace, "init")
    await _git(workspace, "config", "user.email", "test@example.com")
    await _git(workspace, "config", "user.name", "Test")
    (workspace / "src").mkdir()
    (workspace / "src/page.txt").write_text("original")
    (workspace / "src/extra.txt").write_text("original")
    await _git(workspace, "add", ".")
    await _git(workspace, "commit", "-m", "initial")
    (workspace / "src/extra.txt").write_text("unapproved")

    run = AgentRun(
        workspace_path=str(workspace),
        worktree_path=str(workspace),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
        plan=AgentPlan(
            summary="Approved page only",
            actions=[
                AgentAction(
                    action_id="A-1",
                    finding_ids=["F-1"],
                    title="Page",
                    change_type="content",
                    target_files=["src/page.txt"],
                    risk="low",
                    rationale="Evidence",
                    expected_result="Better page",
                )
            ],
        ),
    )
    Path(run.artifact_path).mkdir()
    supervisor = SEOAgentSupervisor(object())
    supervisor.repository = _NoopRepository()
    with pytest.raises(AgentSupervisorError, match="approved plan"):
        await supervisor._inspect_diff(run, _policy())


@pytest.mark.asyncio
async def test_untracked_file_is_in_actual_diff_artifact(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    await _git(workspace, "init")
    await _git(workspace, "config", "user.email", "test@example.com")
    await _git(workspace, "config", "user.name", "Test")
    (workspace / "src").mkdir()
    (workspace / "src/page.txt").write_text("original")
    await _git(workspace, "add", ".")
    await _git(workspace, "commit", "-m", "initial")
    (workspace / "src/new.txt").write_text("new content")

    run = AgentRun(
        workspace_path=str(workspace),
        worktree_path=str(workspace),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
        plan=AgentPlan(
            summary="Add page",
            actions=[
                AgentAction(
                    action_id="A-1",
                    finding_ids=["F-1"],
                    title="New page",
                    change_type="content",
                    target_files=["src/new.txt"],
                    risk="low",
                    rationale="Evidence",
                    expected_result="New page",
                )
            ],
        ),
    )
    Path(run.artifact_path).mkdir()
    supervisor = SEOAgentSupervisor(object())
    supervisor.repository = _NoopRepository()
    summary = await supervisor._inspect_diff(run, _policy())
    assert summary["files"] == ["src/new.txt"]
    assert "new content" in (Path(run.artifact_path) / "changes.diff").read_text()


async def _git(cwd: Path, *args: str):
    proc = await __import__("asyncio").create_subprocess_exec(
        "git", *args, cwd=cwd, stdout=-1, stderr=-1
    )
    _, stderr = await proc.communicate()
    assert proc.returncode == 0, stderr.decode()


class _NoopRepository:
    async def add_command_log(self, *args, **kwargs):
        return None


def test_workspace_symlink_cannot_escape_allowed_root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (outside / ".git").mkdir()
    link = allowed / "linked-repo"
    link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(settings, "SEO_AGENT_ALLOWED_ROOTS", str(allowed))
    supervisor = SEOAgentSupervisor(object())
    with pytest.raises(AgentSupervisorError, match="outside SEO_AGENT_ALLOWED_ROOTS"):
        supervisor._resolve_workspace(str(link))
