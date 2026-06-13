import unittest
from pathlib import Path

from quality_gate_agent.sonar import load_sonar_export, parse_issues_response, parse_quality_gate


class SonarParsingTests(unittest.TestCase):
    def test_loads_sample_export(self):
        issues, gate = load_sonar_export(Path("examples/sample-sonar-response.json"))

        self.assertEqual(len(issues), 7)
        self.assertIsNotNone(gate)
        self.assertEqual(gate.status, "ERROR")
        self.assertEqual(issues[0].path, "src/main/java/com/acme/orders/OrderService.java")
        self.assertEqual(issues[0].language, "java")

    def test_maps_new_impact_severity(self):
        issues = parse_issues_response(
            {
                "issues": [
                    {
                        "key": "new-api",
                        "rule": "python:S1481",
                        "type": "CODE_SMELL",
                        "component": "p:src/app.py",
                        "textRange": {"startLine": 12},
                        "message": "Remove the unused local variable.",
                        "impacts": [{"softwareQuality": "MAINTAINABILITY", "severity": "MEDIUM"}],
                    }
                ]
            }
        )

        self.assertEqual(issues[0].severity, "MAJOR")
        self.assertEqual(issues[0].line, 12)

    def test_quality_gate_conditions(self):
        gate = parse_quality_gate(
            {
                "projectStatus": {
                    "status": "ERROR",
                    "conditions": [
                        {
                            "metricKey": "coverage",
                            "status": "ERROR",
                            "actualValue": "70.1",
                            "errorThreshold": "80",
                            "comparator": "LT",
                        }
                    ],
                }
            }
        )

        self.assertFalse(gate.passed)
        self.assertEqual(gate.conditions[0].metric, "coverage")


if __name__ == "__main__":
    unittest.main()

