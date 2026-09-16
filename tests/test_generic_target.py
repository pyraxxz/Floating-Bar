import unittest
from unittest.mock import patch

from floatingbar.generic_target import BackgroundTypingTarget
from floatingbar.transaction import TargetScope


class BackgroundTypingTargetTests(unittest.TestCase):
    def setUp(self):
        self.target = BackgroundTypingTarget(100, 200)

    def test_exact_scope_is_immutable_until_rebind(self):
        self.assertEqual(self.target.scope(), TargetScope(100, 200))
        self.target.bind(101, 201)
        self.assertEqual(self.target.scope(), TargetScope(101, 201))

    def test_unavailable_when_top_level_window_pid_changes(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=999):
            self.assertFalse(self.target.available())

    def test_send_posts_to_focused_child_inside_bound_process(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = self.target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(300, "hello")
        post_enter.assert_called_once_with(300)

    def test_send_rejects_focus_from_another_process_before_posting(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 999]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "outside the bound process"):
                self.target.send("hello")

        post_text.assert_not_called()

    def test_send_rejects_whitespace_only_text(self):
        with self.assertRaises(ValueError):
            self.target.send("   ")


if __name__ == "__main__":
    unittest.main()
