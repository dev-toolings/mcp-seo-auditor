"""Autonomous end-to-end SEO agent tool."""

from seo_server import service_context as svc
from seo_server.schemas.agent import SeoAgentInput, SeoAgentOutput
from seo_server.server import mcp
from seo_server.tools._base import tool_handler


def _output(run) -> dict:
    return SeoAgentOutput(
        run_id=run.run_id,
        state=run.state.value,
        phase=run.phase,
        progress=run.progress,
        plan_hash=run.plan_hash,
        findings=[finding.model_dump(mode="json") for finding in run.findings],
        plan=run.plan.model_dump(mode="json") if run.plan else None,
        validations=run.validations,
        diff_summary=run.diff_summary,
        error=run.error,
        recoverable=run.recoverable,
        pr_url=run.pr_url,
    ).model_dump(mode="json")


@mcp.tool(
    name="seo_agent",
    description="""Run an autonomous, durable SEO/GEO audit-to-PR workflow.
Actions:
- start: Validate an authorized local Git workspace and begin the read-only audit. Requires workspace_path and a project .seo-agent.toml.
- status: Return durable progress, findings, approved plan, validations, diff summary and PR URL. Requires run_id.
- approve: Approve exactly the current plan_hash and allow worktree edits, tests, commit, push and PR creation.
- reject: Reject the proposed plan without modifying project files. Requires reason.
- resume: Resume a recoverable failed run from its durable checkpoint.
- cancel: Cancel a non-terminal run.
- cleanup: Remove a clean terminal worktree through git worktree remove. Run artifacts remain available.
- runtime: Show the selected non-interactive CLI (Codex, Claude, Grok, or custom).
- skills_plan: Generate or validate a declarative SkillManifest and return create/update/delete operations plus a plan hash.
- skills_apply: Apply an exact SkillManifest/plan_hash pair under an operator-authorized skill root.""",
    task=True,
)
@tool_handler
async def seo_agent(input: SeoAgentInput) -> dict:
    if input.action == "runtime":
        return svc.ctx.skill_lifecycle.runtime_status()
    if input.action == "skills_plan":
        manifest = input.manifest
        runtime: dict[str, str] | None = None
        if manifest is None:
            manifest, runtime = await svc.ctx.skill_lifecycle.generate_manifest(
                input.objective or "",
                input.workspace_path or "",
                prune=input.prune,
                model=input.model or "",
            )
        plan = svc.ctx.skill_lifecycle.plan(manifest, input.skill_root or "")
        result = plan.model_dump(mode="json")
        if runtime:
            result["runtime"] = runtime
        return result
    if input.action == "skills_apply":
        if input.manifest is None:  # Kept explicit for type checkers; schema validation rejects it.
            raise ValueError("skills_apply requires manifest")
        plan = svc.ctx.skill_lifecycle.apply(
            input.manifest,
            input.plan_hash or "",
            input.skill_root or "",
        )
        result = plan.model_dump(mode="json")
        result["applied"] = True
        return result
    supervisor = svc.ctx.agent_supervisor
    if input.action == "start":
        return _output(await supervisor.start(input.workspace_path or ""))
    if input.action == "status":
        return _output(await supervisor.status(input.run_id or ""))
    if input.action == "approve":
        return _output(await supervisor.approve(input.run_id or "", input.plan_hash or ""))
    if input.action == "reject":
        return _output(await supervisor.reject(input.run_id or "", input.reason or ""))
    if input.action == "resume":
        return _output(await supervisor.resume(input.run_id or ""))
    if input.action == "cancel":
        return _output(await supervisor.cancel(input.run_id or ""))
    return _output(await supervisor.cleanup(input.run_id or ""))
