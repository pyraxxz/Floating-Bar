import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.context import title_fingerprint
from floatingbar.transaction import TargetScope


class ContextOverlayTests(unittest.TestCase):
    def test_foreground_non_telegram_still_captures_selected_telegram_context(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.target.hwnd = 500
        window.target.select_for_send.return_value = 500
        window.target.scope.return_value = TargetScope(500, 900)
        window.injector = Mock()
        window._attempt_context = None
        window._result_q = queue.Queue()
        window._active_attempt_id = 1

        preflight = SimpleNamespace(
            ready=True,
            status="ready",
            hwnd=500,
            pid=900,
            submission_path="send-button",
            context_guard_available=True,
            reasons=(),
        )
        with patch("floatingbar.context_overlay.winapi.get_process_image_name", return_value=r"C:\\Telegram Desktop\\Telegram.exe"), patch(
            "floatingbar.context_overlay.winapi.get_window_pid", return_value=900
        ), patch(
            "floatingbar.context_overlay.winapi.get_window_title", return_value="Chat A - Telegram"
        ), patch(
            "floatingbar.context_overlay.run_preflight",
            return_value=preflight,
        ), patch("floatingbar.recovery_overlay.OrbRelayWindow._send_worker"):
            window._send_worker("hello", 0, 1)

        self.assertIsNotNone(window._attempt_context)
        self.assertEqual(window._attempt_context.title_fp, title_fingerprint("Chat A - Telegram"))
        window.injector.set_window_context.assert_called()

    def test_changed_context_is_returned_as_safe_failure(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window._result_q = queue.Queue()
        context = Mock()
        context.hwnd = 500
        context.matches.return_value = False
        window._attempt_context = context
        window._work_hwnd = 500

        preflight = SimpleNamespace(
            ready=True,
            status="ready",
            hwnd=500,
            pid=900,
            submission_path="send-button",
            context_guard_available=True,
            reasons=(),
        )
        with patch("floatingbar.context_overlay.run_preflight", return_value=preflight):
            window._send_worker("hello", 500, 3)

        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 3)
        self.assertIsNone(strategy)
        self.assertIn("changed", error)

    def test_blocked_preflight_stops_before_injector(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.injector = Mock()
        window._attempt_context = None
        window._result_q = queue.Queue()

        blocked = SimpleNamespace(
            ready=False,
            status="blocked",
            submission_path="unavailable",
            context_guard_available=False,
            reasons=("Telegram is minimized; text cannot be safely targeted.",),
        )
        with patch("floatingbar.context_overlay.run_preflight", return_value=blocked), patch(
            "floatingbar.context_overlay.winapi.get_window_pid", return_value=0
        ):
            window._send_worker("hello", 0, 7)

        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 7)
        self.assertIsNone(strategy)
        self.assertIn("minimized", error)
        window.injector.send.assert_not_called()

    def test_send_binds_to_exact_preflight_window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.target.select_for_send.return_value = 700
        window.target.scope.return_value = TargetScope(700, 900)
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = Mock()
        window._attempt_context.hwnd = 700
        window._attempt_context.matches.return_value = True
        window._work_hwnd = 111

        preflight = SimpleNamespace(
            ready=True,
            status="ready-with-degraded-context",
            hwnd=700,
            pid=900,
            submission_path="enter-fallback",
            context_guard_available=False,
            reasons=("generic title",),
        )
        with patch(
            "floatingbar.context_overlay.run_preflight",
            return_value=preflight,
        ), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ) as base_worker:
            window._send_worker("hello", 111, 9)

        self.assertEqual(window._work_hwnd, 700)
        window.target.select_for_send.assert_called_once_with(preferred_hwnd=700)
        self.assertEqual(window.target.scope.return_value, TargetScope(700, 900))
        base_worker.assert_called_once_with("hello", 700, 9)

    def test_preflight_result_becomes_lease_when_foreground_was_not_telegram(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.target.select_for_send.return_value = 700
        window.target.scope.return_value = TargetScope(700, 900)
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = None
        window._work_hwnd = 111

        context = Mock()
        context.hwnd = 700
        context.matches.return_value = True

        preflight = SimpleNamespace(
            ready=True,
            status="ready-with-degraded-context",
            hwnd=700,
            pid=900,
            submission_path="enter-fallback",
            context_guard_available=False,
            reasons=("generic title",),
        )
        with patch(
            "floatingbar.context_overlay.run_preflight",
            return_value=preflight,
        ), patch(
            "floatingbar.context_overlay.capture",
            return_value=context,
        ), patch(
            "floatingbar.context_overlay.OrbRelayWindow._is_telegram_window",
            return_value=True,
        ), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ) as base_worker:
            window._send_worker("hello", 111, 10)

        window.target.select_for_send.assert_called_once_with(preferred_hwnd=700)
        self.assertEqual(window._work_hwnd, 700)
        self.assertEqual(window._active_transaction.target, TargetScope(700, 900))
        base_worker.assert_called_once_with("hello", 700, 10)

    def test_fresh_preflight_context_overrides_stale_expanded_context(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.target.select_for_send.return_value = 700
        window.target.scope.return_value = TargetScope(700, 900)
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = Mock()
        window._attempt_context.hwnd = 700
        window._attempt_context.matches.return_value = False
        window._work_hwnd = 700

        fresh_context = Mock()
        fresh_context.hwnd = 700
        fresh_context.matches.return_value = True
        preflight = SimpleNamespace(
            ready=True,
            status="ready",
            hwnd=700,
            pid=900,
            submission_path="send-button",
            context_guard_available=True,
            context=fresh_context,
            reasons=(),
        )
        with patch(
            "floatingbar.context_overlay.run_preflight",
            return_value=preflight,
        ), patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_worker"
        ) as base_worker:
            window._send_worker("hello", 700, 11)

        self.assertIs(window._attempt_context, fresh_context)
        fresh_context.matches.assert_called_once_with()
        base_worker.assert_called_once_with("hello", 700, 11)

    def test_active_target_lease_releases_when_completion_raises(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.injector = Mock()
        window._active_attempt_id = 12
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 12
        window._active_transaction.context = Mock()
        window._attempt_context = window._active_transaction.context

        with patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_finished",
            side_effect=RuntimeError("completion bug"),
        ):
            with self.assertRaises(RuntimeError):
                window._send_finished(12, None, "error")

        window.target.release.assert_called_once_with()

    def test_stale_completion_never_releases_newer_attempt_lease(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.injector = Mock()
        window._active_attempt_id = 20
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 20
        window._active_transaction.context = Mock()
        window._attempt_context = window._active_transaction.context

        with patch("floatingbar.recovery_overlay.OrbRelayWindow._send_finished") as base_finished:
            window._send_finished(19, None, "old result")

        base_finished.assert_called_once_with(19, None, "old result")
        window.target.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
