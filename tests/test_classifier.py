import unittest

from quality_gate_agent.classifier import classify_issue
from quality_gate_agent.models import Issue


class ClassifierTests(unittest.TestCase):
    def test_known_maintainability_rule_is_safe(self):
        result = classify_issue(
            Issue(
                key="1",
                rule="java:S1192",
                severity="MAJOR",
                type="CODE_SMELL",
                component="p:src/Foo.java",
                path="src/Foo.java",
                line=10,
                message="Define a constant instead of duplicating this literal.",
                tags=("convention",),
                language="java",
            )
        )

        self.assertEqual(result.classification, "safe")
        self.assertLessEqual(result.risk_score, 35)

    def test_security_hotspot_is_risky(self):
        result = classify_issue(
            Issue(
                key="2",
                rule="java:S5131",
                severity="CRITICAL",
                type="SECURITY_HOTSPOT",
                component="p:src/AuthFilter.java",
                path="src/AuthFilter.java",
                line=20,
                message="Make sure allowing requests without authentication is safe here.",
                tags=("owasp", "auth"),
                language="java",
            )
        )

        self.assertEqual(result.classification, "risky")
        self.assertGreaterEqual(result.risk_score, 70)

    def test_complexity_rule_requires_review(self):
        result = classify_issue(
            Issue(
                key="3",
                rule="java:S3776",
                severity="MAJOR",
                type="CODE_SMELL",
                component="p:src/BillingMapper.java",
                path="src/BillingMapper.java",
                line=30,
                message="Refactor this method to reduce its Cognitive Complexity.",
                tags=("brain-overload",),
                language="java",
            )
        )

        self.assertEqual(result.classification, "review")
        self.assertIn("complexity", result.reviewer_focus.lower())


if __name__ == "__main__":
    unittest.main()

