"""Contracts for durable autonomous SEO agent runs."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentRunState(str, Enum):
    QUEUED = "queued"
    AUDITING = "auditing"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    IMPLEMENTING = "implementing"
    VALIDATING = "validating"
    REAUDITING = "reauditing"
    REVIEWING = "reviewing"
    COMMITTING = "committing"
    PUSHING = "pushing"
    OPENING_PR = "opening_pr"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERABLE = "recoverable"
    CANCELLED = "cancelled"


TERMINAL_AGENT_STATES = {
    AgentRunState.COMPLETED,
    AgentRunState.FAILED,
    AgentRunState.CANCELLED,
}


class Evidence(BaseModel):
    source: str
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    url: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    finding_id: str
    claim: str
    status: Literal["observed", "provided", "inferred", "missing", "blocked"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    affected_urls: list[str] = Field(default_factory=list)
    affected_files: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    recommendation: str
    verification: str


class AgentAction(BaseModel):
    action_id: str
    finding_ids: list[str]
    title: str
    change_type: str
    target_files: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"]
    rationale: str
    expected_result: str
    verification: list[str] = Field(default_factory=list)


class AgentPlan(BaseModel):
    version: int = 1
    summary: str
    actions: list[AgentAction]


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid4().hex)
    workspace_path: str
    worktree_path: str | None = None
    artifact_path: str
    base_commit: str
    base_branch: str
    branch_name: str | None = None
    state: AgentRunState = AgentRunState.QUEUED
    phase: str = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    plan_hash: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    plan: AgentPlan | None = None
    validations: list[dict[str, Any]] = Field(default_factory=list)
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    audit_before: dict[str, Any] | None = None
    audit_after: dict[str, Any] | None = None
    error: str | None = None
    recoverable: bool = False
    pr_url: str | None = None
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
