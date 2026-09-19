import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowContractTests(unittest.TestCase):
    def test_release_workflow_requires_exact_main_windows_ci_success(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-exe.yml"
        ).read_text(encoding="utf-8")

        required_fragments = (
            "workflow_id: 'ci.yml'",
            "head_sha: expectedSha",
            "status: 'success'",
            "run.conclusion === 'success'",
            "run.event === 'push'",
            "run.head_branch === 'main'",
            "run.head_sha === expectedSha",
            "No successful main push Windows CI run was found",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, workflow)

    def test_release_workflow_has_dependency_and_timeout_guardrails(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-exe.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("timeout-minutes: 30", workflow)
        self.assertIn(
            "python -m pip install --disable-pip-version-check -r requirements.txt pyinstaller",
            workflow,
        )
        self.assertIn("python -m pip check", workflow)

    def test_release_workflow_requires_exact_smoke_report_source(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-exe.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '$sourceCommit.ToLowerInvariant() -ne $env:EXPECTED_SHA.ToLowerInvariant()',
            workflow,
        )
        self.assertIn(
            "The smoke report was generated from $sourceCommit, but the tagged release source is $env:EXPECTED_SHA.",
            workflow,
        )
        self.assertNotIn("git merge-base --is-ancestor", workflow)

    def test_release_workflow_keeps_release_source_identity_fields(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-exe.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("$sourceCommit", workflow)
        self.assertIn("$env:EXPECTED_SHA", workflow)


if __name__ == "__main__":
    unittest.main()
