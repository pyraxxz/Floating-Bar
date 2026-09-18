import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from floatingbar.smoke_matrix import (
    RESULT_BLOCKED,
    RESULT_FAIL,
    RESULT_PASS,
    build_report,
    completion_errors,
    default_cases,
    environment_case_errors,
    matrix_fingerprint,
    pending_case_ids,
    summarize_report,
    validate_report,
)


class SmokeReportTests(unittest.TestCase):
    @staticmethod
    def _complete_environment():
        return {
            "platform": "Windows",
            "windows_release": "11",
            "windows_version": "10.0.26100",
            "architecture": "AMD64",
            "python_version": "3.12.10",
            "source_commit": "0123456789abcdef0123456789abcdef01234567",
            "monitors": [
                {"index": 0, "width": 1920, "height": 1080, "dpi_x": 96, "dpi_y": 96},
                {"index": 1, "width": 2560, "height": 1440, "dpi_x": 144, "dpi_y": 144},
            ],
            "adapters": [
                {"key": "telegram", "open_window_count": 1, "observed_processes": ["telegram.exe"], "observed_process_instances": [{"process_name": "telegram.exe", "process_start": 1001}]},
                {"key": "terminal", "open_window_count": 1, "observed_processes": ["windowsterminal.exe", "windowsterminalpreview.exe", "conhost.exe"], "observed_process_instances": [{"process_name": "windowsterminal.exe", "process_start": 1002}]},
                {"key": "powershell", "open_window_count": 1, "observed_processes": ["pwsh.exe"], "observed_process_instances": [{"process_name": "pwsh.exe", "process_start": 1003}]},
                {"key": "cmd", "open_window_count": 1, "observed_processes": ["cmd.exe"], "observed_process_instances": [{"process_name": "cmd.exe", "process_start": 1004}]},
                {"key": "whatsapp", "open_window_count": 1, "observed_processes": ["whatsapp.exe"], "observed_process_instances": [{"process_name": "whatsapp.exe", "process_start": 1005}]},
                {"key": "discord", "open_window_count": 1, "observed_processes": ["discord.exe"], "observed_process_instances": [{"process_name": "discord.exe", "process_start": 1006}]},
                {"key": "slack", "open_window_count": 1, "observed_processes": ["slack.exe"], "observed_process_instances": [{"process_name": "slack.exe", "process_start": 1007}]},
                {"key": "teams", "open_window_count": 1, "observed_processes": ["msteams.exe"], "observed_process_instances": [{"process_name": "msteams.exe", "process_start": 1008}]},
            ],
        }

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

    def test_schema_v2_report_is_rejected_after_provenance_change(self):
        report = build_report()
        report["schema_version"] = 2

        errors = validate_report(report)
        self.assertIn("unsupported schema_version", errors)

    def test_matrix_fingerprint_rejects_stale_report(self):
        report = build_report()
        report["matrix_fingerprint"] = "0" * 64

        errors = validate_report(report)
        self.assertIn("matrix_fingerprint does not match current smoke matrix", errors)

    def test_malformed_schema_version_is_reported_without_raising(self):
        report = build_report()
        report["schema_version"] = "not-a-number"

        errors = validate_report(report)
        self.assertIn("invalid schema_version", errors)

    def test_adapter_registry_integrity_is_part_of_report_validation(self):
        report = build_report()
        with patch(
            "floatingbar.smoke_matrix.registry_validation_errors",
            return_value=("verification contract mismatch: example",),
        ):
            errors = validate_report(report)

        self.assertIn("adapter registry: verification contract mismatch: example", errors)

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


    def test_critical_telegram_pass_requires_process_instance_evidence(self):
        report = build_report(environment={
            "adapters": [
                {
                    "key": "telegram",
                    "open_window_count": 1,
                    "observed_processes": ["telegram.exe"],
                    "observed_process_instances": [],
                },
            ]
        })
        for item in report["cases"]:
            if item["case_id"] == "telegram.send":
                item["result"] = RESULT_PASS
        errors = environment_case_errors(report)
        self.assertIn(
            "environment process-instance evidence missing for telegram.send (telegram)",
            errors,
        )

    def test_critical_telegram_pass_accepts_process_instance_evidence(self):
        report = build_report(environment={
            "adapters": [
                {
                    "key": "telegram",
                    "open_window_count": 1,
                    "observed_processes": ["telegram.exe"],
                    "observed_process_instances": [
                        {"process_name": "telegram.exe", "process_start": 123}
                    ],
                },
            ]
        })
        for item in report["cases"]:
            if item["case_id"] == "telegram.send":
                item["result"] = RESULT_PASS
        errors = environment_case_errors(report)
        self.assertNotIn(
            "environment process-instance evidence missing for telegram.send (telegram)",
            errors,
        )

    def test_restart_pass_requires_process_instance_evidence(self):
        report = build_report(environment={
            "adapters": [
                {
                    "key": "telegram",
                    "open_window_count": 1,
                    "observed_processes": ["telegram.exe"],
                    "observed_process_instances": [],
                },
            ]
        })
        for item in report["cases"]:
            if item["case_id"] == "telegram.restart":
                item["result"] = RESULT_PASS
        errors = environment_case_errors(report)
        self.assertIn(
            "environment process-instance evidence missing for telegram.restart (telegram)",
            errors,
        )

    def test_restart_pass_accepts_process_instance_evidence(self):
        report = build_report(environment={
            "adapters": [
                {
                    "key": "telegram",
                    "open_window_count": 1,
                    "observed_processes": ["telegram.exe"],
                    "observed_process_instances": [
                        {"process_name": "telegram.exe", "process_start": 123}
                    ],
                },
            ]
        })
        for item in report["cases"]:
            if item["case_id"] == "telegram.restart":
                item["result"] = RESULT_PASS
        errors = environment_case_errors(report)
        self.assertNotIn(
            "environment process-instance evidence missing for telegram.restart (telegram)",
            errors,
        )

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
        self.assertEqual(
            len(completion_errors(report)),
            len(default_cases()),
        )

    def test_environment_case_errors_require_distinct_dpi_for_dpi_pass(self):
        report = build_report(environment={
            "monitors": [
                {"index": 0, "width": 1920, "height": 1080, "dpi_x": 96, "dpi_y": 96},
                {"index": 1, "width": 2560, "height": 1440, "dpi_x": 96, "dpi_y": 96},
            ]
        })
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            if item["case_id"] == "env.dpi" else item
            for item in report["cases"]
        ]
        errors = environment_case_errors(report)
        self.assertIn("env.dpi PASS requires at least two monitors with distinct effective DPI values", errors)

    def test_environment_case_errors_require_terminal_environment_for_critical_pass(self):
        report = build_report(environment={"monitors": [
            {"index": 0, "width": 1920, "height": 1080, "dpi_x": 96, "dpi_y": 96},
            {"index": 1, "width": 2560, "height": 1440, "dpi_x": 144, "dpi_y": 144},
        ]})
        report["cases"] = [
            {**item, "result": RESULT_PASS}
            if item["case_id"] == "terminal.acceptance.pwsh" else item
            for item in report["cases"]
        ]
        errors = environment_case_errors(report)
        self.assertIn("environment evidence missing for terminal.acceptance.pwsh", errors)

    def test_record_command_stamps_completed_case(self):
        report = build_report()
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--record",
                    str(path),
                    "--case-id",
                    "telegram.send",
                    "--result",
                    "PASS",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

            updated = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        selected = next(
            item for item in updated["cases"] if item["case_id"] == "telegram.send"
        )
        self.assertEqual(selected["result"], "PASS")
        self.assertRegex(
            selected["tested_at"],
            r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
        )
        self.assertTrue(all(
            item["result"] == "PENDING"
            for item in updated["cases"]
            if item["case_id"] != "telegram.send"
        ))

    def test_cli_failure_does_not_expose_raw_exception_text(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{ definitely not json", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--validate",
                    str(path),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 2)
        self.assertIn("exception=JSONDecodeError", result.stderr)
        self.assertNotIn("definitely not json", result.stderr)

    def test_record_command_refuses_overwrite_without_force(self):
        report = build_report()
        report["cases"][0]["result"] = "PASS"
        report["cases"][0]["tested_at"] = "2026-09-18T12:00:00Z"
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--record",
                    str(path),
                    "--case-id",
                    report["cases"][0]["case_id"],
                    "--result",
                    "FAIL",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

            updated = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 3)
        self.assertIn("already PASS", result.stderr)
        self.assertEqual(updated["cases"][0]["result"], "PASS")
        self.assertEqual(updated["cases"][0]["tested_at"], "2026-09-18T12:00:00Z")

    def test_record_command_force_replaces_completed_case(self):
        report = build_report()
        report["cases"][0]["result"] = "PASS"
        report["cases"][0]["tested_at"] = "2026-09-18T12:00:00Z"
        root = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "smoke.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "smoke_report.py"),
                    "--record",
                    str(path),
                    "--case-id",
                    report["cases"][0]["case_id"],
                    "--result",
                    "BLOCKED",
                    "--force",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

            updated = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(updated["cases"][0]["result"], "BLOCKED")
        self.assertNotEqual(updated["cases"][0]["tested_at"], "2026-09-18T12:00:00Z")
        self.assertRegex(
            updated["cases"][0]["tested_at"],
            r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
        )

    def test_release_gate_accepts_complete_windows_report(self):
        report = build_report(environment=self._complete_environment())
        report["cases"] = [
            {**item, "result": RESULT_PASS, "tested_at": "2026-09-18T12:00:00Z"}
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
        self.assertIn("matrix_fingerprint=", result.stdout)

    def test_release_gate_rejects_completed_case_without_timestamp(self):
        report = build_report(environment=self._complete_environment())
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

        self.assertEqual(result.returncode, 3)
        self.assertIn("missing tested_at", result.stdout)

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
            text = path.read_text(encoding="utf-8")
            self.assertIn('"schema_version": 3', text)
            self.assertIn('"matrix_fingerprint":', text)


if __name__ == "__main__":
    unittest.main()
