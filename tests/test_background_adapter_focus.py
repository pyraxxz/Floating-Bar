import unittest
from unittest.mock import patch

from floatingbar.chat_composer_target import ChatComposerTarget
from floatingbar.terminal_target import TerminalTypingTarget


class _Candidate:
    def __init__(self, hwnd, width=500, height=40, pid=200):
        self.hwnd = hwnd
        self.pid = pid
        self.control_type = "Edit"
        self.width = width
        self.height = height
        self.left = 20
        self.top = 700
        self.right = self.left + width
        self.bottom = self.top + height

    @property
    def area(self):
        return self.width * self.height

    @property
    def center_y(self):
        return self.top + self.height // 2

    @property
    def is_likely_composer_shape(self):
        return self.width >= 180 and self.height >= 24


class BackgroundAdapterFocusTests(unittest.TestCase):
    def _patch_runtime(self, target):
        return (
            patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True),
            patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True),
            patch("floatingbar.generic_target.winapi.is_minimized", return_value=False),
            patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200),
            patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=999),
        )

    def test_chat_composer_does_not_require_target_to_be_focused(self):
        target = ChatComposerTarget(100, 200)
        composer = _Candidate(401)
        patches = self._patch_runtime(target)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patch.object(target, "input_candidates", return_value=(composer,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = target.send("background reply")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(401, "background reply")
        post_enter.assert_called_once_with(401, target=401)

    def test_terminal_does_not_require_target_to_be_focused(self):
        target = TerminalTypingTarget(100, 200)
        console = _Candidate(402, width=700)
        patches = self._patch_runtime(target)
        with patches[0], patches[1], patches[2], patches[3], patches[4], \
             patch.object(target, "input_candidates", return_value=(console,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = target.send("echo hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(402, "echo hello")
        post_enter.assert_called_once_with(402, target=402)


if __name__ == "__main__":
    unittest.main()
