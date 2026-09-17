import unittest

from floatingbar.smoke_matrix import build_report, matrix_fingerprint, validate_report


class SmokeDefinitionIntegrityTests(unittest.TestCase):
    def test_case_definition_mutation_is_rejected_even_with_current_fingerprint(self):
        report = build_report()
        report["cases"] = [dict(item) for item in report["cases"]]
        report["cases"][0]["title"] = "Tampered definition"
        report["matrix_fingerprint"] = matrix_fingerprint()

        errors = validate_report(report)

        self.assertIn("case definition mismatch for env.launch: title", errors)
        self.assertNotIn("matrix_fingerprint does not match current smoke matrix", errors)

    def test_case_result_notes_and_timestamp_remain_editable(self):
        report = build_report()
        report["cases"] = [dict(item) for item in report["cases"]]
        report["cases"][0]["result"] = "PASS"
        report["cases"][0]["notes"] = "manual observation"
        report["cases"][0]["tested_at"] = "2026-09-17T12:00:00Z"

        self.assertEqual(validate_report(report), ())


if __name__ == "__main__":
    unittest.main()
