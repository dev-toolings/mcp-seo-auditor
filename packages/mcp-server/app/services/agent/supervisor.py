"""Durable audit -> approve -> implement -> verify -> PR supervisor."""

import asyncio
import fnmatch
import hashlib
import json
import os
import re
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.core.security import trusted_local_urls
from app.models.agent_run import (
    TERMINAL_AGENT_STATES,
    AgentPlan,
    AgentRun,
    AgentRunState,
    Finding,
)
from app.repositories.agent_run_repository import AgentRunRepository
from app.services.agent.cli_runner import AgentCLIRunner
from app.services.agent.config import (
    ProjectPolicy,
    allowed_workspace_roots,
    load_project_policy,
    load_runtime_config,
)


class AgentSupervisorError(RuntimeError):
    pass


class SEOAgentSupervisor:
    _TRANSITIONS = {
        AgentRunState.QUEUED: {AgentRunState.AUDITING},
        AgentRunState.AUDITING: {AgentRunState.PLANNING},
        AgentRunState.PLANNING: {AgentRunState.AWAITING_APPROVAL},
        AgentRunState.AWAITING_APPROVAL: {AgentRunState.IMPLEMENTING},
        AgentRunState.IMPLEMENTING: {AgentRunState.VALIDATING, AgentRunState.PUSHING},
        AgentRunState.VALIDATING: {AgentRunState.REAUDITING},
        AgentRunState.REAUDITING: {AgentRunState.REVIEWING},
        AgentRunState.REVIEWING: {AgentRunState.VALIDATING, AgentRunState.COMMITTING},
        AgentRunState.COMMITTING: {AgentRunState.PUSHING},
        AgentRunState.PUSHING: {AgentRunState.OPENING_PR},
        AgentRunState.OPENING_PR: {AgentRunState.COMPLETED},
        AgentRunState.RECOVERABLE: {AgentRunState.AUDITING, AgentRunState.IMPLEMENTING},
    }

    def __init__(self, service_context):
        self.ctx = service_context
        self.repository = AgentRunRepository(settings.SQLITE_DB_PATH)
        self._tasks: dict[str, asyncio.Task] = {}
        self._semaphore = asyncio.Semaphore(settings.SEO_AGENT_MAX_CONCURRENT_RUNS)

    async def start(self, workspace_path: str) -> AgentRun:
        self._require_enabled()
        workspace = self._resolve_workspace(workspace_path)
        runtime = load_runtime_config()
        if settings.SEO_AGENT_RUNTIME_CONFIG.strip():
            runtime_path = Path(settings.SEO_AGENT_RUNTIME_CONFIG).expanduser().resolve(strict=True)
            if runtime_path == workspace or runtime_path.is_relative_to(workspace):
                raise AgentSupervisorError(
                    "Operator runtime config must be outside the audited repo"
                )
        executable = runtime.argv[0]
        if not shutil.which(executable) and not (
            Path(executable).is_absolute() and Path(executable).is_file()
        ):
            raise AgentSupervisorError(f"Configured agent executable is missing: {executable}")
        active = await self.repository.active_for_workspace(str(workspace))
        if active:
            raise AgentSupervisorError(
                f"Workspace already has active run {active.run_id} ({active.state.value})"
            )
        policy = load_project_policy(workspace)
        base_commit = await self._git_output(
            workspace, ["rev-parse", "--verify", f"{policy.git.base_branch}^{{commit}}"]
        )

        artifact_root = Path(settings.SEO_AGENT_ARTIFACT_ROOT).expanduser().resolve()
        worktree_root = Path(settings.SEO_AGENT_WORKTREE_ROOT).expanduser().resolve()
        artifact_root.mkdir(parents=True, exist_ok=True)
        worktree_root.mkdir(parents=True, exist_ok=True)

        provisional = AgentRun(
            workspace_path=str(workspace),
            artifact_path="",
            base_commit=base_commit.strip(),
            base_branch=policy.git.base_branch,
        )
        artifact_path = artifact_root / provisional.run_id
        worktree_path = worktree_root / f"{workspace.name}-{provisional.run_id[:10]}"
        artifact_path.mkdir(parents=True, exist_ok=False)
        await self._run_raw(
            workspace,
            ["git", "worktree", "add", "--detach", str(worktree_path), provisional.base_commit],
        )
        provisional.artifact_path = str(artifact_path)
        provisional.worktree_path = str(worktree_path)
        try:
            await self.repository.create(provisional)
        except Exception:
            await self._run_raw(workspace, ["git", "worktree", "remove", str(worktree_path)])
            artifact_path.rmdir()
            raise
        self._schedule(
            provisional.run_id,
            self._prepare(provisional.run_id),
            timeout_seconds=policy.limits.max_minutes * 60,
        )
        return provisional

    async def status(self, run_id: str) -> AgentRun:
        run = await self._require_run(run_id)
        return run

    async def approve(self, run_id: str, plan_hash: str) -> AgentRun:
        run = await self._require_run(run_id)
        if run.state != AgentRunState.AWAITING_APPROVAL:
            raise AgentSupervisorError(f"Run is not awaiting approval: {run.state.value}")
        current_hash = self._plan_hash(run.plan) if run.plan else None
        if not current_hash or run.plan_hash != current_hash or plan_hash != current_hash:
            raise AgentSupervisorError("Approval rejected: plan_hash does not match current plan")
        self._assert_transition(run.state, AgentRunState.IMPLEMENTING)
        run.approved_at = datetime.now(timezone.utc)
        run.state = AgentRunState.IMPLEMENTING
        run.phase = "approved"
        run.progress = 45
        await self.repository.save(run)
        policy = load_project_policy(Path(run.worktree_path or ""))
        self._schedule(
            run.run_id,
            self._execute(run.run_id),
            timeout_seconds=policy.limits.max_minutes * 60,
        )
        return run

    async def reject(self, run_id: str, reason: str) -> AgentRun:
        run = await self._require_run(run_id)
        if run.state != AgentRunState.AWAITING_APPROVAL:
            raise AgentSupervisorError(f"Run is not awaiting approval: {run.state.value}")
        self._assert_transition(run.state, AgentRunState.CANCELLED)
        run.state = AgentRunState.CANCELLED
        run.phase = "rejected"
        run.error = reason
        run.recoverable = False
        await self.repository.save(run)
        return run

    async def cancel(self, run_id: str) -> AgentRun:
        run = await self._require_run(run_id)
        if run.state in TERMINAL_AGENT_STATES:
            return run
        task = self._tasks.get(run_id)
        if task:
            task.cancel()
        self._assert_transition(run.state, AgentRunState.CANCELLED)
        run.state = AgentRunState.CANCELLED
        run.phase = "cancelled"
        run.recoverable = False
        await self.repository.save(run)
        return run

    async def resume(self, run_id: str) -> AgentRun:
        run = await self._require_run(run_id)
        if run.state != AgentRunState.RECOVERABLE or not run.recoverable:
            raise AgentSupervisorError("Only recoverable runs can be resumed")
        run.error = None
        if run.approved_at:
            self._assert_transition(run.state, AgentRunState.IMPLEMENTING)
            run.state = AgentRunState.IMPLEMENTING
            await self.repository.save(run)
            coroutine = self._execute(run_id)
        else:
            self._assert_transition(run.state, AgentRunState.AUDITING)
            run.state = AgentRunState.AUDITING
            await self.repository.save(run)
            coroutine = self._prepare(run_id)
        policy = load_project_policy(Path(run.worktree_path or ""))
        self._schedule(run_id, coroutine, timeout_seconds=policy.limits.max_minutes * 60)
        return run

    async def cleanup(self, run_id: str) -> AgentRun:
        run = await self._require_run(run_id)
        if run.state not in TERMINAL_AGENT_STATES:
            raise AgentSupervisorError("Only terminal runs can be cleaned up")
        worktree = Path(run.worktree_path or "")
        if worktree.exists():
            dirty = await self._git_output(worktree, ["status", "--porcelain"])
            if dirty.strip():
                raise AgentSupervisorError("Refusing cleanup: worktree has uncommitted changes")
            head = (await self._git_output(worktree, ["rev-parse", "HEAD"])).strip()
            if head != run.base_commit and not run.pr_url:
                raise AgentSupervisorError(
                    "Refusing cleanup: committed changes are not attached to a created PR"
                )
            await self._run_raw(
                Path(run.workspace_path), ["git", "worktree", "remove", str(worktree)]
            )
        run.worktree_path = None
        run.phase = "cleaned_up"
        await self.repository.save(run)
        return run

    async def resume_pending(self) -> None:
        if not settings.SEO_AGENT_ENABLED:
            return
        for run in await self.repository.resumable():
            if run.state == AgentRunState.AWAITING_APPROVAL:
                continue
            coroutine = self._execute(run.run_id) if run.approved_at else self._prepare(run.run_id)
            policy = load_project_policy(Path(run.worktree_path or ""))
            self._schedule(
                run.run_id,
                coroutine,
                timeout_seconds=policy.limits.max_minutes * 60,
            )

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        await self.repository.close()

    async def _prepare(self, run_id: str) -> None:
        async with self._semaphore:
            try:
                run = await self._require_run(run_id)
                policy = load_project_policy(Path(run.worktree_path or ""))
                runtime = load_runtime_config()
                runner = AgentCLIRunner(runtime, self.repository)

                await self._checkpoint(run, AgentRunState.AUDITING, "site_audit", 10)
                audit = await self.ctx.full_audit.run(
                    policy.site.sitemap_url,
                    max_pages=min(200, policy.limits.max_files * 4),
                    include_cwv=True,
                    language=policy.site.language,
                )
                if audit.get("error"):
                    raise AgentSupervisorError(f"Initial audit failed: {audit['error']}")
                run.audit_before = audit
                self._write_json(run, "audit-before.json", audit)
                gsc_data: dict[str, Any]
                if policy.site.gsc_property:
                    raw_gsc = await self.ctx.gsc.get_performance(
                        days=90,
                        dimensions=["query", "page"],
                        site_url=policy.site.gsc_property,
                    )
                    if raw_gsc.get("error"):
                        gsc_data = {
                            "status": "missing",
                            "source": "google_search_console",
                            "reason": raw_gsc["error"],
                            "rows": [],
                        }
                    else:
                        gsc_data = {
                            "status": "observed",
                            "source": "google_search_console",
                            **raw_gsc,
                        }
                else:
                    gsc_data = {
                        "status": "missing",
                        "source": "google_search_console",
                        "reason": "site.gsc_property is not configured",
                        "rows": [],
                    }
                self._write_json(run, "gsc-keywords.json", gsc_data)

                analyst_prompt = self._phase_prompt(
                    "analyst",
                    run,
                    "Read audit-before.json and inspect the repository read-only. Return JSON "
                    "Use gsc-keywords.json as the only external keyword source. "
                    "with a 'findings' array matching the documented Finding contract. Every "
                    "claim must cite observed/provided evidence; missing information must use "
                    "status='missing'.",
                )
                analyst = await runner.run_phase(run, "analyst", analyst_prompt, writable=False)
                findings = [Finding.model_validate(item) for item in analyst.get("findings", [])]
                if not findings:
                    raise AgentSupervisorError("Analyst returned no findings")
                run.findings = findings
                self._write_json(
                    run, "findings.json", [f.model_dump(mode="json") for f in findings]
                )

                await self._checkpoint(run, AgentRunState.PLANNING, "strategy", 30)
                planner_prompt = self._phase_prompt(
                    "planner",
                    run,
                    "Read findings.json and the repository. Return a JSON AgentPlan with "
                    "version=1, summary and actions. Every action must reference existing "
                    "finding_ids and include exact target_files and verification criteria.",
                )
                planner = await runner.run_phase(run, "planner", planner_prompt, writable=False)
                plan = AgentPlan.model_validate(planner)
                self._validate_plan(plan, findings, policy)
                run.plan = plan
                run.plan_hash = self._plan_hash(plan)
                self._write_json(run, "plan.json", plan.model_dump(mode="json"))
                await self._checkpoint(
                    run, AgentRunState.AWAITING_APPROVAL, "awaiting_approval", 40
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._fail(run_id, exc, recoverable=True)

    async def _execute(self, run_id: str) -> None:
        async with self._semaphore:
            try:
                run = await self._require_run(run_id)
                policy = load_project_policy(Path(run.worktree_path or ""))
                if (
                    not run.approved_at
                    or not run.plan
                    or self._plan_hash(run.plan) != run.plan_hash
                ):
                    raise AgentSupervisorError("Approved plan is missing or its hash has changed")
                runner = AgentCLIRunner(load_runtime_config(), self.repository)
                worktree = Path(run.worktree_path or "")
                if not worktree.is_dir():
                    raise AgentSupervisorError("Run worktree is missing")

                head = (await self._git_output(worktree, ["rev-parse", "HEAD"])).strip()
                dirty = (await self._git_output(worktree, ["status", "--porcelain"])).strip()
                if head != run.base_commit and not dirty:
                    await self._deliver(run, policy)
                    return

                await self._ensure_branch(run, policy)
                dirty = (await self._git_output(worktree, ["status", "--porcelain"])).strip()
                if not dirty:
                    await self._checkpoint(run, AgentRunState.IMPLEMENTING, "implementer", 50)
                    implement_prompt = self._phase_prompt(
                        "implementer",
                        run,
                        "Implement every approved action from plan.json in this worktree. Do not "
                        "change denied paths, do not run git write/network commands, and return "
                        "a JSON object with summary and finding_ids_implemented.",
                    )
                    implementation = await runner.run_phase(
                        run, "implementer", implement_prompt, writable=True
                    )
                    expected_findings = {
                        finding_id
                        for action in run.plan.actions
                        for finding_id in action.finding_ids
                    }
                    implemented_findings = set(implementation.get("finding_ids_implemented", []))
                    if not expected_findings.issubset(implemented_findings):
                        raise AgentSupervisorError(
                            "Implementer did not account for every approved finding"
                        )

                for cycle in range(policy.limits.max_repair_cycles + 1):
                    diff = await self._inspect_diff(run, policy)
                    run.diff_summary = diff
                    self._write_json(run, "diff-summary.json", diff)

                    await self._checkpoint(run, AgentRunState.VALIDATING, "validation", 65)
                    run.validations = await self._run_validations(run, policy)
                    if not all(item["success"] for item in run.validations):
                        raise AgentSupervisorError("Project validation command failed")

                    await self._checkpoint(run, AgentRunState.REAUDITING, "local_reaudit", 75)
                    run.audit_after = await self._preview_and_reaudit(run, policy)
                    self._write_json(run, "audit-after.json", run.audit_after)
                    self._verify_reaudit(run)

                    await self._checkpoint(run, AgentRunState.REVIEWING, "reviewer", 82)
                    review_prompt = self._phase_prompt(
                        "reviewer",
                        run,
                        "Review the actual git diff, validations.json, audit-before.json and "
                        "audit-after.json against plan.json. Return JSON with approved:boolean, "
                        "issues:array and verified_finding_ids:array.",
                    )
                    review = await runner.run_phase(
                        run, f"reviewer-{cycle}", review_prompt, writable=False
                    )
                    approved_findings = {
                        finding_id
                        for action in run.plan.actions
                        for finding_id in action.finding_ids
                    }
                    verified_findings = set(review.get("verified_finding_ids", []))
                    reviewer_approved = (
                        review.get("approved") is True
                        and not review.get("issues")
                        and approved_findings.issubset(verified_findings)
                    )
                    if reviewer_approved:
                        self._write_json(run, "review.json", review)
                        break
                    if cycle >= policy.limits.max_repair_cycles:
                        raise AgentSupervisorError("Reviewer rejected changes after repair limit")
                    self._write_json(run, f"review-{cycle}.json", review)
                    repair_prompt = self._phase_prompt(
                        "repair",
                        run,
                        f"Fix the issues listed in review-{cycle}.json without expanding the "
                        "approved plan. Return JSON with summary and fixed_issues.",
                    )
                    await runner.run_phase(run, f"repair-{cycle + 1}", repair_prompt, writable=True)

                # Validation, preview and reviewer are external processes. Check
                # their final filesystem state before staging anything.
                run.diff_summary = await self._inspect_diff(run, policy)
                self._write_json(run, "diff-summary.json", run.diff_summary)
                await self._commit(run, policy)
                await self._deliver(run, policy)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._fail(run_id, exc, recoverable=True)

    async def _commit(self, run: AgentRun, policy: ProjectPolicy) -> None:
        await self._checkpoint(run, AgentRunState.COMMITTING, "commit", 90)
        worktree = Path(run.worktree_path or "")
        files = run.diff_summary.get("files", [])
        if not files:
            raise AgentSupervisorError("Refusing commit without an inspected file list")
        await self._run_logged(run, "commit", ["git", "add", "--all", "--", *files], cwd=worktree)
        staged = set(
            filter(
                None,
                (await self._git_output(worktree, ["diff", "--cached", "--name-only", "-z"])).split(
                    "\0"
                ),
            )
        )
        if staged != set(files):
            raise AgentSupervisorError(
                f"Staged paths differ from inspected paths: {sorted(staged ^ set(files))}"
            )
        message = f"feat(seo): apply autonomous audit plan ({run.run_id[:8]})"
        await self._run_logged(
            run,
            "commit",
            ["git", "-c", "commit.gpgsign=false", "commit", "-m", message],
            cwd=worktree,
        )

    async def _deliver(self, run: AgentRun, policy: ProjectPolicy) -> None:
        worktree = Path(run.worktree_path or "")
        await self._checkpoint(run, AgentRunState.PUSHING, "push", 94)
        remote = (
            await self._git_output(Path(run.workspace_path), ["remote", "get-url", "origin"])
        ).strip()
        repo_slug, https_remote = self._github_remote(remote)
        await self._run_logged(
            run,
            "push",
            [
                "git",
                "-c",
                "credential.helper=!gh auth git-credential",
                "push",
                "--set-upstream",
                https_remote,
                run.branch_name or "",
            ],
            cwd=worktree,
        )

        await self._checkpoint(run, AgentRunState.OPENING_PR, "pull_request", 98)
        try:
            existing = await self._run_logged(
                run,
                "pull_request_lookup",
                [
                    "gh",
                    "pr",
                    "view",
                    run.branch_name or "",
                    "--repo",
                    repo_slug,
                    "--json",
                    "url",
                    "--jq",
                    ".url",
                ],
                cwd=worktree,
            )
        except AgentSupervisorError:
            existing = ""
        if existing.strip():
            run.pr_url = existing.strip().splitlines()[-1]
            await self._checkpoint(run, AgentRunState.COMPLETED, "completed", 100)
            return
        body_path = Path(run.artifact_path) / "pull-request.md"
        body_path.write_text(self._pr_body(run), encoding="utf-8")
        title = f"SEO agent: {run.plan.summary[:72] if run.plan else run.run_id[:8]}"
        stdout = await self._run_logged(
            run,
            "pull_request",
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repo_slug,
                "--base",
                policy.git.base_branch,
                "--head",
                run.branch_name or "",
                "--title",
                title,
                "--body-file",
                str(body_path),
            ],
            cwd=worktree,
        )
        run.pr_url = stdout.strip().splitlines()[-1]
        await self._checkpoint(run, AgentRunState.COMPLETED, "completed", 100)

    async def _run_validations(self, run: AgentRun, policy: ProjectPolicy) -> list[dict[str, Any]]:
        results = []
        for index, command in enumerate(policy.validation.commands):
            try:
                stdout = await self._run_project_logged(
                    run,
                    f"validation-{index + 1}",
                    command,
                    cwd=Path(run.worktree_path or ""),
                    timeout=policy.limits.max_minutes * 60,
                )
                results.append({"command": command, "success": True, "output": stdout[-2000:]})
            except Exception as exc:
                results.append({"command": command, "success": False, "error": str(exc)})
                break
        self._write_json(run, "validations.json", results)
        return results

    async def _preview_and_reaudit(self, run: AgentRun, policy: ProjectPolicy) -> dict[str, Any]:
        port = self._free_port()
        command = [part.replace("{port}", str(port)) for part in policy.preview.command]
        base_url = policy.preview.url_template.replace("{port}", str(port)).rstrip("/")
        self._validate_preview_base_url(base_url, port)
        log_path = Path(run.artifact_path) / "preview.log"
        sandboxed, env = self._sandbox_project_command(run, command, "preview")
        started = datetime.now(timezone.utc)
        process = None
        try:
            with log_path.open("wb") as log:
                process = await asyncio.create_subprocess_exec(
                    *sandboxed,
                    cwd=run.worktree_path,
                    env=env,
                    stdout=log,
                    stderr=asyncio.subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    await self._wait_ready(
                        urljoin(base_url + "/", policy.preview.readiness_path.lstrip("/")),
                        process,
                        policy.preview.timeout_seconds,
                    )
                    sitemap_url = urljoin(base_url + "/", policy.preview.sitemap_path.lstrip("/"))
                    with trusted_local_urls():
                        result = await self.ctx.full_audit.run(
                            sitemap_url,
                            max_pages=min(200, policy.limits.max_files * 4),
                            include_cwv=False,
                            language=policy.site.language,
                        )
                    if result.get("error"):
                        raise AgentSupervisorError(f"Local re-audit failed: {result['error']}")
                finally:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=10)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
        finally:
            preview_output = (
                log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            )
            await self.repository.add_command_log(
                run.run_id,
                "preview",
                sandboxed,
                process.returncode if process else None,
                preview_output,
                "",
                started,
                datetime.now(timezone.utc),
            )
        return result

    async def _inspect_diff(self, run: AgentRun, policy: ProjectPolicy) -> dict[str, Any]:
        worktree = Path(run.worktree_path or "")
        status = await self._git_output(
            worktree, ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
        files, untracked = self._parse_porcelain(status)
        if not files:
            raise AgentSupervisorError("Implementer produced no file changes")
        if len(files) > policy.limits.max_files:
            raise AgentSupervisorError(
                f"Diff changes {len(files)} files; limit is {policy.limits.max_files}"
            )
        for path in files:
            if any(fnmatch.fnmatch(path, pattern) for pattern in policy.workspace.deny):
                raise AgentSupervisorError(f"Denied path modified: {path}")
            if not any(fnmatch.fnmatch(path, pattern) for pattern in policy.workspace.allow):
                raise AgentSupervisorError(f"Path outside workspace allowlist: {path}")
            approved_targets = [
                target
                for action in (run.plan.actions if run.plan else [])
                for target in action.target_files
            ]
            if not any(
                path == target or fnmatch.fnmatch(path, target) for target in approved_targets
            ):
                raise AgentSupervisorError(f"Path was not part of the approved plan: {path}")
        diff = await self._git_output(worktree, ["diff", "HEAD", "--no-ext-diff", "--unified=3"])
        for path in untracked:
            target = worktree / path
            if target.is_file():
                diff += await self._untracked_diff(worktree, path)
        diff_lines = len(diff.splitlines())
        if diff_lines > policy.limits.max_diff_lines:
            raise AgentSupervisorError(
                f"Diff has {diff_lines} lines; limit is {policy.limits.max_diff_lines}"
            )
        (Path(run.artifact_path) / "changes.diff").write_text(diff, encoding="utf-8")
        return {"files": files, "file_count": len(files), "diff_lines": diff_lines}

    async def _ensure_branch(self, run: AgentRun, policy: ProjectPolicy) -> None:
        worktree = Path(run.worktree_path or "")
        current = (await self._git_output(worktree, ["branch", "--show-current"])).strip()
        if not run.branch_name:
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
            run.branch_name = f"{policy.git.branch_prefix}/{date}-{run.run_id[:8]}"
        if not current:
            await self._run_logged(
                run, "branch", ["git", "switch", "-c", run.branch_name], cwd=worktree
            )
        elif current != run.branch_name:
            raise AgentSupervisorError(f"Unexpected worktree branch: {current}")
        await self.repository.save(run)

    async def _wait_ready(
        self, url: str, process: asyncio.subprocess.Process, timeout_seconds: int
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        async with httpx.AsyncClient(timeout=2) as client:
            while asyncio.get_running_loop().time() < deadline:
                if process.returncode is not None:
                    raise AgentSupervisorError(f"Preview exited with code {process.returncode}")
                try:
                    response = await client.get(url)
                    if response.status_code < 500:
                        return
                except httpx.RequestError:
                    pass
                await asyncio.sleep(0.5)
        raise AgentSupervisorError(f"Preview readiness timed out: {url}")

    def _resolve_workspace(self, raw_path: str) -> Path:
        workspace = Path(raw_path).expanduser().resolve(strict=True)
        roots = allowed_workspace_roots()
        if not roots:
            raise AgentSupervisorError("SEO_AGENT_ALLOWED_ROOTS is empty")
        if not any(workspace == root or workspace.is_relative_to(root) for root in roots):
            raise AgentSupervisorError("Workspace is outside SEO_AGENT_ALLOWED_ROOTS")
        if not (workspace / ".git").exists():
            # Worktrees have a .git file; primary repos usually have a directory.
            raise AgentSupervisorError("workspace_path must be a Git checkout root")
        return workspace

    def _require_enabled(self) -> None:
        if not settings.SEO_AGENT_ENABLED:
            raise AgentSupervisorError("SEO agent is disabled (SEO_AGENT_ENABLED=false)")
        for command in ("git", "gh", "bwrap"):
            if not shutil.which(command):
                raise AgentSupervisorError(f"Required executable is missing: {command}")

    async def _require_run(self, run_id: str) -> AgentRun:
        run = await self.repository.get(run_id)
        if not run:
            raise AgentSupervisorError(f"Unknown agent run: {run_id}")
        return run

    async def _checkpoint(
        self, run: AgentRun, state: AgentRunState, phase: str, progress: int
    ) -> None:
        latest = await self.repository.get(run.run_id)
        if latest and latest.state == AgentRunState.CANCELLED:
            raise asyncio.CancelledError
        self._assert_transition(run.state, state)
        run.state = state
        run.phase = phase
        run.progress = progress
        run.error = None
        run.recoverable = False
        await self.repository.save(run)

    async def _fail(self, run_id: str, exc: Exception, *, recoverable: bool) -> None:
        run = await self.repository.get(run_id)
        if not run or run.state == AgentRunState.CANCELLED:
            return
        target = AgentRunState.RECOVERABLE if recoverable else AgentRunState.FAILED
        self._assert_transition(run.state, target)
        run.state = target
        run.error = str(exc)
        run.recoverable = recoverable
        await self.repository.save(run)

    def _schedule(self, run_id: str, coroutine, *, timeout_seconds: int) -> None:
        current = self._tasks.get(run_id)
        if current and not current.done():
            coroutine.close()
            raise AgentSupervisorError(f"Run already active: {run_id}")

        async def bounded_run():
            try:
                async with asyncio.timeout(timeout_seconds):
                    await coroutine
            except TimeoutError:
                await self._fail(
                    run_id,
                    AgentSupervisorError(
                        f"Run exceeded its active phase limit of {timeout_seconds} seconds"
                    ),
                    recoverable=True,
                )

        task = asyncio.create_task(bounded_run(), name=f"seo-agent-{run_id[:8]}")
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(run_id, None))

    @classmethod
    def _assert_transition(cls, current: AgentRunState, target: AgentRunState) -> None:
        if current == target:
            return
        if target == AgentRunState.CANCELLED and current not in TERMINAL_AGENT_STATES:
            return
        if target in {AgentRunState.RECOVERABLE, AgentRunState.FAILED} and current not in {
            *TERMINAL_AGENT_STATES,
            AgentRunState.AWAITING_APPROVAL,
        }:
            return
        if target not in cls._TRANSITIONS.get(current, set()):
            raise AgentSupervisorError(
                f"Invalid agent state transition: {current.value} -> {target.value}"
            )

    async def _run_logged(
        self,
        run: AgentRun,
        phase: str,
        argv: list[str],
        *,
        cwd: Path,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> str:
        started = datetime.now(timezone.utc)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
            await self.repository.add_command_log(
                run.run_id,
                phase,
                argv,
                None,
                stdout_b.decode(errors="replace"),
                stderr_b.decode(errors="replace"),
                started,
                datetime.now(timezone.utc),
            )
            raise AgentSupervisorError(f"Command timed out ({phase})") from exc
        except asyncio.CancelledError:
            proc.kill()
            await proc.wait()
            raise
        stdout = stdout_b.decode(errors="replace")
        stderr = stderr_b.decode(errors="replace")
        await self.repository.add_command_log(
            run.run_id,
            phase,
            argv,
            proc.returncode,
            stdout,
            stderr,
            started,
            datetime.now(timezone.utc),
        )
        if proc.returncode != 0:
            raise AgentSupervisorError(f"Command failed ({phase}): {stderr[-1500:]}")
        return stdout

    async def _run_project_logged(
        self,
        run: AgentRun,
        phase: str,
        argv: list[str],
        *,
        cwd: Path,
        timeout: int,
    ) -> str:
        sandboxed, env = self._sandbox_project_command(run, argv, phase)
        return await self._run_logged(run, phase, sandboxed, cwd=cwd, timeout=timeout, env=env)

    def _sandbox_project_command(
        self, run: AgentRun, argv: list[str], phase: str
    ) -> tuple[list[str], dict[str, str]]:
        runtime = load_runtime_config()
        workspace = Path(run.worktree_path or "").resolve()
        artifact_dir = Path(run.artifact_path).resolve() / f"project-{phase}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        resolved_argv = list(argv)
        executable = shutil.which(resolved_argv[0])
        if not executable:
            raise AgentSupervisorError(f"Project command is missing: {resolved_argv[0]}")
        resolved_argv[0] = executable
        sandboxed = AgentCLIRunner(runtime, self.repository)._sandbox_argv(
            resolved_argv,
            workspace,
            artifact_dir,
            writable=True,
            network=not phase.startswith("validation-"),
        )
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        # Project-owned commands never receive external-agent credentials.
        home = artifact_dir / "home"
        home.mkdir(exist_ok=True)
        env["HOME"] = str(home)
        env["TMPDIR"] = "/tmp"
        return sandboxed, env

    async def _run_raw(self, cwd: Path, argv: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise AgentSupervisorError(stderr.decode(errors="replace")[-1500:])
        return stdout.decode(errors="replace")

    async def _git_output(self, cwd: Path, args: list[str]) -> str:
        return await self._run_raw(cwd, ["git", *args])

    async def _untracked_diff(self, cwd: Path, path: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            "--no-index",
            "--no-ext-diff",
            "--unified=3",
            "--",
            "/dev/null",
            path,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode not in {0, 1}:
            raise AgentSupervisorError(stderr.decode(errors="replace")[-1500:])
        return stdout.decode(errors="replace")

    @staticmethod
    def _parse_porcelain(status: str) -> tuple[list[str], set[str]]:
        entries = status.split("\0")
        files: list[str] = []
        untracked: set[str] = set()
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            code = entry[:2]
            path = entry[3:]
            if path:
                files.append(path)
                if code == "??":
                    untracked.add(path)
            if "R" in code or "C" in code:
                if index < len(entries) and entries[index]:
                    files.append(entries[index])
                index += 1
        return sorted(set(files)), untracked

    @staticmethod
    def _validate_preview_base_url(base_url: str, port: int) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port != port
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AgentSupervisorError(
                "preview.url_template must resolve to http://127.0.0.1:{port} "
                "or http://[::1]:{port}"
            )

    def _write_json(self, run: AgentRun, name: str, value: Any) -> Path:
        path = Path(run.artifact_path) / name
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
        return path

    def _phase_prompt(self, phase: str, run: AgentRun, instruction: str) -> str:
        return (
            f"You are the {phase} phase of autonomous SEO run {run.run_id}.\n"
            f"Workspace: {run.worktree_path}\nArtifacts: {run.artifact_path}\n\n"
            f"{instruction}\n\nReturn only the requested JSON object, without Markdown fences."
        )

    @staticmethod
    def _plan_hash(plan: AgentPlan) -> str:
        canonical = json.dumps(plan.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _validate_plan(plan: AgentPlan, findings: list[Finding], policy: ProjectPolicy) -> None:
        known = {finding.finding_id for finding in findings}
        for action in plan.actions:
            unknown = set(action.finding_ids) - known
            if unknown:
                raise AgentSupervisorError(f"Plan references unknown findings: {sorted(unknown)}")
            if not action.target_files:
                raise AgentSupervisorError(f"Action has no target files: {action.action_id}")
            for target in action.target_files:
                candidate = Path(target)
                if candidate.is_absolute() or ".." in candidate.parts:
                    raise AgentSupervisorError(f"Unsafe plan target: {target}")
                if any(fnmatch.fnmatch(target, pattern) for pattern in policy.workspace.deny):
                    raise AgentSupervisorError(f"Plan targets denied path: {target}")
                if not any(fnmatch.fnmatch(target, pattern) for pattern in policy.workspace.allow):
                    raise AgentSupervisorError(f"Plan target is outside allowlist: {target}")
        if not plan.actions:
            raise AgentSupervisorError("Planner returned no actions")

    def _verify_reaudit(self, run: AgentRun) -> None:
        before = (run.audit_before or {}).get("overall_score")
        after = (run.audit_after or {}).get("overall_score")
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            raise AgentSupervisorError("Re-audit did not return comparable overall scores")
        comparison = {"before": before, "after": after, "delta": after - before}
        self._write_json(run, "audit-comparison.json", comparison)
        if after < before:
            raise AgentSupervisorError("Local re-audit regressed the overall SEO score")

    @staticmethod
    def _github_remote(remote: str) -> tuple[str, str]:
        patterns = (
            r"^git@github\.com:(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
            r"^https://github\.com/(?P<slug>[^/]+/[^/]+?)(?:\.git)?$",
        )
        for pattern in patterns:
            match = re.match(pattern, remote)
            if match:
                slug = match.group("slug")
                return slug, f"https://github.com/{slug}.git"
        raise AgentSupervisorError("origin must be a GitHub SSH or HTTPS remote")

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _pr_body(run: AgentRun) -> str:
        findings = "\n".join(
            f"- `{finding.finding_id}` [{finding.severity}] {finding.claim}"
            for finding in run.findings
        )
        validations = "\n".join(
            f"- {'PASS' if item.get('success') else 'FAIL'}: `{' '.join(item.get('command', []))}`"
            for item in run.validations
        )
        before = (run.audit_before or {}).get("overall_score", "n/a")
        after = (run.audit_after or {}).get("overall_score", "n/a")
        changes = "\n".join(
            f"- `{action.action_id}` -> {', '.join(f'`{path}`' for path in action.target_files)} "
            f"(findings: {', '.join(f'`{finding_id}`' for finding_id in action.finding_ids)})"
            for action in (run.plan.actions if run.plan else [])
        )
        missing = (
            "\n".join(
                f"- `{finding.finding_id}`: {', '.join(finding.missing_data) or finding.claim}"
                for finding in run.findings
                if finding.status == "missing" or finding.missing_data
            )
            or "- None reported"
        )
        diff = run.diff_summary
        return (
            f"## Autonomous SEO run\n\nRun: `{run.run_id}`\n\n"
            f"### Plan\n\n{run.plan.summary if run.plan else ''}\n\n"
            f"### Evidence\n\n{findings}\n\n"
            f"### Changes\n\n{changes}\n\n"
            f"### Validation\n\n{validations}\n\n"
            f"### Re-audit\n\nOverall score: **{before} -> {after}**\n\n"
            f"### Limits and actual diff\n\nFiles: **{diff.get('file_count', 0)}**; "
            f"diff lines: **{diff.get('diff_lines', 0)}**.\n\n"
            f"### Missing data\n\n{missing}\n\n"
            "This pull request was generated after explicit plan approval and was not merged automatically.\n"
        )
