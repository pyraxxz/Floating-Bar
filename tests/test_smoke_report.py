import json
import subprocess
import sys
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

        self.assertEqual(summary["total"], 30)
        self.assertEqual(summary["pending"], 30)
        self.assertEqual(summary["pass"], 0)
        self.assertEqual(validate_report(report), ())
        self.assertEqual(len(pending_case_ids(report)), 30)

    def test_summary_counts_results_without_reading_notes(self):
        report = build_report()
        report["cases"][0]["result"] = RESULT_PASS
        report["cases"][1]["result"] = RESULT_FAIL
        report["cases"][2]["result"] = RESULT_BLOCKED
        report["cases"][0]["notes"] = "contains no application content"

        self.assertEqual(
            summarize_report(report),
            {"pending": 27, "pass": 1, "fail": 1, "blocked": 1, "total": 30},
        )
        self.assertEqual(validate_report(report), ())

    def test_terminal_acceptance_case_is_present_in_the_matrix(self):
        report = build_report()
        case_ids = {item["case_id"] for item in report["cases"]}
        self.assertIn("terminal.acceptance", case_ids)

    def test_require_complete_semantics_are_representable(self):
        report = build_report()
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            for item in report["cases"]
        ]
        self.assertEqual(summarize_report(report)["pending"], 0)
        self.assertEqual(validate_report(report), ())

    def test_release_gate_accepts_complete_windows_report(self):
        report = build_report(
            environment={
                "platform": "Windows",
                "windows_release": "11",
                "windows_version": "10.0.26100",
                "architecture": "AMD64",
                "python_version": "3.12.10",
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
            }
        )
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            for item in report["cases"]
        ]

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--validate",
                    str(path),
                    "--require-complete",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Release gate: PASS", result.stdout)

    def test_release_gate_rejects_non_windows_environment(self):
        report = build_report(
            environment={
                "platform": "Linux",
                "windows_release": "",
                "windows_version": "",
                "architecture": "x86_64",
                "python_version": "3.12.10",
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
            }
        )
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            for item in report["cases"]
        ]

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--validate",
                    str(path),
                    "--require-complete",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 5)
        self.assertIn("environment snapshot is not a Windows validation snapshot", result.stdout)

    def test_release_gate_rejects_missing_source_commit(self):
        report = build_report(
            environment={
                "platform": "Windows",
                "windows_release": "11",
                "windows_version": "10.0.26100",
                "architecture": "AMD64",
                "python_version": "3.12.10",
            }
        )
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            for item in report["cases"]
        ]

        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--validate",
                    str(path),
                    "--require-complete",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 5)
        self.assertIn("environment snapshot missing field: source_commit", result.stdout)

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
