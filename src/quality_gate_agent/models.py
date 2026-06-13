from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SEVERITY_RANK = {
    "INFO": 0,
    "MINOR": 1,
    "MAJOR": 2,
    "CRITICAL": 3,
    "BLOCKER": 4,
}


@dataclass(frozen=True)
class Issue:
    key: str
    rule: str
    severity: str
    type: str
    component: str
    path: str
    line: int | None
    message: str
    tags: tuple[str, ...] = ()
    effort: str | None = None
    language: str | None = None

    @property
    def location(self) -> str:
        if self.line is None:
            return self.path
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class QualityGateCondition:
    metric: str
    status: str
    comparator: str | None = None
    threshold: str | None = None
    actual: str | None = None


@dataclass(frozen=True)
class QualityGateStatus:
    status: str
    conditions: tuple[QualityGateCondition, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status.upper() in {"OK", "PASSED", "PASS"}


@dataclass(frozen=True)
class TriageResult:
    issue: Issue
    classification: str
    risk_score: int
    reason: str
    reviewer_focus: str


@dataclass(frozen=True)
class PlanFilters:
    severities: tuple[str, ...] = ()
    types: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()


@dataclass(frozen=True)
class FixPlan:
    project_key: str | None
    branch: str | None
    gate: QualityGateStatus | None
    filters: PlanFilters
    total_issues: int
    considered_issues: int
    selected: tuple[TriageResult, ...]
    skipped: tuple[TriageResult, ...]
    filtered_out: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(severity.upper(), -1)

