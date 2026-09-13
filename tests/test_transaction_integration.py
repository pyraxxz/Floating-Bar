import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow


class TransactionIntegrationTests(unittest.TestCase):
    def _window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = Mock()
        window._attempt_context.hwnd = 700
        window._attempt_context.matches.return_value = True
        window._active_transaction = None
        window._work_hwnd = 700
        return window

    def test_send_worker_binds_exact_preflight_target_into_transaction(self):
        window = self._window()
        preflight = SimpleNamespace(
            ready=True,
            status="ready",
            submission_path="send-button",
            context_guard_available=True,
            hwnd=700,
            pid=900,
            reasons=(),
        )

        with patch("floatingbar.context_overlay.run_preflight", return_value=preflight), patch.object(
            window, "_is_telegram_window", return_value=True
        ), patch.object(window, "_capture_target_context"), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ) as base_worker:
            window._send_worker("hello", 700, 12)

        attempt = window._active_transaction
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.attempt_id, 12)
        self.assertEqual(attempt.text, "hello")
        self.assertEqual(attempt.target.hwnd, 700)
        self.assertEqual(attempt.target.pid, 900)
        self.assertIs(attempt.context, window._attempt_context)
        base_worker.assert_called_once_with("hello", 700, 12)

    def test_blocked_preflight_creates_no_transaction(self):
        window = self._window()
        window._active_transaction = None
        preflight = SimpleNamespace(
            ready=False,
            status="blocked",
            submission_path="unavailable",
            context_guard_available=False,
            hwnd=700,
            pid=900,
            reasons=("scope changed",),
        )

        with patch("floatingbar.context_overlay.run_preflight", return_value=preflight), patch.object(
            window, "_is_telegram_window", return_value=True
        ):
            window._send_worker("hello", 700, 13)

        self.assertIsNone(window._active_transaction)
        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 13)
        self.assertIsNone(strategy)
        self.assertIn("scope changed", error)


if __name__ == "__main__":
    unittest.main()
