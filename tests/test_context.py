import unittest
from unittest.mock import patch

from floatingbar.context import WindowContext, capture, title_fingerprint


class ContextTests(unittest.TestCase):
    def test_title_fingerprint_is_stable_and_nonempty(self):
        first = title_fingerprint("Example Chat - Telegram")
        second = title_fingerprint("Example Chat - Telegram")
        self.assertTrue(first)
        self.assertEqual(first, second)
        self.assertNotEqual(first, "Example Chat - Telegram")

    def test_title_fingerprint_changes_when_context_changes(self):
        self.assertNotEqual(
            title_fingerprint("First Chat"),
            title_fingerprint("Second Chat"),
        )

    def test_empty_title_has_no_fingerprint(self):
        self.assertEqual(title_fingerprint(""), "")
        self.assertEqual(title_fingerprint("   "), "")

    def test_window_context_matches_same_hwnd_pid_and_title(self):
        context = WindowContext(100, 200, title_fingerprint("Chat A"))
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Chat A"
        ), patch("floatingbar.context.winapi.user32.IsWindow", return_value=True):
            self.assertTrue(context.matches())

    def test_window_context_rejects_changed_title(self):
        context = WindowContext(100, 200, title_fingerprint("Chat A"))
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Chat B"
        ), patch("floatingbar.context.winapi.user32.IsWindow", return_value=True):
            self.assertFalse(context.matches())

    def test_window_context_rejects_changed_pid(self):
        context = WindowContext(100, 200, title_fingerprint("Chat A"))
        with patch("floatingbar.context.winapi.get_window_pid", return_value=201), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Chat A"
        ), patch("floatingbar.context.winapi.user32.IsWindow", return_value=True):
            self.assertFalse(context.matches())

    def test_capture_uses_title_only_to_create_fingerprint(self):
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Chat A"
        ):
            context = capture(100)

        self.assertEqual(context.hwnd, 100)
        self.assertEqual(context.pid, 200)
        self.assertEqual(context.title_fp, title_fingerprint("Chat A"))


if __name__ == "__main__":
    unittest.main()
