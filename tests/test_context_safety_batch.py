import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.context import WindowContext, title_fingerprint
from floatingbar.preflight import run
from floatingbar.transaction import SendCandidate


class ContextSafetyBatchTests(unittest.TestCase):
    def _target(self):
        target = SimpleNamespace()
        target.select_for_send = lambda preferred_hwnd=0: 100
        target.scope = lambda: (100, 200)
        box = SimpleNamespace()
        box.element_info = SimpleNamespace(runtime_id=())
        target.compose_box = lambda: box
        target.compose_click_point = lambda value: (20, 30)
        target.send_button_click = lambda near_box=None: SendCandidate("Send", 80, 30, 123.5)
        return target

    def test_context_matches_fails_closed_when_window_probe_raises(self):
        context = WindowContext(100, 200, title_fingerprint("Chat A"))
        with patch(
            "floatingbar.context.winapi.get_window_pid",
            side_effect=RuntimeError("window disappeared"),
        ):
            self.assertFalse(context.matches())

    def test_context_matches_fails_closed_when_window_api_raises(self):
        context = WindowContext(100, 200, "", process_name="telegram.exe")
        with patch("floatingbar.context.winapi.get_window_pid", return_value=200), patch(
            "floatingbar.context.winapi.user32.IsWindow",
            side_effect=RuntimeError("api unavailable"),
        ):
            self.assertFalse(context.matches())

    def test_preflight_blocks_when_target_selection_raises(self):
        target = self._target()
        target.select_for_send = lambda preferred_hwnd=0: (_ for _ in ()).throw(
            RuntimeError("discovery failed")
        )

        result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(
            result.reasons,
            ("Telegram target could not be inspected safely.",),
        )

    def test_preflight_blocks_when_scope_inspection_raises(self):
        target = self._target()
        target.scope = lambda: (_ for _ in ()).throw(RuntimeError("scope failed"))

        result = run(target)

        self.assertFalse(result.ready)
        self.assertEqual(
            result.reasons,
            ("Telegram target scope could not be inspected safely.",),
        )

    def test_preflight_blocks_compose_inspection_failure_instead_of_raising(self):
        target = self._target()
        target.compose_box = lambda: (_ for _ in ()).throw(RuntimeError("uia failed"))
        context = WindowContext(100, 200, "")
        with patch("floatingbar.preflight.winapi.is_minimized", return_value=False), patch(
            "floatingbar.preflight.winapi.get_focused_hwnd", return_value=0
        ), patch("floatingbar.preflight.capture", return_value=context):
            result = run(target)

        self.assertFalse(result.ready)
        self.assertTrue(
            any("compose controls could not be inspected safely" in reason for reason in result.reasons)
        )


if __name__ == "__main__":
    unittest.main()
