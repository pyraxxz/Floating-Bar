import unittest
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget
from floatingbar.terminal_target import TerminalTypingTarget


class _Candidate:
    def __init__(self, hwnd, width=500, height=40, pid=200):
        self.hwnd = hwnd
        self.pid = pid
        self.control_type = "Edit"
        self.focused = False
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
        target.bind(100, 200, spec=adapter_for_process("whatsapp.exe"))
        composer = _Candidate(401)
        patches = self._patch_runtime(target)
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch.object(target, "input_candidates", return_value=(composer,)),
            patch.object(target, "_verification_target", return_value=401),
            patch.object(target, "_composer_value_length", return_value=0),
            patch.object(target, "_wait_for_length", side_effect=[True, True]),
            patch("floatingbar.generic_target.winapi.post_text") as post_text,
            patch("floatingbar.generic_target.winapi.post_enter") as post_enter,
        ):
            result = target.send("background reply")

        self.assertEqual(result, "posted-enter (VERIFIED)")
        post_text.assert_called_once_with(401, "background reply", expected_pid=200, expected_process_start=None)
        post_enter.assert_called_once_with(401, target=401, expected_pid=200, expected_process_start=None)

    def test_chat_prefers_composer_shaped_control_over_focused_search_field(self):
        target = ChatComposerTarget(100, 200)
        target.bind(100, 200, spec=adapter_for_process("whatsapp.exe"))
        focused_search = _Candidate(402, width=120, height=20)
        composer = _Candidate(403, width=600, height=40)
        patches = (
            patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True),
            patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True),
            patch("floatingbar.generic_target.winapi.is_minimized", return_value=False),
            patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200),
            patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=402),
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patch.object(target, "input_candidates", return_value=(focused_search, composer)),
            patch.object(target, "_verification_target", return_value=403),
            patch.object(target, "_composer_value_length", return_value=0),
            patch.object(target, "_wait_for_length", side_effect=[True, True]),
            patch("floatingbar.generic_target.winapi.post_text") as post_text,
            patch("floatingbar.generic_target.winapi.post_enter") as post_enter,
        ):
            result = target.send("background reply")

        self.assertEqual(result, "posted-enter (VERIFIED)")
        post_text.assert_called_once_with(403, "background reply", expected_pid=200, expected_process_start=None)
        post_enter.assert_called_once_with(403, target=403, expected_pid=200, expected_process_start=None)

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
        post_text.assert_called_once_with(402, "echo hello", expected_pid=200, expected_process_start=None)
        post_enter.assert_called_once_with(402, target=402, expected_pid=200, expected_process_start=None)


if __name__ == "__main__":
    unittest.main()
