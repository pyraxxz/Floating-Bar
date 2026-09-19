import unittest
from pathlib import Path

from floatingbar.smoke_matrix import default_cases


class SmokeChecklistContractTests(unittest.TestCase):
    """Keep the human real-Windows checklist synchronized with the smoke matrix."""

    @classmethod
    def setUpClass(cls):
        cls.repository_root = Path(__file__).resolve().parents[1]
        cls.checklist = (
            cls.repository_root
            / "docs"
            / "REAL_WINDOWS_SMOKE_CHECKLIST.md"
        ).read_text(encoding="utf-8")

    def test_every_smoke_case_has_operator_checklist_heading(self):
        missing = [
            case.case_id
            for case in default_cases()
            if f"### {case.case_id} " not in self.checklist
        ]
        self.assertEqual(
            missing,
            [],
            "real-Windows checklist is missing smoke-matrix cases: "
            + ", ".join(missing),
        )

    def test_checklist_preserves_content_free_execution_rules(self):
        required_phrases = (
            "content-free",
            "message bodies",
            "python tools/smoke_report.py --validate smoke-report.json --require-complete",
        )
        missing = [phrase for phrase in required_phrases if phrase not in self.checklist]
        self.assertEqual(
            missing,
            [],
            "real-Windows checklist is missing safety/reporting guidance: "
            + ", ".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
