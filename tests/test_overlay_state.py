import unittest

from floatingbar.evidence import EvidenceState, from_result
from floatingbar.overlay import OrbRelayWindow, _classify_send_result


class OverlayStateTests(unittest.TestCase):
    def test_error_is_failed_and_retryable(self):
        result = _classify_send_result(None, "Telegram unavailable")
        self.assertEqual(result.state, EvidenceState.FAILED)
        self.assertTrue(result.retryable)
        self.assertEqual(result.detail, "Telegram unavailable")

    def test_unverified_strategy_is_submitted_and_uncertain(self):
        for strategy in (
            "posted-click (verification-unavailable)",
            "posted-click (unverified)",
        ):
            result = _classify_send_result(strategy, None)
            self.assertTrue(result.uncertain)
            self.assertFalse(result.confirmed)
            self.assertFalse(result.retryable)

    def test_verified_strategy_is_confirmed(self):
        for strategy in (
            "posted-click (VERIFIED)",
            "posted-enter (VERIFIED)",
        ):
            result = _classify_send_result(strategy, None)
            self.assertEqual(result.state, EvidenceState.VERIFIED)
            self.assertTrue(result.confirmed)
            self.assertFalse(result.retryable)

    def test_unknown_result_is_uncertain_not_retryable(self):
        result = _classify_send_result(None, None)
        self.assertEqual(result.state, EvidenceState.UNKNOWN)
        self.assertTrue(result.uncertain)
        self.assertFalse(result.retryable)

    def test_error_takes_precedence_over_success_strategy(self):
        result = _classify_send_result("posted-click (VERIFIED)", "late failure")
        self.assertEqual(result.state, EvidenceState.FAILED)
        self.assertTrue(result.retryable)

    def test_overlay_wrapper_matches_mapper(self):
        strategy = "posted-click (VERIFIED)"
        self.assertEqual(
            _classify_send_result(strategy, None),
            from_result(strategy, None),
        )

    def test_stale_send_result_is_ignored(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._active_attempt_id = 2
        window._sending = True
        window._active_send_text = "new message"
        window._blink_job = None

        window._send_finished(1, "posted-click (VERIFIED)", None)

        self.assertTrue(window._sending)
        self.assertEqual(window._active_send_text, "new message")


if __name__ == "__main__":
    unittest.main()
