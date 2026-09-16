import unittest
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.app_targets import target_for_adapter, target_mode_for
from floatingbar.terminal_target import TerminalTypingTarget


class AppTargetTests(unittest.TestCase):
    def test_terminal_factory_returns_dedicated_target(self):
        spec = adapter_for_process("wt.exe")
        target = target_for_adapter(spec)
        self.assertIsInstance(target, TerminalTypingTarget)
        self.assertEqual(target_mode_for(spec), "terminal-structured-focus")

    def test_unknown_factory_falls_back_to_generic_target(self):
        self.assertEqual(target_mode_for(None), "unsupported")
        target = target_for_adapter(None)
        self.assertEqual(type(target).__name__, "BackgroundTypingTarget")

    def test_terminal_send_requires_structural_candidate_for_focused_child(self):
        target = TerminalTypingTarget(100, 200)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch.object(target, "input_candidates", return_value=()), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "not a discovered editable target"):
                target.send("hello")
        post_text.assert_not_called()

    def test_terminal_send_allows_discovered_focused_child(self):
        target = TerminalTypingTarget(100, 200)
        candidate = type("Candidate", (), {"hwnd": 300})()
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch.object(target, "input_candidates", return_value=(candidate,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = target.send("hello")
        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(300, "hello")
        post_enter.assert_called_once_with(300, target=300)


if __name__ == "__main__":
    unittest.main()
