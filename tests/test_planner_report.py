import unittest
from datetime import datetime, timezone

from quality_gate_agent.models import Issue, PlanFilters
from quality_gate_agent.planner import build_plan
from quality_gate_agent.report import render_markdown


class PlannerReportTests(unittest.TestCase):
    def test_builds_plan_with_safe_selection_and_skips_risky(self):
        issues = [
            Issue(
                key="safe",
                rule="java:S1854",
                severity="MAJOR",
                type="CODE_SMELL",
                component="p:src/Foo.java",
                path="src/Foo.java",
                line=1,
                message="Remove this useless assignment.",
                language="java",
            ),
            Issue(
                key="risky",
                rule="java:S3649",
                severity="CRITICAL",
                type="VULNERABILITY",
                component="p:src/Repo.java",
                path="src/Repo.java",
                line=2,
                message="SQL queries should not be vulnerable to injection attacks.",
                tags=("cwe",),
                language="java",
            ),
        ]

        plan = build_plan(
            issues,
            project_key="p",
            branch="feature",
            filters=PlanFilters(severities=("MAJOR", "CRITICAL"), languages=("java",)),
            max_issues=5,
        )

        self.assertEqual(len(plan.selected), 1)
        self.assertEqual(plan.selected[0].issue.key, "safe")
        self.assertEqual(len(plan.skipped), 1)

        markdown = render_markdown(plan, generated_at=datetime(2026, 6, 13, tzinfo=timezone.utc))
        self.assertIn("# Quality Gate Agent Plan", markdown)
        self.assertIn("java:S1854", markdown)
        self.assertIn("Agent Prompt Pack", markdown)
        self.assertIn("src/Foo.java:1", markdown)

    def test_zero_max_issues_selects_none(self):
        issues = [
            Issue(
                key="safe",
                rule="java:S1854",
                severity="MAJOR",
                type="CODE_SMELL",
                component="p:src/Foo.java",
                path="src/Foo.java",
                line=1,
                message="Remove this useless assignment.",
                language="java",
            )
        ]

        plan = build_plan(issues, max_issues=0)

        self.assertEqual(plan.selected, ())
        self.assertEqual(len(plan.skipped), 1)


if __name__ == "__main__":
    unittest.main()
