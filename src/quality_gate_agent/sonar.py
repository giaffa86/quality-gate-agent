from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .models import Issue, QualityGateCondition, QualityGateStatus


IMPACT_SEVERITY_MAP = {
    "LOW": "MINOR",
    "MEDIUM": "MAJOR",
    "HIGH": "CRITICAL",
}


class SonarClient:
    def __init__(self, base_url: str, token: str | None = None, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @classmethod
    def from_env(cls, base_url: str, token_env: str = "SONAR_TOKEN", timeout: int = 30) -> "SonarClient":
        return cls(base_url=base_url, token=os.environ.get(token_env), timeout=timeout)

    def fetch_issues(
        self,
        project_key: str,
        branch: str | None = None,
        organization: str | None = None,
        severities: tuple[str, ...] = (),
        types: tuple[str, ...] = (),
        rules: tuple[str, ...] = (),
        languages: tuple[str, ...] = (),
        issue_statuses: str | None = "OPEN,CONFIRMED,REOPENED",
    ) -> list[Issue]:
        params: dict[str, Any] = {
            "componentKeys": project_key,
            "ps": 500,
        }
        if branch:
            params["branch"] = branch
        if organization:
            params["organization"] = organization
        if severities:
            params["severities"] = ",".join(severities)
        if types:
            params["types"] = ",".join(types)
        if rules:
            params["rules"] = ",".join(rules)
        if languages:
            params["languages"] = ",".join(languages)
        if issue_statuses:
            params["statuses"] = issue_statuses

        issues: list[Issue] = []
        page = 1
        while True:
            payload = self._get_json("/api/issues/search", params | {"p": page})
            issues.extend(parse_issues_response(payload))
            paging = payload.get("paging", {})
            total = int(paging.get("total", len(issues)))
            page_size = int(paging.get("pageSize", params["ps"]))
            if page * page_size >= total:
                return issues
            page += 1

    def fetch_quality_gate(
        self,
        project_key: str,
        branch: str | None = None,
        organization: str | None = None,
    ) -> QualityGateStatus | None:
        params: dict[str, Any] = {"projectKey": project_key}
        if branch:
            params["branch"] = branch
        if organization:
            params["organization"] = organization
        payload = self._get_json("/api/qualitygates/project_status", params)
        return parse_quality_gate(payload)

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(f"{self.base_url}{path}?{query}")
        request.add_header("Accept", "application/json")
        if self.token:
            token = base64.b64encode(f"{self.token}:".encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {token}")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def load_sonar_export(path: Path) -> tuple[list[Issue], QualityGateStatus | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return parse_issues_response({"issues": payload}), None
    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported JSON shape in {path}")
    return parse_issues_response(payload), parse_quality_gate(payload)


def parse_issues_response(payload: dict[str, Any]) -> list[Issue]:
    components = _component_lookup(payload.get("components", []))
    raw_issues = payload.get("issues", [])
    if not isinstance(raw_issues, list):
        raise ValueError("Sonar response field 'issues' must be a list")
    return [parse_issue(raw, components) for raw in raw_issues]


def parse_issue(raw: dict[str, Any], components: dict[str, str] | None = None) -> Issue:
    components = components or {}
    component = str(raw.get("component") or "")
    path = str(raw.get("path") or components.get(component) or _path_from_component(component) or component)
    rule = str(raw.get("rule") or "unknown")
    severity = _severity_from_raw(raw)
    issue_type = str(raw.get("type") or raw.get("issueType") or "CODE_SMELL").upper()
    line = raw.get("line")
    if line is None and isinstance(raw.get("textRange"), dict):
        line = raw["textRange"].get("startLine")
    return Issue(
        key=str(raw.get("key") or raw.get("id") or f"{rule}:{path}:{line or 0}"),
        rule=rule,
        severity=severity,
        type=issue_type,
        component=component,
        path=path,
        line=int(line) if line is not None else None,
        message=str(raw.get("message") or ""),
        tags=tuple(str(tag).lower() for tag in (raw.get("tags") or ())),
        effort=str(raw.get("effort")) if raw.get("effort") is not None else None,
        language=_language_from_issue(rule, path),
    )


def parse_quality_gate(payload: dict[str, Any]) -> QualityGateStatus | None:
    status_payload = payload.get("projectStatus") or payload.get("qualityGate")
    if not isinstance(status_payload, dict):
        return None
    raw_conditions = status_payload.get("conditions") or []
    conditions = []
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        conditions.append(
            QualityGateCondition(
                metric=str(item.get("metricKey") or item.get("metric") or "unknown"),
                status=str(item.get("status") or "UNKNOWN"),
                comparator=item.get("comparator"),
                threshold=_string_or_none(item.get("errorThreshold") or item.get("threshold")),
                actual=_string_or_none(item.get("actualValue") or item.get("actual")),
            )
        )
    return QualityGateStatus(
        status=str(status_payload.get("status") or "UNKNOWN"),
        conditions=tuple(conditions),
    )


def _component_lookup(components: list[Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for component in components:
        if not isinstance(component, dict):
            continue
        key = component.get("key")
        if not key:
            continue
        path = component.get("path") or component.get("longName") or component.get("name")
        if path:
            lookup[str(key)] = str(path)
    return lookup


def _severity_from_raw(raw: dict[str, Any]) -> str:
    severity = raw.get("severity")
    if severity:
        return str(severity).upper()
    impacts = raw.get("impacts")
    if isinstance(impacts, list) and impacts:
        impact = impacts[0]
        if isinstance(impact, dict):
            mapped = IMPACT_SEVERITY_MAP.get(str(impact.get("severity", "")).upper())
            if mapped:
                return mapped
            return str(impact.get("severity") or "UNKNOWN").upper()
    return "UNKNOWN"


def _language_from_issue(rule: str, path: str) -> str | None:
    if ":" in rule:
        return rule.split(":", 1)[0].lower()
    suffix_map = {
        ".java": "java",
        ".kt": "kotlin",
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".cs": "csharp",
        ".go": "go",
    }
    lowered = path.lower()
    for suffix, language in suffix_map.items():
        if lowered.endswith(suffix):
            return language
    return None


def _path_from_component(component: str) -> str:
    if ":" not in component:
        return component
    return component.split(":", 1)[1]


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)

