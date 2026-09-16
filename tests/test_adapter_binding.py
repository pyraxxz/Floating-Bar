import unittest
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget
from floatingbar.terminal_target import TerminalTypingTarget


class _Candidate:
    def __init__(self, hwnd=401, pid=200):
        self.hwnd = hwnd
        self.pid = pid
        self.control_type = "Edit"
        self.class_name = "RichEdit"
        self.width = 600
        self.height = 40
        self.left = 20
        self.top = 700
        self.right = 620
        self.bottom = 740
        self.focused = False

    @property
    def area(self):
        return self.width * self.height

    @property
    def center_y(self):
        return self.top + self.height // 2

    @property
    def is_likely_composer_shape(self):
        return True


class AdapterBindingTests(unittest.TestCase):
    def _runtime_patches(self):
        return (
            patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True),
            patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True),
            patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200),
            patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=999),
        )

    def test_chat_target_uses_bound_adapter_submission_policy(self):
        spec = adapter_for_process("discord.exe")
        target = ChatComposerTarget()
        target.bind(100, 200, spec=spec)
        candidate = _Candidate()
        patches = self._runtime_patches()
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(target, "input_candidates", return_value=(candidate,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            result = target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(401, "hello")
        post_enter.assert_called_once_with(401, target=401)

    def test_terminal_target_rejects_unsupported_submit_policy_before_enter_or_typing(self):
        class Spec:
            submit_mode = "click"

        target = TerminalTypingTarget()
        target.bind(100, 200, spec=Spec())
        candidate = _Candidate(402)
        patches = self._runtime_patches()
        with patches[0], patches[1], patches[2], patches[3], \
             patch.object(target, "input_candidates", return_value=(candidate,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            with self.assertRaisesRegex(RuntimeError, "unsupported"):
                target.send("dir")

        post_text.assert_not_called()
        post_enter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
