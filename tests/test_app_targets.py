import unittest
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.app_targets import target_for_adapter, target_mode_for
from floatingbar.chat_composer_target import ChatComposerTarget
from floatingbar.terminal_target import TerminalTypingTarget


class _Candidate:
    def __init__(self, hwnd, control_type="Edit", width=100, height=20, focused=False):
        self.hwnd = hwnd
        self.pid = 200
        self.control_type = control_type
        self.width = width
        self.height = height
        self.focused = focused

    @property
    def is_likely_composer_shape(self):
        return self.width >= 180 and self.height >= 24


class AppTargetTests(unittest.TestCase):
    def test_terminal_factory_returns_dedicated_target(self):
        spec = adapter_for_process("wt.exe")
        target = target_for_adapter(spec)
        self.assertIsInstance(target, TerminalTypingTarget)
        self.assertEqual(target_mode_for(spec), "terminal-structured-focus")

    def test_chat_apps_use_composer_target(self):
        for process in ("whatsapp.exe", "discord.exe", "slack.exe", "teams.exe"):
            with self.subTest(process=process):
                spec = adapter_for_process(process)
                self.assertIsInstance(target_for_adapter(spec), ChatComposerTarget)
                self.assertEqual(target_mode_for(spec), "chat-structured-focus")

    def test_unknown_factory_falls_back_to_generic_target(self):
        self.assertEqual(target_mode_for(None), "unsupported")
        target = target_for_adapter(None)
        self.assertEqual(type(target).__name__, "BackgroundTypingTarget")

    def test_chat_send_prefers_composer_shape_over_focused_search_field(self):
        target = ChatComposerTarget(100, 200)
        search = _Candidate(300, width=120, height=20, focused=True)
        composer = _Candidate(400, width=500, height=42, focused=False)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch.object(target, "input_candidates", return_value=(search, composer)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(400, "hello")
        post_enter.assert_called_once_with(400, target=400)

    def test_chat_send_requires_structural_candidate_for_focused_child(self):
        target = ChatComposerTarget(100, 200)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch.object(target, "input_candidates", return_value=()), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "not a discovered editable composer"):
                target.send("hello")
        post_text.assert_not_called()

    def test_chat_send_allows_discovered_edit_control(self):
        candidate = _Candidate(300, width=500, height=42, focused=True)
        target = ChatComposerTarget(100, 200)
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

    def test_chat_send_rejects_non_edit_role(self):
        target = ChatComposerTarget(100, 200)
        candidate = _Candidate(300, control_type="Button")
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch.object(target, "input_candidates", return_value=(candidate,)):
            with self.assertRaisesRegex(RuntimeError, "not a discovered editable composer"):
                target.send("hello")


if __name__ == "__main__":
    unittest.main()
