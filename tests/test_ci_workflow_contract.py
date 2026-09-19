import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


class CiWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_ci_is_a_windows_gate_for_prs_and_main_pushes(self):
        self.assertIn("pull_request:", self.workflow)
        self.assertIn(
            "types: [opened, synchronize, reopened, ready_for_review]",
            self.workflow,
        )
        self.assertIn("push:", self.workflow)
        self.assertIn("branches: [main]", self.workflow)
        self.assertIn("runs-on: windows-latest", self.workflow)

    def test_ci_has_a_hard_job_timeout(self):
        self.assertIn("timeout-minutes: 20", self.workflow)

    def test_ci_verifies_dependency_resolution_before_tests(self):
        self.assertIn(
            "python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller",
            self.workflow,
        )
        self.assertIn("python -m pip check", self.workflow)

    def test_ci_keeps_the_regression_suite_and_build_as_required_steps(self):
        self.assertIn("python -m unittest discover -s tests -v", self.workflow)
        self.assertIn(
            "pyinstaller --onefile --noconsole --name FloatingBar main.py",
            self.workflow,
        )

    def test_ci_keeps_test_output_when_a_run_fails(self):
        self.assertIn("actions/upload-artifact@v4", self.workflow)
        self.assertIn("if: ${{ failure() }}", self.workflow)
        self.assertIn("path: ci-test-output.txt", self.workflow)
        self.assertIn("retention-days: 7", self.workflow)


if __name__ == "__main__":
    unittest.main()
