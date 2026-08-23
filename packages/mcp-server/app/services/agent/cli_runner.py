"""Sandboxed external CLI runner used by autonomous SEO phases."""

import asyncio
import json
import os
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.agent_run import AgentRun
from app.repositories.agent_run_repository import AgentRunRepository
from app.services.agent.config import AgentRuntimeConfig


class AgentCLIError(RuntimeError):
    pass


class AgentCLIRunner:
    def __init__(self, config: AgentRuntimeConfig, repository: AgentRunRepository | None = None):
        self.config = config
        self.repository = repository

    async def run_phase(
        self,
        run: AgentRun,
        phase: str,
        prompt: str,
        *,
        writable: bool,
    ) -> dict[str, Any]:
        workspace = Path(run.worktree_path or "").resolve()
        artifact_dir = Path(run.artifact_path).resolve() / phase
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = artifact_dir / "prompt.md"
        result_file = artifact_dir / "result.json"
        prompt_file.write_text(prompt, encoding="utf-8")

        argv = self._render_argv(prompt, prompt_file, result_file, workspace, writable=writable)
        if self.config.sandbox:
            argv = self._sandbox_argv(argv, workspace, artifact_dir, writable=writable)

        env = self._runtime_env(artifact_dir)

        started = datetime.now(timezone.utc)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=workspace,
                env=env,
                stdin=asyncio.subprocess.PIPE if self.config.prompt_mode == "stdin" else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdin = prompt.encode() if self.config.prompt_mode == "stdin" else None
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(stdin), timeout=self.config.timeout_seconds
            )
        except TimeoutError as exc:
            if "proc" in locals():
                proc.kill()
                await proc.wait()
            raise AgentCLIError(f"Agent phase {phase} timed out") from exc
        except asyncio.CancelledError:
            if "proc" in locals():
                proc.kill()
                await proc.wait()
            raise

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        finished = datetime.now(timezone.utc)
        if self.repository is not None:
            await self.repository.add_command_log(
                run.run_id, phase, argv, proc.returncode, stdout, stderr, started, finished
            )
        if proc.returncode != 0:
            raise AgentCLIError(f"Agent phase {phase} exited {proc.returncode}: {stderr[-1000:]}")

        raw = (
            result_file.read_text(encoding="utf-8") if self.config.result_mode == "file" else stdout
        )
        try:
            result = self._decode_result(raw)
        except json.JSONDecodeError as exc:
            raise AgentCLIError(f"Agent phase {phase} returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise AgentCLIError(f"Agent phase {phase} must return a JSON object")
        return result

    def _render_argv(
        self,
        prompt: str,
        prompt_file: Path,
        result_file: Path,
        workspace: Path,
        *,
        writable: bool,
    ) -> list[str]:
        if self.config.provider != "custom":
            return self._provider_argv(prompt, workspace, writable=writable)
        replacements = {
            "{prompt}": prompt,
            "{prompt_file}": str(prompt_file),
            "{result_file}": str(result_file),
            "{workspace}": str(workspace),
        }
        rendered = []
        for value in self.config.argv:
            for marker, replacement in replacements.items():
                value = value.replace(marker, replacement)
            rendered.append(value)
        executable = shutil.which(rendered[0])
        if executable:
            rendered[0] = str(Path(executable).absolute())
        if self.config.prompt_mode == "argument" and not any(
            "{prompt}" in value for value in self.config.argv
        ):
            rendered.append(prompt)
        if self.config.prompt_mode == "file" and not any(
            "{prompt_file}" in value for value in self.config.argv
        ):
            rendered.append(str(prompt_file))
        return rendered

    def _provider_argv(self, prompt: str, workspace: Path, *, writable: bool) -> list[str]:
        executable = self.config.argv[0]
        model = self.config.model.strip()
        if self.config.provider == "codex":
            argv = [
                executable,
                "exec",
                "--ephemeral",
                "--sandbox",
                "workspace-write" if writable else "read-only",
                "--skip-git-repo-check",
                "--color",
                "never",
                "--cd",
                str(workspace),
            ]
            if model:
                argv.extend(["--model", model])
            return [*argv, prompt]
        if self.config.provider == "claude":
            argv = [
                executable,
                "-p",
                "--no-session-persistence",
                "--output-format",
                "text",
                "--permission-mode",
                "acceptEdits" if writable else "plan",
                "--tools",
                "Read,Glob,Grep,Edit,Write" if writable else "Read,Glob,Grep",
            ]
            if model:
                argv.extend(["--model", model])
            return [*argv, prompt]
        if self.config.provider == "grok":
            argv = [
                executable,
                "--cwd",
                str(workspace),
                "--permission-mode",
                "acceptEdits" if writable else "plan",
                "--disable-web-search",
                "--no-subagents",
                "--output-format",
                "plain",
            ]
            if model:
                argv.extend(["--model", model])
            return [*argv, "-p", prompt]
        raise AgentCLIError(f"Unsupported agent provider: {self.config.provider}")

    def _runtime_env(self, artifact_dir: Path) -> dict[str, str]:
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        for key in self.config.env_allowlist:
            if key in os.environ:
                env[key] = os.environ[key]
        if self.config.provider == "custom":
            isolated_home = artifact_dir / "home"
            isolated_home.mkdir(exist_ok=True)
            env["HOME"] = str(isolated_home)
            return env

        # Built-in CLIs need their existing login state. Keep only identity,
        # configuration and provider authentication variables, not the complete
        # server environment.
        for key in (
            "HOME",
            "USER",
            "LOGNAME",
            "XDG_CONFIG_HOME",
            "CODEX_HOME",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "XAI_API_KEY",
        ):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    @staticmethod
    def _decode_result(raw: str) -> dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            first_newline = cleaned.find("\n")
            cleaned = cleaned[first_newline + 1 : -3].strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError as original:
            decoder = json.JSONDecoder()
            for index, char in enumerate(cleaned):
                if char != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(cleaned[index:])
                    break
                except json.JSONDecodeError:
                    continue
            else:
                raise original
        if not isinstance(value, dict):
            raise json.JSONDecodeError("Agent response is not a JSON object", cleaned, 0)
        return value

    def _sandbox_argv(
        self,
        argv: list[str],
        workspace: Path,
        artifact_dir: Path,
        *,
        writable: bool,
        network: bool = True,
    ) -> list[str]:
        bwrap = shutil.which("bwrap")
        if not bwrap:
            raise AgentCLIError("Bubblewrap is required for autonomous agent execution")

        sandbox = [bwrap, "--die-with-parent", "--new-session", "--proc", "/proc", "--dev", "/dev"]
        if not network:
            sandbox.append("--unshare-net")
        for system_path in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
            if Path(system_path).exists():
                sandbox.extend(["--ro-bind", system_path, system_path])
        sandbox.extend(["--tmpfs", "/tmp"])

        runtime_paths = set(self.config.runtime_read_paths)
        executable_path = Path(argv[0])
        if executable_path.exists():
            runtime_paths.add(str(executable_path.parent))
            runtime_paths.add(str(executable_path.resolve().parent))
        for raw_path in sorted(runtime_paths):
            path = Path(raw_path).expanduser().resolve()
            if path.exists() and not str(path).startswith(("/usr", "/bin", "/lib", "/etc")):
                sandbox.extend(["--ro-bind", str(path), str(path)])

        workspace_flag = "--bind" if writable else "--ro-bind"
        sandbox.extend([workspace_flag, str(workspace), str(workspace)])
        git_metadata = workspace / ".git"
        if git_metadata.exists():
            sandbox.extend(["--ro-bind", str(git_metadata), str(git_metadata)])
            if git_metadata.is_file():
                first_line = git_metadata.read_text(encoding="utf-8").splitlines()[0]
                if first_line.startswith("gitdir:"):
                    git_dir = Path(first_line.removeprefix("gitdir:").strip())
                    if not git_dir.is_absolute():
                        git_dir = (workspace / git_dir).resolve()
                    common_dir_file = git_dir / "commondir"
                    common_dir = (
                        (git_dir / common_dir_file.read_text(encoding="utf-8").strip()).resolve()
                        if common_dir_file.is_file()
                        else git_dir
                    )
                    if common_dir.exists():
                        sandbox.extend(["--ro-bind", str(common_dir), str(common_dir)])
        run_artifact_dir = artifact_dir.parent
        sandbox.extend(["--ro-bind", str(run_artifact_dir), str(run_artifact_dir)])
        sandbox.extend(["--bind", str(artifact_dir), str(artifact_dir)])
        sandbox.extend(["--chdir", str(workspace)])

        # Hide GitHub CLI and replace git with a read-only wrapper inside the namespace.
        blocker = artifact_dir / "blocked-command"
        blocker.write_text("#!/bin/sh\necho 'command blocked by seo-agent sandbox' >&2\nexit 126\n")
        blocker.chmod(blocker.stat().st_mode | stat.S_IXUSR)
        git_wrapper = artifact_dir / "git"
        git_wrapper.write_text(
            "#!/bin/sh\n"
            'case "${1:-}" in\n'
            '  status|diff|show|ls-files|rev-parse|log) exec /usr/lib/git-core/git "$@" ;;\n'
            "  *) echo 'git write/network command blocked by seo-agent sandbox' >&2; exit 126 ;;\n"
            "esac\n"
        )
        git_wrapper.chmod(git_wrapper.stat().st_mode | stat.S_IXUSR)
        if Path("/usr/bin/git").exists():
            sandbox.extend(["--ro-bind", str(git_wrapper), "/usr/bin/git"])
        if Path("/usr/bin/gh").exists():
            sandbox.extend(["--ro-bind", str(blocker), "/usr/bin/gh"])
        return [*sandbox, "--", *argv]
