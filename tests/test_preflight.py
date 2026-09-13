import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.preflight import run
from floatingbar.transaction import SendCandidate


class PreflightTests(unittest.TestCase):
    def _target(
        self,
        hwnd=100,
        pid=200,
        compose_point=(20, 30),
        send=SendCandidate("Send", 80, 30, 123.5),
    ):
        target = SimpleNamespace()
        target.select_for_send = lambda preferred_hwnd=0: hwnd
        target.hwnd = hwnd
        target.scope = lambda: (hwnd, pid)
        box = SimpleNamespace()
        box.rectangle = lambda: SimpleNamespace(left=10, top=20, right=220, bottom=60)
        target.compose_box = lambda: box
        target.compose_click_point = lambda value: compose_point
        target.send_button_click = lambda near_box=None: send
        return target

    def test_ready_preflight_requires_compose_scope_and_non_minimized(self):
        target = self._target()
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch(
            "floatingbar.preflight.winapi.get_window_pid", return_value=200
        ), patch(
            "floatingbar.preflight.winapi.get_window_title", return_value="Chat A - Telegram"
        ), patch(
            "floatingbar.preflight.winapi.user32.IsWindow", return_value=True
        ):
            result = run(target)

        self.assertTrue(result.ready)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.hwnd, 100)
        self.assertEqual(result.pid, 200)
        self.assertEqual(result.compose_click, (20, 30))
        self.assertTrue(result.button_available)
        self.assertEqual(result.send_name, "Send")
        self.assertEqual(result.send_point, (80, 30))
        self.assertEqual(result.send_evidence_score, 123.5)
        self.assertEqual(result.submission_path, "send-button")
        self.assertTrue(result.scope_stable)
        self.assertTrue(result.context_guard_available)
        self.assertTrue(result.context_stable)

    def test_preflight_is_side_effect_free(self):
        target = self._target()
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch(
            "floatingbar.preflight.winapi.get_window_pid", return_value=200
        ), patch(
            "floatingbar.preflight.winapi.get_window_title", return_value="Chat A - Telegram"
        ), patch(
            "floatingbar.preflight.winapi.user32.IsWindow", return_value=True
        ), patch("floatingbar.preflight.winapi.post_click") as post_click, patch(
            "floatingbar.preflight.winapi.post_enter"
        ) as post_enter, patch(
            "floatingbar.preflight.winapi.set_foreground_window"
        ) as set_foreground, patch(
            "floatingbar.preflight.winapi.ensure_restored"
        ) as ensure_restored:
            result = run(target)

        self.assertTrue(result.ready)
        post_click.assert_not_called()
        post_enter.assert_not_called()
        set_foreground.assert_not_called()
        ensure_restored.assert_not_called()

    def test_minimized_preflight_is_not_ready(self):
        target = self._target()
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=True), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch("floatingbar.preflight.winapi.get_window_pid", return_value=200
        ):
            result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertTrue(any("minimized" in reason for reason in result.reasons))

    def test_missing_send_button_is_warning_but_not_hard_failure(self):
        target = self._target(send=None)
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch(
            "floatingbar.preflight.winapi.get_window_pid", return_value=200
        ), patch(
            "floatingbar.preflight.winapi.get_window_title", return_value="Chat A - Telegram"
        ), patch(
            "floatingbar.preflight.winapi.user32.IsWindow", return_value=True
        ):
            result = run(target)

        self.assertTrue(result.ready)
        self.assertEqual(result.submission_path, "enter-fallback")
        self.assertEqual(result.send_evidence_score, 0.0)
        self.assertTrue(result.context_guard_available)
        self.assertTrue(any("Enter fallback" in reason for reason in result.reasons))

    def test_generic_telegram_title_degrades_context_but_does_not_block(self):
        target = self._target()
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch(
            "floatingbar.preflight.winapi.get_window_pid", return_value=200
        ), patch(
            "floatingbar.preflight.winapi.get_window_title", return_value="Telegram"
        ), patch(
            "floatingbar.preflight.winapi.user32.IsWindow", return_value=True
        ):
            result = run(target)

        self.assertTrue(result.ready)
        self.assertEqual(result.status, "ready-with-degraded-context")
        self.assertFalse(result.context_guard_available)
        self.assertFalse(result.context_stable)

    def test_context_title_change_is_blocking(self):
        target = self._target()
        titles = iter(["Chat A - Telegram", "Chat B - Telegram"])
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch(
            "floatingbar.preflight.winapi.get_window_pid", return_value=200
        ), patch(
            "floatingbar.preflight.winapi.get_window_title", side_effect=lambda hwnd: next(titles)
        ), patch(
            "floatingbar.preflight.winapi.user32.IsWindow", return_value=True
        ):
            result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.context_stable)
        self.assertTrue(any("context changed" in reason for reason in result.reasons))

    def test_scope_change_makes_preflight_not_ready(self):
        target = self._target()
        calls = [(100, 200), (101, 200)]
        target.scope = lambda: calls.pop(0)
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=101
        ), patch("floatingbar.preflight.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.preflight.winapi.get_window_title", return_value="Chat A - Telegram"
        ), patch("floatingbar.preflight.winapi.user32.IsWindow", return_value=True):
            result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.scope_stable)
        self.assertTrue(any("scope changed" in reason for reason in result.reasons))

    def test_missing_telegram_is_not_ready(self):
        target = self._target(hwnd=0)
        target.scope = lambda: (0, 0)
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=0
        ):
            result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reasons, ("Telegram Desktop was not found.",))


if __name__ == "__main__":
    unittest.main()
