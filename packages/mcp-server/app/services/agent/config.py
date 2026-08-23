"""Project and operator configuration for autonomous SEO runs."""

import os
import shlex
import shutil
import tomllib
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings

PROJECT_POLICY_FILE = ".seo-agent.toml"


class SitePolicy(BaseModel):
    base_url: str
    sitemap_url: str
    gsc_property: str | None = None
    language: str = "en"


class WorkspacePolicy(BaseModel):
    allow: list[str]
    deny: list[str] = Field(
        default_factory=lambda: [
            ".env*",
            "**/.env*",
            "**/credentials/**",
            "**/*secret*",
            ".seo-agent.toml",
            ".git/**",
        ]
    )

    @field_validator("allow")
    @classmethod
    def require_allowlist(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("workspace.allow must contain at least one glob")
        return value


class ValidationPolicy(BaseModel):
    commands: list[list[str]]

    @field_validator("commands")
    @classmethod
    def validate_commands(cls, commands: list[list[str]]) -> list[list[str]]:
        if not commands or any(
            not command or any(not part for part in command) for command in commands
        ):
            raise ValueError("validation.commands must contain non-empty argv arrays")
        forbidden = {"npm", "npx", "sh", "bash", "dash", "zsh", "fish", "pwsh", "powershell", "cmd"}
        for command in commands:
            if Path(command[0]).name in forbidden:
                raise ValueError("validation commands must use direct argv and bun/bunx")
        return commands


class PreviewPolicy(BaseModel):
    command: list[str]
    url_template: str = "http://127.0.0.1:{port}"
    readiness_path: str = "/"
    sitemap_path: str = "/sitemap.xml"
    timeout_seconds: int = Field(default=120, ge=10, le=600)

    @model_validator(mode="after")
    def require_port_placeholder(self):
        if not self.command:
            raise ValueError("preview.command must be a non-empty argv array")
        if Path(self.command[0]).name in {
            "npm",
            "npx",
            "sh",
            "bash",
            "dash",
            "zsh",
            "fish",
            "pwsh",
            "powershell",
            "cmd",
        }:
            raise ValueError("preview command must use direct argv and bun/bunx")
        if "{port}" not in self.url_template and not any("{port}" in p for p in self.command):
            raise ValueError("preview must expose a {port} placeholder")
        return self


class GitPolicy(BaseModel):
    base_branch: str = "main"
    branch_prefix: str = "seo-agent"


class LimitsPolicy(BaseModel):
    max_files: int = Field(default=50, ge=1, le=200)
    max_diff_lines: int = Field(default=5000, ge=1, le=20000)
    max_minutes: int = Field(default=60, ge=5, le=180)
    max_repair_cycles: int = Field(default=2, ge=0, le=2)


class ProjectPolicy(BaseModel):
    version: Literal[1]
    site: SitePolicy
    workspace: WorkspacePolicy
    validation: ValidationPolicy
    preview: PreviewPolicy
    git: GitPolicy = Field(default_factory=GitPolicy)
    limits: LimitsPolicy = Field(default_factory=LimitsPolicy)


class AgentRuntimeConfig(BaseModel):
    version: Literal[1]
    provider: Literal["custom", "codex", "claude", "grok"] = "custom"
    argv: list[str] = Field(default_factory=list)
    model: str = ""
    prompt_mode: Literal["argument", "stdin", "file"] = "argument"
    result_mode: Literal["stdout_json", "file"] = "stdout_json"
    timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    env_allowlist: list[str] = Field(default_factory=list)
    runtime_read_paths: list[str] = Field(default_factory=list)
    sandbox: bool = True

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, argv: list[str]) -> list[str]:
        if any(";" in part or "\n" in part for part in argv):
            raise ValueError("agent argv must not contain shell separators")
        return argv

    @model_validator(mode="after")
    def require_custom_argv(self):
        if self.provider == "custom" and not self.argv:
            raise ValueError("custom agent argv cannot be empty")
        return self


def load_project_policy(workspace: Path) -> ProjectPolicy:
    path = workspace / PROJECT_POLICY_FILE
    if not path.is_file():
        raise ValueError(f"Missing required project policy: {path}")
    with path.open("rb") as handle:
        policy = ProjectPolicy.model_validate(tomllib.load(handle))
    policy.limits.max_files = min(policy.limits.max_files, settings.SEO_AGENT_MAX_FILES)
    policy.limits.max_diff_lines = min(
        policy.limits.max_diff_lines, settings.SEO_AGENT_MAX_DIFF_LINES
    )
    policy.limits.max_minutes = min(policy.limits.max_minutes, settings.SEO_AGENT_MAX_RUN_MINUTES)
    policy.limits.max_repair_cycles = min(
        policy.limits.max_repair_cycles, settings.SEO_AGENT_MAX_REPAIR_CYCLES
    )
    return policy


def load_runtime_config() -> AgentRuntimeConfig:
    raw_path = settings.SEO_AGENT_RUNTIME_CONFIG.strip()
    if raw_path:
        path = Path(raw_path).expanduser().resolve()
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        # Accept either top-level fields or an [agent] table.
        config = AgentRuntimeConfig.model_validate(data.get("agent", data))
    else:
        config = detect_runtime_config()
    config.timeout_seconds = min(config.timeout_seconds, settings.SEO_AGENT_MAX_CLI_SECONDS)
    return config


def detect_runtime_config() -> AgentRuntimeConfig:
    """Select the first installed non-interactive agent CLI.

    The default order is Codex, Claude, then Grok. Operators can select one
    provider explicitly or change the order without writing a runtime TOML.
    """
    requested = settings.SEO_AGENT_PROVIDER.strip().lower() or "auto"
    known = {"codex", "claude", "grok"}
    if requested != "auto" and requested not in known:
        raise ValueError("SEO_AGENT_PROVIDER must be auto, codex, claude, or grok")
    order = [
        value.strip().lower()
        for value in settings.SEO_AGENT_PROVIDER_ORDER.split(",")
        if value.strip()
    ]
    if any(value not in known for value in order):
        raise ValueError("SEO_AGENT_PROVIDER_ORDER contains an unknown provider")
    candidates = [requested] if requested != "auto" else order
    for provider in candidates:
        executable = shutil.which(provider)
        if executable:
            return AgentRuntimeConfig(
                version=1,
                provider=cast(Literal["codex", "claude", "grok"], provider),
                argv=[executable],
                model=settings.SEO_AGENT_MODEL.strip(),
                sandbox=False,
            )
    names = ", ".join(candidates) or "codex, claude, grok"
    raise ValueError(f"No non-interactive agent CLI found ({names})")


def allowed_workspace_roots() -> list[Path]:
    values = [value for value in settings.SEO_AGENT_ALLOWED_ROOTS.split(os.pathsep) if value]
    return [Path(value).expanduser().resolve() for value in values]


def allowed_skill_roots() -> list[Path]:
    values = [value for value in settings.SEO_AGENT_SKILL_ROOTS.split(os.pathsep) if value]
    return [Path(value).expanduser().resolve() for value in values]


def describe_command(argv: list[str]) -> str:
    return shlex.join(argv)
