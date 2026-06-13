import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from quality_gate_agent.cli import main
from quality_gate_agent.session import SessionError, render_session_markdown, run_session


class SessionWorkflowTests(unittest.TestCase):
    def test_runs_validation_and_renders_session_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self._init_repo(base / "repo")
            plan_path = self._write_plan(base)
            command = f'"{sys.executable}" -c "print(123)"'

            session = run_session(plan_path=plan_path, worktree=repo, test_commands=(command,))
            markdown = render_session_markdown(session)

            self.assertTrue(session.succeeded)
            self.assertEqual(session.commands[0].exit_code, 0)
            self.assertIn("Session status: passed", markdown)
            self.assertIn("123", markdown)
            self.assertIn("java:S1854", markdown)

    def test_creates_default_branch_from_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self._init_repo(base / "repo")
            plan_path = self._write_plan(base)

            session = run_session(
                plan_path=plan_path,
                worktree=repo,
                create_branch=True,
                generated_at=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(session.git.current_branch, "qga/my-service-20260613-120000")
            self.assertEqual(session.git.branch_action, "created qga/my-service-20260613-120000")

    def test_refuses_to_create_branch_from_dirty_worktree_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self._init_repo(base / "repo")
            plan_path = self._write_plan(base)
            (repo / "scratch.txt").write_text("dirty", encoding="utf-8")

            with self.assertRaisesRegex(SessionError, "uncommitted changes"):
                run_session(plan_path=plan_path, worktree=repo, create_branch=True)

    def test_cli_writes_report_and_returns_failed_validation_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = self._init_repo(base / "repo")
            plan_path = self._write_plan(base)
            report_path = base / "session.md"
            command = f'"{sys.executable}" -c "import sys; sys.exit(7)"'

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(
                    [
                        "session",
                        "--plan",
                        str(plan_path),
                        "--worktree",
                        str(repo),
                        "--test-command",
                        command,
                        "--out",
                        str(report_path),
                    ]
                )

            self.assertEqual(code, 1)
            self.assertIn("Session status: failed", report_path.read_text(encoding="utf-8"))
            self.assertIn("Exit code: 7", report_path.read_text(encoding="utf-8"))

    def _init_repo(self, path: Path) -> Path:
        path.mkdir()
        try:
            result = subprocess.run(["git", "init"], cwd=path, text=True, capture_output=True)
        except FileNotFoundError:
            self.skipTest("git is not installed")
        if result.returncode != 0:
            self.fail(result.stderr)
        return path

    def _write_plan(self, directory: Path) -> Path:
        path = directory / "plan.json"
        payload = {
            "project_key": "my-service",
            "branch": "feature/orders",
            "selected": [
                {
                    "issue": {
                        "key": "safe",
                        "rule": "java:S1854",
                        "severity": "MAJOR",
                        "type": "CODE_SMELL",
                        "component": "p:src/Foo.java",
                        "path": "src/Foo.java",
                        "line": 1,
                        "message": "Remove this useless assignment.",
                    },
                    "classification": "safe",
                    "risk_score": 10,
                    "reason": "localized maintainability fix",
                    "reviewer_focus": "Verify equivalent behavior.",
                }
            ],
            "skipped": [],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
