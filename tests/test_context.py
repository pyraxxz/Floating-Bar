import unittest
from unittest.mock import patch

from floatingbar.context import (
    WindowContext,
    capture,
    title_fingerprint,
)


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

    def test_generic_telegram_title_has_no_fingerprint(self):
        self.assertEqual(title_fingerprint("Telegram"), "")
        self.assertEqual(title_fingerprint("Telegram Desktop"), "")

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

    def test_window_context_matches_process_identity(self):
        context = WindowContext(
            100,
            200,
            "",
            process_name="telegram.exe",
        )
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.user32.IsWindow", return_value=True
        ), patch(
            "floatingbar.context.winapi.get_process_image_name",
            return_value="C:\\Apps\\Telegram\\Telegram.exe",
        ):
            self.assertTrue(context.matches())
        self.assertFalse(context.guard_available)

    def test_window_context_rejects_changed_process_identity(self):
        context = WindowContext(
            100,
            200,
            "",
            process_name="telegram.exe",
        )
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.user32.IsWindow", return_value=True
        ), patch(
            "floatingbar.context.winapi.get_process_image_name",
            return_value="C:\\Apps\\Other\\other.exe",
        ):
            self.assertFalse(context.matches())

    def test_window_context_rejects_changed_compose_runtime_id(self):
        context = WindowContext(
            100,
            200,
            "",
            compose_runtime_id=(7, 8, 9),
        )
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.user32.IsWindow", return_value=True
        ), patch(
            "floatingbar.context.compose_runtime_id_present", return_value=False
        ):
            self.assertFalse(context.matches())

    def test_window_context_accepts_matching_compose_runtime_id_without_title(self):
        context = WindowContext(
            100,
            200,
            "",
            compose_runtime_id=(7, 8, 9),
        )
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.user32.IsWindow", return_value=True
        ), patch(
            "floatingbar.context.compose_runtime_id_present", return_value=True
        ):
            self.assertTrue(context.matches())
        self.assertTrue(context.guard_available)

    def test_capture_retains_only_non_content_context_anchors(self):
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Chat A"
        ), patch(
            "floatingbar.context.winapi.get_process_image_name",
            return_value="C:\\Apps\\Telegram\\Telegram.exe",
        ):
            context = capture(100, compose_runtime_id=(7, 8, 9))

        self.assertEqual(context.hwnd, 100)
        self.assertEqual(context.pid, 200)
        self.assertEqual(context.title_fp, title_fingerprint("Chat A"))
        self.assertEqual(context.compose_runtime_id, (7, 8, 9))
        self.assertEqual(context.process_name, "telegram.exe")
        self.assertTrue(context.guard_available)

    def test_capture_generic_title_can_still_have_structural_guard(self):
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.get_window_title", return_value="Telegram"
        ), patch(
            "floatingbar.context.winapi.get_process_image_name",
            return_value="C:\\Apps\\Telegram\\Telegram.exe",
        ):
            context = capture(100, compose_runtime_id=(7, 8, 9))

        self.assertEqual(context.title_fp, "")
        self.assertEqual(context.process_name, "telegram.exe")
        self.assertTrue(context.guard_available)


if __name__ == "__main__":
    unittest.main()
