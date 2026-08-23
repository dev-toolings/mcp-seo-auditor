"""Generate and reconcile managed Codex skills from a versioned manifest."""

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Literal
from uuid import uuid4

from app.core.config import settings
from app.models.agent_run import AgentRun
from app.models.skill_manifest import (
    ManagedSkill,
    SkillManifest,
    SkillOperation,
    SkillReconciliationPlan,
)
from app.services.agent.cli_runner import AgentCLIRunner
from app.services.agent.config import (
    allowed_skill_roots,
    allowed_workspace_roots,
    load_runtime_config,
)

_MARKER = ".mcp-seo-auditor-managed.json"


class SkillLifecycleError(RuntimeError):
    pass


class SkillLifecycleService:
    """Plan and apply create/update/delete operations for managed skills."""

    async def generate_manifest(
        self,
        objective: str,
        workspace_path: str,
        *,
        prune: bool,
        model: str = "",
    ) -> tuple[SkillManifest, dict[str, str]]:
        self._require_enabled()
        workspace = self._resolve_workspace(workspace_path)
        runtime = load_runtime_config()
        if model.strip():
            runtime = runtime.model_copy(update={"model": model.strip()})
        artifact_root = Path(settings.SEO_AGENT_ARTIFACT_ROOT).expanduser().resolve()
        artifact_path = artifact_root / "skill-plans" / uuid4().hex
        artifact_path.mkdir(parents=True, exist_ok=False)
        run = AgentRun(
            workspace_path=str(workspace),
            worktree_path=str(workspace),
            artifact_path=str(artifact_path),
            base_commit="skill-manifest",
            base_branch="skill-manifest",
        )
        schema = json.dumps(SkillManifest.model_json_schema(), ensure_ascii=False)
        prompt = (
            "Design the smallest useful set of Codex skills for the objective below. "
            "Return only one JSON object matching the provided schema. Skills must contain "
            "non-obvious, task-specific guidance; do not repeat generic coding advice. "
            "Names use lowercase letters, digits and hyphens. Put conditional detail in "
            "references/ files. Never include credentials or absolute paths.\n\n"
            f"Objective:\n{objective.strip()}\n\n"
            f"Set prune to {str(prune).lower()}.\n\nJSON Schema:\n{schema}"
        )
        raw = await AgentCLIRunner(runtime).run_phase(run, "skill-manifest", prompt, writable=False)
        manifest = SkillManifest.model_validate(raw)
        manifest.prune = prune
        return manifest, {"provider": runtime.provider, "model": runtime.model}

    def plan(self, manifest: SkillManifest, skill_root: str = "") -> SkillReconciliationPlan:
        root = self._resolve_skill_root(skill_root, create=False)
        operations: list[SkillOperation] = []
        desired = {skill.name: skill for skill in manifest.skills}
        for name, skill in desired.items():
            target = self._safe_target(root, name)
            action: Literal["create", "update", "delete", "unchanged"]
            if not target.exists():
                action, reason = "create", "skill does not exist"
            else:
                self._require_managed_directory(target)
                current_digest = self._tree_digest(target)
                desired_digest = self._desired_digest(skill)
                if current_digest == desired_digest:
                    action, reason = "unchanged", "managed contents already match"
                else:
                    action, reason = "update", "managed contents differ from manifest"
            operations.append(SkillOperation(action=action, name=name, reason=reason))

        if manifest.prune and root.exists():
            for child in sorted(root.iterdir(), key=lambda path: path.name):
                if (
                    child.is_dir()
                    and not child.is_symlink()
                    and child.name not in desired
                    and (child / _MARKER).is_file()
                ):
                    operations.append(
                        SkillOperation(
                            action="delete",
                            name=child.name,
                            reason="managed skill is absent from a pruning manifest",
                        )
                    )
        operations.sort(key=lambda item: (item.name, item.action))
        plan_hash = self._plan_hash(root, manifest, operations)
        return SkillReconciliationPlan(
            root=str(root),
            manifest=manifest,
            operations=operations,
            plan_hash=plan_hash,
        )

    def apply(
        self, manifest: SkillManifest, plan_hash: str, skill_root: str = ""
    ) -> SkillReconciliationPlan:
        self._require_enabled()
        root = self._resolve_skill_root(skill_root, create=True)
        plan = self.plan(manifest, str(root))
        if not plan_hash or plan.plan_hash != plan_hash:
            raise SkillLifecycleError("skill plan hash changed; generate and approve a new plan")
        desired = {skill.name: skill for skill in manifest.skills}
        for operation in plan.operations:
            target = self._safe_target(root, operation.name)
            if operation.action == "unchanged":
                continue
            if operation.action == "delete":
                self._require_managed_directory(target)
                shutil.rmtree(target)
                continue
            self._replace_skill(root, target, desired[operation.name])
        return self.plan(manifest, str(root))

    def runtime_status(self) -> dict[str, object]:
        try:
            runtime = load_runtime_config()
        except Exception as exc:
            return {"available": False, "error": str(exc)}
        return {
            "available": True,
            "provider": runtime.provider,
            "model": runtime.model or None,
            "executable": runtime.argv[0],
            "custom_config": bool(settings.SEO_AGENT_RUNTIME_CONFIG.strip()),
        }

    @staticmethod
    def _require_enabled() -> None:
        if not settings.SEO_AGENT_ENABLED:
            raise SkillLifecycleError("SEO agent is disabled (SEO_AGENT_ENABLED=false)")

    @staticmethod
    def _resolve_workspace(raw_path: str) -> Path:
        workspace = Path(raw_path).expanduser().resolve(strict=True)
        if not workspace.is_dir():
            raise SkillLifecycleError("workspace_path must be a directory")
        roots = allowed_workspace_roots()
        if not roots or not any(
            workspace == root or workspace.is_relative_to(root) for root in roots
        ):
            raise SkillLifecycleError("workspace_path is outside SEO_AGENT_ALLOWED_ROOTS")
        return workspace

    def _resolve_skill_root(self, raw_path: str, *, create: bool) -> Path:
        roots = allowed_skill_roots()
        if not roots:
            raise SkillLifecycleError("SEO_AGENT_SKILL_ROOTS is empty")
        requested = Path(raw_path).expanduser() if raw_path else roots[0]
        resolved = requested.resolve(strict=False)
        if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
            raise SkillLifecycleError("skill_root is outside SEO_AGENT_SKILL_ROOTS")
        if resolved.exists() and (not resolved.is_dir() or resolved.is_symlink()):
            raise SkillLifecycleError("skill_root must be a real directory")
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    @staticmethod
    def _safe_target(root: Path, name: str) -> Path:
        target = root / name
        if target.resolve(strict=False).parent != root.resolve(strict=False):
            raise SkillLifecycleError(f"unsafe skill target: {name}")
        if target.is_symlink():
            raise SkillLifecycleError(f"refusing symlinked skill target: {name}")
        return target

    @staticmethod
    def _require_managed_directory(target: Path) -> None:
        if not target.is_dir() or target.is_symlink() or not (target / _MARKER).is_file():
            raise SkillLifecycleError(f"refusing to replace unmanaged skill: {target.name}")

    def _replace_skill(self, root: Path, target: Path, skill: ManagedSkill) -> None:
        staging = root / f".mcp-seo-auditor-staging-{uuid4().hex}"
        backup = root / f".mcp-seo-auditor-backup-{uuid4().hex}"
        try:
            self._write_skill(staging, skill)
            if target.exists():
                self._require_managed_directory(target)
                os.replace(target, backup)
            os.replace(staging, target)
            if backup.exists():
                shutil.rmtree(backup)
        except Exception:
            if not target.exists() and backup.exists():
                os.replace(backup, target)
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def _write_skill(self, directory: Path, skill: ManagedSkill) -> None:
        directory.mkdir(parents=False, exist_ok=False)
        files = self._desired_files(skill)
        for relative, content in files.items():
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        marker = {
            "version": 1,
            "managed_by": "mcp-seo-auditor",
            "name": skill.name,
            "digest": self._desired_digest(skill),
        }
        (directory / _MARKER).write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _desired_files(skill: ManagedSkill) -> dict[str, str]:
        skill_md = (
            "---\n"
            f"name: {json.dumps(skill.name)}\n"
            f"description: {json.dumps(skill.description)}\n"
            "metadata:\n"
            '  managed-by: "mcp-seo-auditor"\n'
            "---\n\n"
            f"{skill.instructions.rstrip()}\n"
        )
        return {"SKILL.md": skill_md, **skill.files}

    def _desired_digest(self, skill: ManagedSkill) -> str:
        return self._files_digest(self._desired_files(skill))

    def _tree_digest(self, directory: Path) -> str:
        files: dict[str, str] = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise SkillLifecycleError(f"managed skill contains a symlink: {directory.name}")
            if path.is_file() and path.name != _MARKER:
                files[path.relative_to(directory).as_posix()] = path.read_text(encoding="utf-8")
        return self._files_digest(files)

    @staticmethod
    def _files_digest(files: dict[str, str]) -> str:
        payload = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _plan_hash(root: Path, manifest: SkillManifest, operations: list[SkillOperation]) -> str:
        payload = {
            "root": str(root),
            "manifest": manifest.model_dump(mode="json"),
            "operations": [operation.model_dump(mode="json") for operation in operations],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
