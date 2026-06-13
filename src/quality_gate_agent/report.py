from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .models import FixPlan, TriageResult


def render_markdown(plan: FixPlan, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    lines: list[str] = []
    lines.append("# Quality Gate Agent Plan")
    lines.append("")
    lines.append(f"- Generated: {generated_at.isoformat(timespec='seconds')}")
    lines.append(f"- Project: {plan.project_key or 'unknown'}")
    lines.append(f"- Branch: {plan.branch or 'default'}")
    lines.append(f"- Quality gate: {_gate_label(plan)}")
    lines.append(f"- Issues loaded: {plan.total_issues}")
    lines.append(f"- Issues considered: {plan.considered_issues}")
    lines.append(f"- Issues filtered out: {plan.filtered_out}")
    lines.append(f"- Selected candidates: {len(plan.selected)}")
    lines.append("")

    if plan.gate and plan.gate.conditions:
        lines.append("## Quality Gate Conditions")
        lines.append("")
        lines.append("| Metric | Status | Actual | Threshold | Comparator |")
        lines.append("| --- | --- | --- | --- | --- |")
        for condition in plan.gate.conditions:
            lines.append(
                "| "
                + " | ".join(
                    [
                        condition.metric,
                        condition.status,
                        condition.actual or "",
                        condition.threshold or "",
                        condition.comparator or "",
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.append("## Selected Candidates")
    lines.append("")
    if plan.selected:
        lines.extend(_triage_table(plan.selected))
    else:
        lines.append("No safe candidates were selected with the current filters.")
    lines.append("")

    lines.append("## Skipped Or Needs Review")
    lines.append("")
    skipped_preview = plan.skipped[:20]
    if skipped_preview:
        lines.extend(_triage_table(skipped_preview))
        if len(plan.skipped) > len(skipped_preview):
            lines.append("")
            lines.append(f"_Additional skipped issues omitted from preview: {len(plan.skipped) - len(skipped_preview)}_")
    else:
        lines.append("No considered issues were skipped.")
    lines.append("")

    lines.append("## Reviewer Focus")
    lines.append("")
    if plan.selected:
        for result in plan.selected:
            lines.append(f"- `{result.issue.location}`: {result.reviewer_focus}")
    else:
        lines.append("- Review filters or include medium-risk candidates if a manual session is intended.")
    lines.append("")

    lines.append("## Suggested Workflow")
    lines.append("")
    lines.append("1. Create a small remediation branch for this plan.")
    lines.append("2. Apply only the selected candidates listed above.")
    lines.append("3. Run the project test command before re-running the quality gate scanner.")
    lines.append("4. Keep risky and review-classified issues out of automated batches unless a reviewer explicitly opts in.")
    lines.append("")

    if plan.notes:
        lines.append("## Notes")
        lines.append("")
        for note in plan.notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append("## Agent Prompt Pack")
    lines.append("")
    lines.append("```text")
    lines.append("You are remediating a failed quality gate in a small, reviewable batch.")
    lines.append("Apply fixes only for the selected Quality Gate Agent candidates.")
    lines.append("Do not change public behavior unless the issue explicitly requires it.")
    lines.append("Add or update focused tests when behavior could change.")
    lines.append("After editing, summarize the diff, tests run, and any reviewer concerns.")
    lines.append("")
    for result in plan.selected:
        issue = result.issue
        lines.append(f"- {issue.rule} [{issue.severity}/{issue.type}] {issue.location}")
        lines.append(f"  Message: {issue.message}")
        lines.append(f"  Risk: {result.risk_score}/100, {result.reason}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_markdown(plan: FixPlan, path: Path) -> str:
    markdown = render_markdown(plan)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return markdown


def _gate_label(plan: FixPlan) -> str:
    if not plan.gate:
        return "unknown"
    return "passed" if plan.gate.passed else f"failed ({plan.gate.status})"


def _triage_table(results: tuple[TriageResult, ...]) -> list[str]:
    lines = [
        "| Class | Rule | Severity | Type | Location | Risk | Reason |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        issue = result.issue
        lines.append(
            "| "
            + " | ".join(
                [
                    result.classification,
                    f"`{issue.rule}`",
                    issue.severity,
                    issue.type,
                    f"`{issue.location}`",
                    str(result.risk_score),
                    _escape_table(result.reason),
                ]
            )
            + " |"
        )
    return lines


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

