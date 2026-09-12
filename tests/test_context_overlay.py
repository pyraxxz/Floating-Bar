import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.context import WindowContext, title_fingerprint


class ContextOverlayTests(unittest.TestCase):
    def test_foreground_non_telegram_still_captures_selected_telegram_context(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.target.hwnd = 500
        window.target.select_for_send.return_value = 500
        window.injector = Mock()
        window._attempt_context = None
        window._result_q = queue.Queue()
        window._active_attempt_id = 1

        with patch("floatingbar.context_overlay.winapi.get_process_image_name", return_value=r"C:\\Telegram Desktop\\Telegram.exe"), patch(
            "floatingbar.context_overlay.winapi.get_window_pid", return_value=900
        ), patch(
            "floatingbar.context_overlay.winapi.get_window_title", return_value="Chat A - Telegram"
        ):
            window._send_worker("hello", 0, 1)

        self.assertIsNotNone(window._attempt_context)
        self.assertEqual(window._attempt_context.title_fp, title_fingerprint("Chat A - Telegram"))
        window.injector.set_window_context.assert_called()

    def test_changed_context_is_returned_as_safe_failure(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        context = Mock()
        context.matches.return_value = False
        window._attempt_context = context
        window._result_q = queue.Queue()

        window._send_worker("hello", 500, 3)

        attempt_id, strategy, error = window._result_q.get_nowait()
        self.assertEqual(attempt_id, 3)
        self.assertIsNone(strategy)
        self.assertIn("changed", error)


if __name__ == "__main__":
    unittest.main()
