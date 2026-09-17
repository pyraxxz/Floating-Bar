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
    default_cases,
    matrix_fingerprint,
    pending_case_ids,
    summarize_report,
    validate_report,
)


class SmokeReportTests(unittest.TestCase):
    def test_blank_report_has_complete_pending_matrix(self):
        report = build_report(environment={"windows_release": "11"})
        summary = summarize_report(report)
        expected_total = len(default_cases())

        self.assertEqual(summary["total"], expected_total)
        self.assertEqual(summary["pending"], expected_total)
        self.assertEqual(summary["pass"], 0)
        self.assertEqual(validate_report(report), ())
        self.assertEqual(len(pending_case_ids(report)), expected_total)

    def test_matrix_fingerprint_is_stable_and_recorded(self):
        report = build_report()
        self.assertEqual(report["matrix_fingerprint"], matrix_fingerprint())
        self.assertRegex(report["matrix_fingerprint"], r"^[0-9a-f]{64}$")

    def test_matrix_fingerprint_rejects_stale_report(self):
        report = build_report()
        report["matrix_fingerprint"] = "0" * 64

        errors = validate_report(report)
        self.assertIn("matrix_fingerprint does not match current smoke matrix", errors)

    def test_summary_counts_results_without_reading_notes(self):
        report = build_report()
        report["cases"][0]["result"] = RESULT_PASS
        report["cases"][1]["result"] = RESULT_FAIL
        report["cases"][2]["result"] = RESULT_BLOCKED
        report["cases"][0]["notes"] = "contains no application content"
        expected_pending = len(default_cases()) - 3

        self.assertEqual(
            summarize_report(report),
            {"pending": expected_pending, "pass": 1, "fail": 1, "blocked": 1, "total": len(default_cases())},
        )
        self.assertEqual(validate_report(report), ())

    def test_terminal_acceptance_matrix_has_each_supported_variant_case(self):
        report = build_report()
        case_ids = {item["case_id"] for item in report["cases"]}
        self.assertTrue(
            {
                "terminal.acceptance.wt",
                "terminal.acceptance.preview",
                "terminal.acceptance.conhost",
                "terminal.acceptance.pwsh",
            }.issubset(case_ids)
        )
        self.assertNotIn("terminal.acceptance", case_ids)

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
            self.assertIn('"schema_version": 2', path.read_text(encoding="utf-8"))
            self.assertIn('"matrix_fingerprint":', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()