"""Declarative contract for managed Codex skills."""

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_RESOURCE_ROOTS = {"agents", "assets", "references", "scripts"}


class ManagedSkill(BaseModel):
    """Desired contents of one managed skill directory."""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=12, max_length=500)
    instructions: str = Field(min_length=1, max_length=100_000)
    files: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _SKILL_NAME_RE.fullmatch(value):
            raise ValueError("skill name must use lowercase letters, digits, and hyphens")
        return value

    @field_validator("files")
    @classmethod
    def validate_files(cls, value: dict[str, str]) -> dict[str, str]:
        for raw_path, content in value.items():
            path = PurePosixPath(raw_path)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] not in _ALLOWED_RESOURCE_ROOTS
            ):
                raise ValueError(f"unsafe skill resource path: {raw_path}")
            if raw_path in {"SKILL.md", ".mcp-seo-auditor-managed.json"}:
                raise ValueError(f"reserved skill resource path: {raw_path}")
            if "\x00" in content:
                raise ValueError(f"skill resource contains a NUL byte: {raw_path}")
        return value


class SkillManifest(BaseModel):
    """Complete desired state for managed skills under one authorized root."""

    version: Literal[1] = 1
    skills: list[ManagedSkill]
    prune: bool = False

    @model_validator(mode="after")
    def unique_names(self):
        names = [skill.name for skill in self.skills]
        if len(names) != len(set(names)):
            raise ValueError("skill names must be unique")
        return self


class SkillOperation(BaseModel):
    action: Literal["create", "update", "delete", "unchanged"]
    name: str
    reason: str


class SkillReconciliationPlan(BaseModel):
    version: Literal[1] = 1
    root: str
    manifest: SkillManifest
    operations: list[SkillOperation]
    plan_hash: str
