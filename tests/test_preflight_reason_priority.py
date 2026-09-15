import unittest

from floatingbar.preflight import PreflightResult


class PreflightReasonPriorityTests(unittest.TestCase):
    def test_blocking_reason_outranks_non_blocking_warning(self):
        result = PreflightResult(
            ready=False,
            reasons=("missing send", "scope changed"),
            reason_codes=("SEND_BUTTON_UNAVAILABLE", "TARGET_SCOPE_CHANGED"),
        )

        self.assertEqual(result.primary_reason_code, "TARGET_SCOPE_CHANGED")

    def test_first_warning_remains_primary_for_ready_degraded_result(self):
        result = PreflightResult(
            ready=True,
            reasons=("no send button", "generic context"),
            reason_codes=("SEND_BUTTON_UNAVAILABLE", "CONTEXT_GUARD_UNAVAILABLE"),
        )

        self.assertEqual(result.primary_reason_code, "SEND_BUTTON_UNAVAILABLE")

    def test_multiple_blocking_reasons_preserve_first_blocking_order(self):
        result = PreflightResult(
            ready=False,
            reasons=("warning", "scope changed", "context changed"),
            reason_codes=(
                "SEND_BUTTON_UNAVAILABLE",
                "TARGET_SCOPE_CHANGED",
                "CONTEXT_CHANGED",
            ),
        )

        self.assertEqual(result.primary_reason_code, "TARGET_SCOPE_CHANGED")


if __name__ == "__main__":
    unittest.main()
