from __future__ import annotations

from .models import Issue, TriageResult, severity_rank


SAFE_RULES = {
    "java:S106",
    "java:S1125",
    "java:S1155",
    "java:S1172",
    "java:S1192",
    "java:S1481",
    "java:S1854",
    "javascript:S1481",
    "javascript:S1854",
    "typescript:S1481",
    "typescript:S1854",
    "python:S1481",
}

REVIEW_RULES = {
    "java:S112",
    "java:S3776",
    "javascript:S3776",
    "typescript:S3776",
    "python:S3776",
}

RISKY_TYPES = {"VULNERABILITY", "SECURITY_HOTSPOT"}

RISKY_TAGS = {
    "auth",
    "authentication",
    "authorization",
    "cwe",
    "crypto",
    "injection",
    "owasp",
    "password",
    "privacy",
    "sql",
    "xss",
}

RISKY_TEXT_HINTS = {
    "authentication",
    "authorization",
    "credential",
    "crypto",
    "encrypt",
    "injection",
    "password",
    "permission",
    "secret",
    "sql",
    "token",
    "trust",
    "xss",
}


def classify_issue(issue: Issue) -> TriageResult:
    score = _risk_score(issue)
    hard_risky = _has_risky_signal(issue)

    if hard_risky or score >= 70:
        classification = "risky"
        reason = "security, vulnerability, or high-impact signal requires manual design review"
        focus = "Confirm the security or behavior contract before applying any automated fix."
    elif _is_safe_candidate(issue, score):
        classification = "safe"
        reason = "low-risk maintainability issue with localized fix surface"
        focus = "Verify the local behavior remains equivalent after the patch."
    else:
        classification = "review"
        reason = "fix is plausible but needs reviewer judgement before batching"
        focus = _review_focus(issue)

    return TriageResult(
        issue=issue,
        classification=classification,
        risk_score=score,
        reason=reason,
        reviewer_focus=focus,
    )


def classify_issues(issues: list[Issue]) -> list[TriageResult]:
    return [classify_issue(issue) for issue in issues]


def _risk_score(issue: Issue) -> int:
    severity_score = {
        "INFO": 5,
        "MINOR": 15,
        "MAJOR": 30,
        "CRITICAL": 55,
        "BLOCKER": 75,
    }.get(issue.severity.upper(), 40)
    type_score = {
        "CODE_SMELL": 0,
        "BUG": 15,
        "VULNERABILITY": 35,
        "SECURITY_HOTSPOT": 40,
    }.get(issue.type.upper(), 10)
    score = severity_score + type_score

    if issue.rule in SAFE_RULES:
        score -= 20
    if issue.rule in REVIEW_RULES:
        score += 10
    if _tags_overlap(issue.tags, RISKY_TAGS):
        score += 30
    if _text_contains_hint(issue.message):
        score += 20

    return max(0, min(100, score))


def _is_safe_candidate(issue: Issue, score: int) -> bool:
    if issue.type.upper() != "CODE_SMELL":
        return False
    if severity_rank(issue.severity) > severity_rank("MAJOR"):
        return False
    if issue.rule in REVIEW_RULES:
        return False
    return score <= 35


def _has_risky_signal(issue: Issue) -> bool:
    return (
        issue.type.upper() in RISKY_TYPES
        or _tags_overlap(issue.tags, RISKY_TAGS)
        or _text_contains_hint(issue.message)
    )


def _tags_overlap(tags: tuple[str, ...], risky_tags: set[str]) -> bool:
    lowered = {tag.lower() for tag in tags}
    return bool(lowered & risky_tags)


def _text_contains_hint(message: str) -> bool:
    lowered = message.lower()
    return any(hint in lowered for hint in RISKY_TEXT_HINTS)


def _review_focus(issue: Issue) -> str:
    if issue.rule.endswith(":S3776"):
        return "Check behavior across the extracted branches before accepting complexity refactors."
    if issue.rule.endswith(":S112"):
        return "Confirm the replacement exception type matches the public API contract."
    if issue.type.upper() == "BUG":
        return "Reproduce or cover the bug path before trusting an automated patch."
    return "Review the change boundary and add a regression test when the behavior is not obvious."

