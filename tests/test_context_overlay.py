import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.transaction import SendAttempt, TargetScope
from floatingbar.transaction_coordinator import PreparedTransaction, TransactionRejected


class ContextOverlayTests(unittest.TestCase):
    def _window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.coordinator = Mock()
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = None
        window._retry_context = None
        window._active_transaction = None
        window._active_attempt_id = 0
        window._work_hwnd = 0
        return window

    def _prepared(self, attempt_id=7, restore_hwnd=111, context=None):
        context = context or Mock()
        context.hwnd = 700
        attempt = SendAttempt(
            attempt_id=attempt_id,
            text="hello",
            target=TargetScope(700, 900),
            restore_hwnd=restore_hwnd,
            context=context,
        )
        return PreparedTransaction(
            attempt=attempt,
            preflight=Mock(),
        )

    def test_send_worker_uses_coordinator_and_preserves_restore_hwnd(self):
        window = self._window()
        prepared = self._prepared(restore_hwnd=111)
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=False), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ) as base_worker:
            window._send_worker("hello", 111, 7)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=7,
            preferred_hwnd=0,
            restore_hwnd=111,
        )
        self.assertIs(window._active_transaction, prepared.attempt)
        self.assertEqual(window._work_hwnd, 700)
        self.assertIs(window._attempt_context, prepared.attempt.context)
        window.injector.set_window_context.assert_called_once_with(prepared.attempt.context)
        base_worker.assert_called_once_with("hello", 700, 7)

    def test_send_worker_passes_telegram_foreground_as_exact_preference(self):
        window = self._window()
        prepared = self._prepared(restore_hwnd=700)
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=True), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ):
            window._send_worker("hello", 700, 8)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=8,
            preferred_hwnd=700,
            restore_hwnd=700,
        )

    def test_transaction_rejection_is_returned_as_safe_failure(self):
        window = self._window()
        window.coordinator.prepare.side_effect = TransactionRejected("blocked")

        window._send_worker("hello", 111, 9)

        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 9)
        self.assertIsNone(strategy)
        self.assertEqual(error, "blocked")

    def test_unexpected_coordinator_failure_is_returned_as_safe_failure(self):
        window = self._window()
        window.coordinator.prepare.side_effect = RuntimeError("unexpected")

        window._send_worker("hello", 111, 10)

        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 10)
        self.assertIsNone(strategy)
        self.assertIn("unexpected", error)

    def test_active_target_lease_releases_when_completion_raises(self):
        window = self._window()
        window._active_attempt_id = 12
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 12
        window._active_transaction.context = Mock()

        with patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_finished",
            side_effect=RuntimeError("completion bug"),
        ):
            with self.assertRaises(RuntimeError):
                window._send_finished(12, None, "error")

        window.target.release.assert_called_once_with()

    def test_stale_completion_never_releases_newer_attempt_lease(self):
        window = self._window()
        window._active_attempt_id = 20
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 20
        window._active_transaction.context = Mock()

        with patch("floatingbar.recovery_overlay.OrbRelayWindow._send_finished") as base_finished:
            window._send_finished(19, None, "old result")

        base_finished.assert_called_once_with(19, None, "old result")
        window.target.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
