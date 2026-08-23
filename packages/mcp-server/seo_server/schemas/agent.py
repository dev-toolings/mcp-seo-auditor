"""Input/output contracts for the autonomous seo_agent tool."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.skill_manifest import SkillManifest
from seo_server.schemas.validators import MCPInput


class SeoAgentInput(MCPInput):
    action: Literal[
        "start",
        "status",
        "approve",
        "reject",
        "resume",
        "cancel",
        "cleanup",
        "runtime",
        "skills_plan",
        "skills_apply",
    ]
    workspace_path: str | None = None
    run_id: str | None = None
    plan_hash: str | None = None
    reason: str | None = None
    objective: str | None = Field(default=None, max_length=20_000)
    skill_root: str | None = None
    manifest: SkillManifest | None = None
    prune: bool = False
    model: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def validate_action_fields(self):
        run_actions = {"status", "approve", "reject", "resume", "cancel", "cleanup"}
        if self.action == "start" and not self.workspace_path:
            raise ValueError("workspace_path is required for start")
        if self.action in run_actions and not self.run_id:
            raise ValueError(f"run_id is required for {self.action}")
        if self.action == "approve" and not self.plan_hash:
            raise ValueError("plan_hash is required for approve")
        if self.action == "reject" and not self.reason:
            raise ValueError("reason is required for reject")
        if self.action == "skills_plan" and not self.manifest:
            if not self.objective or not self.workspace_path:
                raise ValueError(
                    "skills_plan requires manifest or both objective and workspace_path"
                )
        if self.action == "skills_apply" and (not self.manifest or not self.plan_hash):
            raise ValueError("skills_apply requires manifest and plan_hash")
        return self


class SeoAgentOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    state: str
    phase: str
    progress: int = Field(ge=0, le=100)
    plan_hash: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    validations: list[dict[str, Any]] = Field(default_factory=list)
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    recoverable: bool = False
    pr_url: str | None = None
