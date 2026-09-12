import unittest
from unittest.mock import Mock, patch

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

    def test_failed_send_enables_retry_menu_and_preserves_text_and_target(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._active_attempt_id = 1
        window._sending = True
        window._active_send_text = "retry me"
        window._work_hwnd = 321
        window._blink_job = None
        window._retry_draft = None
        window._retry_target_hwnd = 0
        window._flash_orb = Mock()
        window._show_feedback = Mock()
        window._hide_feedback = Mock()
        window._set_retry_menu_enabled = Mock()

        window._send_finished(1, None, "Telegram unavailable")

        self.assertEqual(window._retry_draft, "retry me")
        self.assertEqual(window._retry_target_hwnd, 321)
        window._set_retry_menu_enabled.assert_called_once_with(True)

    def test_confirmed_send_disables_retry_menu(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._active_attempt_id = 1
        window._sending = True
        window._active_send_text = "sent"
        window._work_hwnd = 321
        window._blink_job = None
        window._retry_draft = "old draft"
        window._retry_target_hwnd = 321
        window._flash_orb = Mock()
        window._show_feedback = Mock()
        window._hide_feedback = Mock()
        window._set_retry_menu_enabled = Mock()

        window._send_finished(1, "posted-click (VERIFIED)", None)

        self.assertIsNone(window._retry_draft)
        self.assertEqual(window._retry_target_hwnd, 0)
        window._set_retry_menu_enabled.assert_called_once_with(False)

    def test_uncertain_send_disables_retry_menu_and_drops_draft(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._active_attempt_id = 1
        window._sending = True
        window._active_send_text = "maybe sent"
        window._work_hwnd = 321
        window._blink_job = None
        window._retry_draft = "old draft"
        window._retry_target_hwnd = 321
        window._flash_orb = Mock()
        window._show_feedback = Mock()
        window._hide_feedback = Mock()
        window._set_retry_menu_enabled = Mock()

        window._send_finished(1, "posted-click (verification-unavailable)", None)

        self.assertIsNone(window._retry_draft)
        self.assertEqual(window._retry_target_hwnd, 0)
        window._set_retry_menu_enabled.assert_called_once_with(False)

    def test_retry_failed_draft_prefers_original_target_over_current_foreground(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._sending = False
        window._retry_draft = "retry me"
        window._retry_target_hwnd = 321
        window._work_hwnd = 0
        window._hide_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch(
            "floatingbar.overlay.winapi.get_foreground_window",
            return_value=456,
        ) as foreground:
            window._retry_failed_draft()

        self.assertEqual(window._work_hwnd, 321)
        foreground.assert_not_called()
        window._hide_feedback.assert_called_once_with()
        window._show_bar.assert_called_once_with()
        window._set_retry_menu_enabled.assert_called_once_with(True)

    def test_retry_failed_draft_falls_back_to_foreground_when_no_target_saved(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._sending = False
        window._retry_draft = "retry me"
        window._retry_target_hwnd = 0
        window._work_hwnd = 0
        window._hide_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch(
            "floatingbar.overlay.winapi.get_foreground_window",
            return_value=456,
        ):
            window._retry_failed_draft()

        self.assertEqual(window._work_hwnd, 456)

    def test_retry_draft_is_noop_when_sending(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._sending = True
        window._retry_draft = "retry me"
        window._retry_target_hwnd = 321
        window._hide_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        window._retry_failed_draft()

        window._hide_feedback.assert_not_called()
        window._show_bar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
