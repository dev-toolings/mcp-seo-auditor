import pytest

from app.models.agent_run import AgentRun, AgentRunState
from app.repositories.agent_run_repository import AgentRunRepository
from app.services.agent.supervisor import AgentSupervisorError, SEOAgentSupervisor


@pytest.mark.asyncio
async def test_agent_run_persists_and_enforces_workspace_lock(tmp_path):
    repo = AgentRunRepository(str(tmp_path / "runs.db"))
    run = AgentRun(
        workspace_path=str(tmp_path / "repo"),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
    )
    await repo.create(run)
    restored = await repo.get(run.run_id)
    assert restored and restored.state == AgentRunState.QUEUED
    assert (await repo.active_for_workspace(run.workspace_path)).run_id == run.run_id

    duplicate = run.model_copy(update={"run_id": "other"})
    with pytest.raises(Exception):
        await repo.create(duplicate)

    run.state = AgentRunState.COMPLETED
    await repo.save(run)
    assert await repo.active_for_workspace(run.workspace_path) is None
    await repo.close()


@pytest.mark.asyncio
async def test_resumable_excludes_approval_and_terminal_states(tmp_path):
    repo = AgentRunRepository(str(tmp_path / "runs.db"))
    for index, state in enumerate(
        [AgentRunState.AUDITING, AgentRunState.AWAITING_APPROVAL, AgentRunState.COMPLETED]
    ):
        run = AgentRun(
            run_id=f"run-{index}",
            workspace_path=str(tmp_path / f"repo-{index}"),
            artifact_path=str(tmp_path / f"artifacts-{index}"),
            base_commit="a" * 40,
            base_branch="main",
            state=state,
        )
        await repo.create(run)
    assert [run.run_id for run in await repo.resumable()] == ["run-0"]
    await repo.close()


@pytest.mark.asyncio
async def test_changed_plan_invalidates_previous_approval_hash(tmp_path):
    from app.models.agent_run import AgentAction, AgentPlan

    repository = AgentRunRepository(str(tmp_path / "runs.db"))
    plan = AgentPlan(
        summary="Original",
        actions=[
            AgentAction(
                action_id="A-1",
                finding_ids=["F-1"],
                title="Fix",
                change_type="content",
                target_files=["src/page.tsx"],
                risk="low",
                rationale="Evidence",
                expected_result="Fixed",
            )
        ],
    )
    run = AgentRun(
        workspace_path=str(tmp_path / "repo"),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
        state=AgentRunState.AWAITING_APPROVAL,
        plan=plan,
        plan_hash=SEOAgentSupervisor._plan_hash(plan),
    )
    old_hash = run.plan_hash
    run.plan.summary = "Changed after presentation"
    await repository.create(run)
    supervisor = SEOAgentSupervisor(object())
    supervisor.repository = repository
    with pytest.raises(AgentSupervisorError, match="plan_hash"):
        await supervisor.approve(run.run_id, old_hash)
    await repository.close()


@pytest.mark.asyncio
async def test_cancel_is_durable(tmp_path):
    repository = AgentRunRepository(str(tmp_path / "runs.db"))
    run = AgentRun(
        workspace_path=str(tmp_path / "repo"),
        artifact_path=str(tmp_path / "artifacts"),
        base_commit="a" * 40,
        base_branch="main",
    )
    await repository.create(run)
    supervisor = SEOAgentSupervisor(object())
    supervisor.repository = repository
    cancelled = await supervisor.cancel(run.run_id)
    assert cancelled.state == AgentRunState.CANCELLED
    assert (await repository.get(run.run_id)).state == AgentRunState.CANCELLED
    await repository.close()


def test_invalid_state_transition_is_rejected():
    with pytest.raises(AgentSupervisorError, match="Invalid agent state transition"):
        SEOAgentSupervisor._assert_transition(AgentRunState.AUDITING, AgentRunState.COMMITTING)
