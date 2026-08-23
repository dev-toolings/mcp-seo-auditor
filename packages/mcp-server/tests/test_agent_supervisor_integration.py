import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from app.core.config import settings
from app.models.agent_run import AgentAction, AgentPlan, AgentRun, AgentRunState
from app.services.agent import supervisor as supervisor_module
from app.services.agent.config import ProjectPolicy
from app.services.agent.supervisor import SEOAgentSupervisor

POLICY = """
version = 1

[site]
base_url = "https://example.com"
sitemap_url = "https://example.com/sitemap.xml"

[workspace]
allow = ["src/**"]
deny = [".env*", "**/.env*"]

[validation]
commands = [["python3", "-c", "from pathlib import Path; assert Path('src/page.txt').read_text().strip() == 'optimized'"]]

[preview]
command = ["python3", "-m", "http.server", "{port}"]
url_template = "http://127.0.0.1:{port}"

[git]
base_branch = "main"

[limits]
max_files = 5
max_diff_lines = 100
max_repair_cycles = 1
"""


class _FullAudit:
    async def run(self, *args, **kwargs):
        return {"overall_score": 40, "dimension_scores": {"technical": 40}}


class _Context:
    full_audit = _FullAudit()


@pytest.mark.asyncio
async def test_full_run_preserves_primary_checkout_until_approval(tmp_path, monkeypatch):
    repo = tmp_path / "site"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "src").mkdir()
    (repo / "src/page.txt").write_text("original\n")
    (repo / ".seo-agent.toml").write_text(POLICY)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    (repo / "notes.txt").write_text("user dirty file\n")

    runtime = tmp_path / "runtime.toml"
    runtime.write_text('version=1\nargv=["fake"]\n')
    monkeypatch.setattr(settings, "SEO_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "SEO_AGENT_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setattr(settings, "SEO_AGENT_RUNTIME_CONFIG", str(runtime))
    monkeypatch.setattr(settings, "SEO_AGENT_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setattr(settings, "SEO_AGENT_WORKTREE_ROOT", str(tmp_path / "worktrees"))
    monkeypatch.setattr(settings, "SQLITE_DB_PATH", str(tmp_path / "runs.db"))
    monkeypatch.setattr(supervisor_module.shutil, "which", lambda command: f"/usr/bin/{command}")

    async def fake_phase(self, run, phase, prompt, *, writable):
        if phase == "analyst":
            return {
                "findings": [
                    {
                        "finding_id": "F-1",
                        "claim": "Page needs optimization",
                        "status": "observed",
                        "severity": "high",
                        "confidence": 1,
                        "recommendation": "Optimize page",
                        "verification": "File contains optimized content",
                    }
                ]
            }
        if phase == "planner":
            return {
                "version": 1,
                "summary": "Optimize the page",
                "actions": [
                    {
                        "action_id": "A-1",
                        "finding_ids": ["F-1"],
                        "title": "Optimize page",
                        "change_type": "content",
                        "target_files": ["src/page.txt"],
                        "risk": "low",
                        "rationale": "Audit evidence",
                        "expected_result": "Optimized page",
                        "verification": ["validation command passes"],
                    }
                ],
            }
        if phase == "implementer":
            Path(run.worktree_path, "src/page.txt").write_text("optimized\n")
            return {"summary": "done", "finding_ids_implemented": ["F-1"]}
        return {"approved": True, "issues": [], "verified_finding_ids": ["F-1"]}

    monkeypatch.setattr(supervisor_module.AgentCLIRunner, "run_phase", fake_phase)

    async def fake_reaudit(self, run, policy):
        return {"overall_score": 80, "dimension_scores": {"technical": 80}}

    async def fake_deliver(self, run, policy):
        run.pr_url = "https://github.com/example/site/pull/1"
        await self._checkpoint(run, AgentRunState.PUSHING, "push", 94)
        await self._checkpoint(run, AgentRunState.OPENING_PR, "pull_request", 98)
        await self._checkpoint(run, AgentRunState.COMPLETED, "completed", 100)

    monkeypatch.setattr(SEOAgentSupervisor, "_preview_and_reaudit", fake_reaudit)
    monkeypatch.setattr(SEOAgentSupervisor, "_deliver", fake_deliver)

    supervisor = SEOAgentSupervisor(_Context())
    run = await supervisor.start(str(repo))
    run = await _wait_state(supervisor, run.run_id, AgentRunState.AWAITING_APPROVAL)
    assert (repo / "src/page.txt").read_text() == "original\n"
    assert (repo / "notes.txt").read_text() == "user dirty file\n"
    gsc = json.loads((Path(run.artifact_path) / "gsc-keywords.json").read_text())
    assert gsc["status"] == "missing"

    await supervisor.approve(run.run_id, run.plan_hash)
    completed = await _wait_state(supervisor, run.run_id, AgentRunState.COMPLETED)
    assert completed.pr_url.endswith("/1")
    assert (repo / "src/page.txt").read_text() == "original\n"
    assert Path(completed.worktree_path, "src/page.txt").read_text() == "optimized\n"
    assert _git_output(Path(completed.worktree_path), "status", "--porcelain") == ""

    cleaned = await supervisor.cleanup(run.run_id)
    assert cleaned.worktree_path is None
    await supervisor.shutdown()


@pytest.mark.asyncio
async def test_delivery_uses_https_push_and_opens_ready_pr(tmp_path):
    policy = ProjectPolicy.model_validate(
        {
            "version": 1,
            "site": {"base_url": "https://x.test", "sitemap_url": "https://x.test/s.xml"},
            "workspace": {"allow": ["src/**"]},
            "validation": {"commands": [["bun", "test"]]},
            "preview": {"command": ["bun", "start", "{port}"]},
        }
    )
    workspace = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    artifacts = tmp_path / "artifacts"
    workspace.mkdir()
    worktree.mkdir()
    artifacts.mkdir()
    plan = AgentPlan(
        summary="Improve metadata",
        actions=[
            AgentAction(
                action_id="A-1",
                finding_ids=["F-1"],
                title="Metadata",
                change_type="metadata",
                target_files=["src/page.tsx"],
                risk="low",
                rationale="Evidence",
                expected_result="Metadata present",
            )
        ],
    )
    run = AgentRun(
        workspace_path=str(workspace),
        worktree_path=str(worktree),
        artifact_path=str(artifacts),
        base_commit="a" * 40,
        base_branch="main",
        branch_name="seo-agent/20260731-test",
        state=AgentRunState.COMMITTING,
        plan=plan,
    )
    supervisor = SEOAgentSupervisor(_Context())
    await supervisor.repository.create(run)
    calls = []

    async def fake_git_output(cwd, args):
        return "git@github.com:example/site.git\n"

    async def fake_run_logged(run, phase, argv, **kwargs):
        calls.append((phase, argv))
        return "https://github.com/example/site/pull/42\n" if phase == "pull_request" else ""

    supervisor._git_output = fake_git_output
    supervisor._run_logged = fake_run_logged
    await supervisor._deliver(run, policy)
    push = next(argv for phase, argv in calls if phase == "push")
    pull_request = next(argv for phase, argv in calls if phase == "pull_request")
    assert "https://github.com/example/site.git" in push
    assert pull_request[:3] == ["gh", "pr", "create"]
    assert "--draft" not in pull_request
    assert run.state == AgentRunState.COMPLETED
    assert run.pr_url.endswith("/42")
    await supervisor.shutdown()


async def _wait_state(supervisor, run_id, expected):
    for _ in range(200):
        run = await supervisor.status(run_id)
        if run.state == expected:
            return run
        if run.state in {AgentRunState.FAILED, AgentRunState.RECOVERABLE}:
            raise AssertionError(run.error)
        await asyncio.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {expected}")


def _git(cwd: Path, *args: str):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_output(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()
