import json
import tempfile
import unittest
from pathlib import Path

from floatingbar.smoke_matrix import (
    RESULT_BLOCKED,
    RESULT_FAIL,
    RESULT_PASS,
    build_report,
    pending_case_ids,
    summarize_report,
    validate_report,
)


class SmokeReportTests(unittest.TestCase):
    def test_blank_report_has_complete_pending_matrix(self):
        report = build_report(environment={"windows_release": "11"})
        summary = summarize_report(report)

        self.assertEqual(summary["total"], 29)
        self.assertEqual(summary["pending"], 29)
        self.assertEqual(summary["pass"], 0)
        self.assertEqual(validate_report(report), ())
        self.assertEqual(len(pending_case_ids(report)), 29)

    def test_summary_counts_results_without_reading_notes(self):
        report = build_report()
        report["cases"][0]["result"] = RESULT_PASS
        report["cases"][1]["result"] = RESULT_FAIL
        report["cases"][2]["result"] = RESULT_BLOCKED
        report["cases"][0]["notes"] = "contains no application content"

        self.assertEqual(
            summarize_report(report),
            {"pending": 26, "pass": 1, "fail": 1, "blocked": 1, "total": 29},
        )
        self.assertEqual(validate_report(report), ())

    def test_require_complete_semantics_are_representable(self):
        report = build_report()
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            for item in report["cases"]
        ]
        self.assertEqual(summarize_report(report)["pending"], 0)
        self.assertEqual(validate_report(report), ())

    def test_duplicate_and_unknown_case_ids_are_rejected(self):
        report = build_report()
        report["cases"] = list(report["cases"])
        report["cases"].append(dict(report["cases"][0]))
        report["cases"][-1]["case_id"] = "unknown.case"

        errors = validate_report(report)
        self.assertIn("unknown case_id: unknown.case", errors)

    def test_report_can_be_serialized_to_a_real_file(self):
        report = build_report(environment={"platform": "Windows"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertIn('"schema_version": 1', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
