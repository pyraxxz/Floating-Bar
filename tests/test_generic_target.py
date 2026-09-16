import unittest
from unittest.mock import patch

from floatingbar.control_candidates import InputCandidate
from floatingbar.generic_target import BackgroundTypingTarget, TargetProbe
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
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=999):
            self.assertFalse(self.target.available())

    def test_unavailable_when_top_level_window_is_hidden(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=False), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200):
            self.assertFalse(self.target.available())

    def test_unavailable_when_top_level_window_is_minimized(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200):
            self.assertFalse(self.target.available())

    def test_probe_is_content_free_and_reports_candidates(self):
        candidates = (
            InputCandidate(301, 200, "Edit", "Edit", 0, 0, 400, 30, True, True, True),
            InputCandidate(302, 200, "Edit", "Edit", 0, 40, 400, 80, False, True, True),
        )
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=301), \
             patch("floatingbar.generic_target.enumerate_input_candidates", return_value=candidates):
            probe = self.target.probe()

        self.assertIsInstance(probe, TargetProbe)
        self.assertEqual(probe.scope, TargetScope(100, 200))
        self.assertTrue(probe.available)
        self.assertEqual(probe.focused_hwnd, 301)
        self.assertEqual(probe.candidate_hwnds, (301, 302))
        self.assertEqual(probe.candidate_count, 2)

    def test_probe_fails_closed_when_target_is_unavailable(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=False):
            probe = self.target.probe()
        self.assertEqual(probe.scope, TargetScope(100, 200))
        self.assertFalse(probe.available)
        self.assertEqual(probe.focused_hwnd, 0)
        self.assertEqual(probe.candidate_hwnds, ())

    def test_send_posts_to_focused_child_inside_bound_process(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = self.target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(300, "hello")
        post_enter.assert_called_once_with(300, target=300)

    def test_send_rejects_focus_from_another_process_before_posting(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 999]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "outside the bound process"):
                self.target.send("hello")

        post_text.assert_not_called()

    def test_send_never_restores_or_foregrounds_target(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text"), \
             patch("floatingbar.generic_target.winapi.post_enter"), \
             patch("floatingbar.generic_target.winapi.ensure_restored") as ensure_restored, \
             patch("floatingbar.generic_target.winapi.set_foreground_window") as set_foreground:
            self.target.send("hello")

        ensure_restored.assert_not_called()
        set_foreground.assert_not_called()

    def test_send_rejects_whitespace_only_text(self):
        with self.assertRaises(ValueError):
            self.target.send("   ")


if __name__ == "__main__":
    unittest.main()
