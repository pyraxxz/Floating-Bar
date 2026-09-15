import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.transaction import SendAttempt, SendCompletion, SendRequest, TargetScope
from floatingbar.transaction_coordinator import PreparedTransaction, TransactionRejected
from floatingbar.transaction_state import TransactionState


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
        window._active_lifecycle = None
        window._active_attempt_id = 0
        window._retry_draft = None
        window._retry_target_hwnd = 0
        window._sending = False
        window._state = "orb"
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

    def test_send_worker_uses_request_first_coordinator_and_prepared_target(self):
        window = self._window()
        prepared = self._prepared()
        window.coordinator.prepare_request.return_value = prepared
        request = SendRequest(12, "hello", 700)

        with patch.object(window, "_is_telegram_window", return_value=True), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker_request(request)

        window.coordinator.prepare_request.assert_called_once_with(
            request,
            preferred_hwnd=700,
        )
        self.assertEqual(window._active_transaction.target, TargetScope(700, 900))
        self.assertEqual(window._active_transaction.restore_hwnd, 321)
        self.assertEqual(window._work_hwnd, 700)
        self.assertEqual(window._active_lifecycle.state, TransactionState.SENDING)
        execute_attempt.assert_called_once_with("hello", 321, 12)

    def test_send_worker_preserves_nontelegram_foreground_for_restore(self):
        window = self._window()
        prepared = self._prepared(attempt_id=13, restore_hwnd=111)
        window.coordinator.prepare_request.return_value = prepared
        request = SendRequest(13, "hello", 111)

        with patch.object(window, "_is_telegram_window", return_value=False), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker_request(request)

        window.coordinator.prepare_request.assert_called_once_with(
            request,
            preferred_hwnd=0,
        )
        self.assertEqual(window._active_transaction.restore_hwnd, 111)
        self.assertEqual(window._active_lifecycle.state, TransactionState.SENDING)
        execute_attempt.assert_called_once_with("hello", 111, 13)

    def test_blocked_coordinator_marks_lifecycle_rejected(self):
        window = self._window()
        window.coordinator.prepare_request.side_effect = TransactionRejected("blocked")

        request = SendRequest(14, "hello", 700)
        window._send_worker_request(request)

        self.assertIsNone(window._active_transaction)
        self.assertEqual(window._active_lifecycle.state, TransactionState.REJECTED)
        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 14)
        self.assertIsNone(completion.strategy)
        self.assertEqual(completion.error, "blocked")


if __name__ == "__main__":
    unittest.main()
