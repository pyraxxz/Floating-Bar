import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.transaction import SendAttempt, TargetScope
from floatingbar.transaction_coordinator import PreparedTransaction, TransactionRejected


class TransactionIntegrationTests(unittest.TestCase):
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

    def _prepared(self, attempt_id=12, restore_hwnd=321):
        context = Mock()
        context.hwnd = 700
        attempt = SendAttempt(
            attempt_id=attempt_id,
            text="hello",
            target=TargetScope(700, 900),
            restore_hwnd=restore_hwnd,
            context=context,
        )
        return PreparedTransaction(attempt=attempt, preflight=Mock())

    def test_send_worker_uses_coordinator_attempt_target(self):
        window = self._window()
        prepared = self._prepared()
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=True), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker("hello", 700, 12)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=12,
            preferred_hwnd=700,
            restore_hwnd=700,
        )
        self.assertEqual(window._active_transaction.target, TargetScope(700, 900))
        self.assertEqual(window._active_transaction.restore_hwnd, 321)
        self.assertEqual(window._work_hwnd, 700)
        execute_attempt.assert_called_once_with("hello", 321, 12)

    def test_send_worker_preserves_nontelegram_foreground_for_restore(self):
        window = self._window()
        prepared = self._prepared(attempt_id=13, restore_hwnd=111)
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=False), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker("hello", 111, 13)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=13,
            preferred_hwnd=0,
            restore_hwnd=111,
        )
        self.assertEqual(window._active_transaction.restore_hwnd, 111)
        execute_attempt.assert_called_once_with("hello", 111, 13)

    def test_blocked_coordinator_creates_no_active_attempt(self):
        window = self._window()
        window.coordinator.prepare.side_effect = TransactionRejected("blocked")

        window._send_worker("hello", 700, 14)

        self.assertIsNone(window._active_transaction)
        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 14)
        self.assertIsNone(strategy)
        self.assertEqual(error, "blocked")


if __name__ == "__main__":
    unittest.main()
