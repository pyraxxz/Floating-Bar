import unittest

from floatingbar.evidence import EvidenceState, from_result


class EvidenceTests(unittest.TestCase):
    def test_verified_result_is_confirmed(self):
        result = from_result("posted-click (VERIFIED)")
        self.assertEqual(result.state, EvidenceState.VERIFIED)
        self.assertTrue(result.confirmed)
        self.assertFalse(result.retryable)

    def test_verification_unavailable_is_uncertain(self):
        result = from_result("posted-click (verification-unavailable)")
        self.assertEqual(result.state, EvidenceState.UNAVAILABLE)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.retryable)

    def test_unverified_result_is_submitted_and_uncertain(self):
        result = from_result("posted-enter (unverified)")
        self.assertEqual(result.state, EvidenceState.SUBMITTED)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.confirmed)

    def test_error_is_failed_and_retryable(self):
        result = from_result(None, "Telegram disappeared")
        self.assertEqual(result.state, EvidenceState.FAILED)
        self.assertTrue(result.retryable)
        self.assertEqual(result.detail, "Telegram disappeared")

    def test_empty_result_is_unknown(self):
        result = from_result(None)
        self.assertEqual(result.state, EvidenceState.UNKNOWN)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.retryable)

    def test_error_takes_precedence_over_success_strategy(self):
        result = from_result("posted-click (VERIFIED)", "late failure")
        self.assertEqual(result.state, EvidenceState.FAILED)
        self.assertTrue(result.retryable)


if __name__ == "__main__":
    unittest.main()
