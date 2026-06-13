from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import PlanFilters
from .planner import build_plan
from .report import write_markdown
from .session import SessionError, run_session, write_session_markdown
from .sonar import SonarClient, load_sonar_export


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "plan":
        return _run_plan(args, parser)
    if args.command == "session":
        return _run_session(args)
    parser.error("unknown command")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qga",
        description="Turn quality gate failures into safe, reviewable agent remediation plans.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Create a remediation plan from Sonar issues.")
    source = plan.add_argument_group("source")
    source.add_argument("--issues-file", type=Path, help="Path to a Sonar /api/issues/search JSON response.")
    source.add_argument("--sonar-url", help="Base URL for SonarQube or SonarCloud.")
    source.add_argument("--sonar-token-env", default="SONAR_TOKEN", help="Environment variable containing the token.")
    source.add_argument("--project-key", help="Sonar project key.")
    source.add_argument("--branch", help="Project branch.")
    source.add_argument("--organization", help="SonarCloud organization.")
    source.add_argument("--issue-statuses", default="OPEN,CONFIRMED,REOPENED", help="Comma-separated Sonar issue statuses.")

    filters = plan.add_argument_group("filters")
    filters.add_argument("--severity", help="Comma-separated severities, for example MAJOR,CRITICAL.")
    filters.add_argument("--type", dest="issue_type", help="Comma-separated issue types, for example CODE_SMELL,BUG.")
    filters.add_argument("--rule", help="Comma-separated rule keys.")
    filters.add_argument("--language", help="Comma-separated language keys, for example java,python.")
    filters.add_argument("--max-issues", type=int, default=5, help="Maximum selected issues.")
    filters.add_argument("--include-review", action="store_true", help="Allow medium-risk review candidates in the batch.")

    output = plan.add_argument_group("output")
    output.add_argument("--out", type=Path, default=Path("reports/quality-gate-plan.md"), help="Markdown report path.")
    output.add_argument("--json-out", type=Path, help="Optional machine-readable plan JSON path.")
    output.add_argument("--print", action="store_true", help="Print the Markdown report to stdout.")

    session = subparsers.add_parser("session", help="Start or record a controlled remediation session.")
    session_source = session.add_argument_group("source")
    session_source.add_argument("--plan", type=Path, required=True, help="Path to a plan JSON file from qga plan.")

    session_git = session.add_argument_group("git")
    session_git.add_argument("--worktree", type=Path, default=Path("."), help="Repository worktree to inspect.")
    session_git.add_argument("--create-branch", action="store_true", help="Create a remediation branch before validation.")
    session_git.add_argument("--branch-name", help="Branch to create, or require when --create-branch is omitted.")
    session_git.add_argument("--allow-dirty", action="store_true", help="Allow branch creation from a dirty worktree.")

    validation = session.add_argument_group("validation")
    validation.add_argument(
        "--test-command",
        action="append",
        default=[],
        help="Validation command to run from the worktree. May be provided more than once.",
    )
    validation.add_argument("--command-timeout", type=int, default=600, help="Timeout per validation command in seconds.")

    session_output = session.add_argument_group("output")
    session_output.add_argument(
        "--out",
        type=Path,
        default=Path("reports/remediation-session.md"),
        help="Markdown session report path.",
    )
    session_output.add_argument("--print", action="store_true", help="Print the Markdown session report to stdout.")
    return parser


def _run_plan(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    filters = PlanFilters(
        severities=_csv(args.severity, upper=True),
        types=_csv(args.issue_type, upper=True),
        rules=_csv(args.rule),
        languages=_csv(args.language, lower=True),
    )

    if args.issues_file:
        issues, gate = load_sonar_export(args.issues_file)
    else:
        if not args.sonar_url or not args.project_key:
            parser.error("provide either --issues-file or both --sonar-url and --project-key")
        client = SonarClient.from_env(args.sonar_url, token_env=args.sonar_token_env)
        issues = client.fetch_issues(
            project_key=args.project_key,
            branch=args.branch,
            organization=args.organization,
            severities=filters.severities,
            types=filters.types,
            rules=filters.rules,
            languages=filters.languages,
            issue_statuses=args.issue_statuses,
        )
        gate = client.fetch_quality_gate(
            project_key=args.project_key,
            branch=args.branch,
            organization=args.organization,
        )

    plan = build_plan(
        issues=issues,
        project_key=args.project_key,
        branch=args.branch,
        gate=gate,
        filters=filters,
        max_issues=args.max_issues,
        include_review=args.include_review,
    )
    markdown = write_markdown(plan, args.out)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    if args.print:
        sys.stdout.write(markdown)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(f"Wrote {args.out}\n")
        if args.json_out:
            sys.stdout.write(f"Wrote {args.json_out}\n")
    return 0


def _run_session(args: argparse.Namespace) -> int:
    try:
        session = run_session(
            plan_path=args.plan,
            worktree=args.worktree,
            create_branch=args.create_branch,
            branch_name=args.branch_name,
            test_commands=tuple(args.test_command),
            allow_dirty=args.allow_dirty,
            command_timeout=args.command_timeout,
        )
    except (OSError, ValueError, SessionError) as exc:
        sys.stderr.write(f"qga session: {exc}\n")
        return 2

    markdown = write_session_markdown(session, args.out)
    if args.print:
        sys.stdout.write(markdown)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(f"Wrote {args.out}\n")
    return 0 if session.succeeded else 1


def _csv(value: str | None, upper: bool = False, lower: bool = False) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if upper:
        parts = [part.upper() for part in parts]
    if lower:
        parts = [part.lower() for part in parts]
    return tuple(parts)


if __name__ == "__main__":
    raise SystemExit(main())
