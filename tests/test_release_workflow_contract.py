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

    def test_release_workflow_keeps_release_source_ancestry_guard(self):
        workflow = (
            REPO_ROOT / ".github" / "workflows" / "build-exe.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("$sourceCommit", workflow)
        self.assertIn("$env:EXPECTED_SHA", workflow)


if __name__ == "__main__":
    unittest.main()
