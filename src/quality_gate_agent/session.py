from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionError(RuntimeError):
    """Raised when a remediation session cannot be started safely."""


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class GitState:
    root: Path
    initial_branch: str
    current_branch: str
    branch_action: str
    was_dirty: bool
    is_dirty: bool
    status_lines: tuple[str, ...]


@dataclass(frozen=True)
class RemediationSession:
    plan_path: Path
    plan: dict[str, Any]
    generated_at: datetime
    git: GitState
    commands: tuple[CommandResult, ...]
    notes: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return all(command.passed for command in self.commands)


def run_session(
    plan_path: Path,
    worktree: Path = Path("."),
    create_branch: bool = False,
    branch_name: str | None = None,
    test_commands: tuple[str, ...] = (),
    allow_dirty: bool = False,
    command_timeout: int = 600,
    generated_at: datetime | None = None,
) -> RemediationSession:
    generated_at = generated_at or datetime.now(timezone.utc)
    plan_path = plan_path.resolve()
    worktree = worktree.resolve()
    plan = load_plan(plan_path)

    initial_branch = _current_branch(worktree)
    initial_status = _git_status(worktree)
    was_dirty = bool(initial_status)

    if create_branch and was_dirty and not allow_dirty:
        raise SessionError("worktree has uncommitted changes; use --allow-dirty to create a branch anyway")

    branch_action = "not requested"
    if create_branch:
        target_branch = branch_name or default_branch_name(plan, generated_at)
        _create_branch(worktree, target_branch)
        branch_action = f"created {target_branch}"
    elif branch_name:
        if initial_branch != branch_name:
            raise SessionError(f"current branch is {initial_branch!r}, expected {branch_name!r}")
        branch_action = f"validated {branch_name}"

    command_results = tuple(
        _run_validation_command(command, worktree, command_timeout) for command in test_commands
    )
    final_status = _git_status(worktree)
    git_state = GitState(
        root=_git_root(worktree),
        initial_branch=initial_branch,
        current_branch=_current_branch(worktree),
        branch_action=branch_action,
        was_dirty=was_dirty,
        is_dirty=bool(final_status),
        status_lines=tuple(final_status),
    )

    notes: list[str] = []
    if not test_commands:
        notes.append("No validation commands were configured for this session.")
    if allow_dirty and was_dirty:
        notes.append("Session started from a dirty worktree because --allow-dirty was set.")

    return RemediationSession(
        plan_path=plan_path,
        plan=plan,
        generated_at=generated_at,
        git=git_state,
        commands=command_results,
        notes=tuple(notes),
    )


def load_plan(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SessionError(f"plan JSON must be an object: {path}")
    if "selected" not in payload:
        raise SessionError(f"plan JSON is missing the 'selected' field: {path}")
    return payload


def default_branch_name(plan: dict[str, Any], generated_at: datetime) -> str:
    project = _slug(str(plan.get("project_key") or "quality-gate"))
    stamp = generated_at.strftime("%Y%m%d-%H%M%S")
    return f"qga/{project}-{stamp}"


def render_session_markdown(session: RemediationSession) -> str:
    lines: list[str] = []
    lines.append("# Quality Gate Agent Session")
    lines.append("")
    lines.append(f"- Generated: {session.generated_at.isoformat(timespec='seconds')}")
    lines.append(f"- Plan: `{session.plan_path}`")
    lines.append(f"- Project: {session.plan.get('project_key') or 'unknown'}")
    lines.append(f"- Source branch: {session.plan.get('branch') or 'default'}")
    lines.append(f"- Selected candidates: {len(session.plan.get('selected') or [])}")
    lines.append(f"- Session status: {'passed' if session.succeeded else 'failed'}")
    lines.append("")

    lines.append("## Git")
    lines.append("")
    lines.append(f"- Repository: `{session.git.root}`")
    lines.append(f"- Initial branch: `{session.git.initial_branch}`")
    lines.append(f"- Current branch: `{session.git.current_branch}`")
    lines.append(f"- Branch action: {session.git.branch_action}")
    lines.append(f"- Started dirty: {_yes_no(session.git.was_dirty)}")
    lines.append(f"- Currently dirty: {_yes_no(session.git.is_dirty)}")
    if session.git.status_lines:
        lines.append("")
        lines.append("```text")
        lines.extend(session.git.status_lines)
        lines.append("```")
    lines.append("")

    lines.append("## Selected Candidates")
    lines.append("")
    selected = session.plan.get("selected") or []
    if selected:
        lines.extend(_selected_table(selected))
    else:
        lines.append("No selected candidates were found in the plan.")
    lines.append("")

    lines.append("## Validation")
    lines.append("")
    if session.commands:
        for command in session.commands:
            lines.append(f"### `{command.command}`")
            lines.append("")
            lines.append(f"- Exit code: {command.exit_code}")
            if command.stdout:
                lines.append("")
                lines.append("Stdout:")
                lines.append("")
                lines.append("```text")
                lines.append(_trim_output(command.stdout))
                lines.append("```")
            if command.stderr:
                lines.append("")
                lines.append("Stderr:")
                lines.append("")
                lines.append("```text")
                lines.append(_trim_output(command.stderr))
                lines.append("```")
            lines.append("")
    else:
        lines.append("No validation commands were configured.")
        lines.append("")

    if session.notes:
        lines.append("## Notes")
        lines.append("")
        for note in session.notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Agent Handoff")
    lines.append("")
    lines.append("```text")
    lines.append("Continue this remediation session in a small, reviewable batch.")
    lines.append("Apply fixes only for the selected candidates from the linked plan.")
    lines.append("Keep unrelated changes out of the branch.")
    lines.append("Run the validation commands again after edits, then update this session report.")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_session_markdown(session: RemediationSession, path: Path) -> str:
    markdown = render_session_markdown(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return markdown


def _run_validation_command(command: str, cwd: Path, timeout: int) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            exit_code=124,
            stdout=_output_text(exc.stdout),
            stderr=_output_text(exc.stderr) or f"Command timed out after {timeout} seconds.",
        )
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _create_branch(worktree: Path, branch_name: str) -> None:
    if _git(["show-ref", "--verify", f"refs/heads/{branch_name}"], worktree, check=False).returncode == 0:
        raise SessionError(f"branch already exists: {branch_name}")
    _git(["checkout", "-b", branch_name], worktree)


def _git_root(worktree: Path) -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"], worktree).stdout.strip())


def _current_branch(worktree: Path) -> str:
    branch = _git(["branch", "--show-current"], worktree, check=False).stdout.strip()
    if branch:
        return branch
    symbolic = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], worktree, check=False)
    if symbolic.returncode == 0 and symbolic.stdout.strip():
        return symbolic.stdout.strip()
    head = _git(["rev-parse", "--short", "HEAD"], worktree, check=False)
    if head.returncode == 0 and head.stdout.strip():
        return head.stdout.strip()
    return "detached"


def _git_status(worktree: Path) -> list[str]:
    status = _git(["status", "--porcelain"], worktree).stdout
    return [line for line in status.splitlines() if line.strip()]


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise SessionError("git is required to run a remediation session") from exc
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise SessionError(f"git {' '.join(args)} failed: {detail}")
    return completed


def _selected_table(selected: list[Any]) -> list[str]:
    lines = [
        "| Rule | Severity | Type | Location | Risk |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for item in selected:
        if not isinstance(item, dict):
            continue
        issue = item.get("issue") if isinstance(item.get("issue"), dict) else {}
        location = _issue_location(issue)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_table_text(issue.get('rule') or 'unknown')}`",
                    _table_text(issue.get("severity") or ""),
                    _table_text(issue.get("type") or ""),
                    f"`{_table_text(location)}`",
                    _table_text(item.get("risk_score") if item.get("risk_score") is not None else ""),
                ]
            )
            + " |"
        )
    return lines


def _issue_location(issue: dict[str, Any]) -> str:
    path = str(issue.get("path") or issue.get("component") or "unknown")
    line = issue.get("line")
    if line is None:
        return path
    return f"{path}:{line}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._").lower()
    return slug or "quality-gate"


def _table_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _trim_output(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value.rstrip()
    return value[:limit].rstrip() + "\n... output truncated ..."


def _output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
