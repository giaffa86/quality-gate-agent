from __future__ import annotations

from .classifier import classify_issues
from .models import FixPlan, Issue, PlanFilters, QualityGateStatus, TriageResult, severity_rank


def build_plan(
    issues: list[Issue],
    project_key: str | None = None,
    branch: str | None = None,
    gate: QualityGateStatus | None = None,
    filters: PlanFilters | None = None,
    max_issues: int = 5,
    include_review: bool = False,
) -> FixPlan:
    filters = filters or PlanFilters()
    considered = [issue for issue in issues if _matches_filters(issue, filters)]
    triaged = classify_issues(considered)

    selectable = [
        result
        for result in triaged
        if result.classification == "safe" or (include_review and result.classification == "review")
    ]
    limit = max(0, max_issues)
    selected = tuple(sorted(selectable, key=_selection_sort_key)[:limit])
    selected_keys = {result.issue.key for result in selected}
    skipped = tuple(result for result in triaged if result.issue.key not in selected_keys)

    notes = []
    if include_review:
        notes.append("Medium-risk review candidates were eligible because --include-review was set.")
    if max_issues <= 0:
        notes.append("No issues were selected because --max-issues was zero or negative.")

    return FixPlan(
        project_key=project_key,
        branch=branch,
        gate=gate,
        filters=filters,
        total_issues=len(issues),
        considered_issues=len(considered),
        selected=selected,
        skipped=skipped,
        filtered_out=len(issues) - len(considered),
        notes=tuple(notes),
    )


def _matches_filters(issue: Issue, filters: PlanFilters) -> bool:
    if filters.severities and issue.severity.upper() not in filters.severities:
        return False
    if filters.types and issue.type.upper() not in filters.types:
        return False
    if filters.rules and issue.rule not in filters.rules:
        return False
    if filters.languages and (issue.language or "").lower() not in filters.languages:
        return False
    return True


def _selection_sort_key(result: TriageResult) -> tuple[int, int, str, str]:
    classification_rank = 0 if result.classification == "safe" else 1
    return (
        classification_rank,
        result.risk_score,
        -severity_rank(result.issue.severity),
        result.issue.location,
    )
