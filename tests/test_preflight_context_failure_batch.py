import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.context import WindowContext, title_fingerprint
from floatingbar.preflight import PreflightResult, run
from floatingbar.transaction import SendCandidate


class PreflightContextFailureBatchTests(unittest.TestCase):
    def _target(self):
        target = SimpleNamespace()
        target.select_for_send = lambda preferred_hwnd=0: 100
        target.hwnd = 100
        target.scope = lambda: (100, 200)
        box = SimpleNamespace()
        box.element_info = SimpleNamespace(runtime_id=(7, 8, 9))
        box.rectangle = lambda: SimpleNamespace(left=10, top=20, right=220, bottom=60)
        target.compose_box = lambda: box
        target.compose_click_point = lambda value: (20, 30)
        target.send_button_click = lambda near_box=None: SendCandidate("Send", 80, 30, 123.5)
        return target

    def _stable_windows(self):
        return [
            patch("floatingbar.preflight.winapi.is_minimized", return_value=False),
            patch("floatingbar.preflight.winapi.get_focused_hwnd", return_value=101),
            patch("floatingbar.preflight.winapi.get_window_pid", return_value=200),
            patch("floatingbar.preflight.winapi.user32.IsWindow", return_value=True),
        ]

    def test_initial_context_inspection_failure_blocks_instead_of_continuing(self):
        target = self._target()
        final = WindowContext(
            100,
            200,
            title_fingerprint("Chat A - Telegram"),
            compose_runtime_id=(7, 8, 9),
        )
        with patch("floatingbar.preflight.capture", side_effect=[RuntimeError("initial uia failure"), final]):
            patches = self._stable_windows()
            for item in patches:
                item.start()
            try:
                result = run(target)
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.context_protection, "blocked")
        self.assertTrue(
            any("before preflight" in reason for reason in result.reasons)
        )

    def test_final_context_inspection_failure_blocks_instead_of_degrading(self):
        target = self._target()
        initial = WindowContext(
            100,
            200,
            title_fingerprint("Chat A - Telegram"),
            compose_runtime_id=(7, 8, 9),
        )
        with patch("floatingbar.preflight.capture", side_effect=[initial, RuntimeError("uia failure")]):
            patches = self._stable_windows()
            for item in patches:
                item.start()
            try:
                result = run(target)
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertFalse(result.ready)
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.context_protection, "blocked")
        self.assertFalse(result.context_guard_available)
        self.assertFalse(result.context_stable)
        self.assertTrue(
            any("context could not be inspected safely" in reason for reason in result.reasons)
        )

    def test_generic_context_without_anchors_remains_supported_degraded_state(self):
        target = self._target()
        context = WindowContext(100, 200, "")
        with patch("floatingbar.preflight.capture", side_effect=[context, context]):
            patches = self._stable_windows()
            for item in patches:
                item.start()
            try:
                result = run(target)
            finally:
                for item in reversed(patches):
                    item.stop()

        self.assertTrue(result.ready)
        self.assertEqual(result.status, "ready-with-degraded-context")
        self.assertEqual(result.context_protection, "degraded")
        self.assertIsNotNone(result.context)
        self.assertFalse(result.context_guard_available)
        self.assertFalse(result.context_stable)

    def test_guarded_context_reports_guarded_protection(self):
        result = PreflightResult(
            ready=True,
            reasons=(),
            context_guard_available=True,
            context_stable=True,
        )
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.context_protection, "guarded")

    def test_blocked_json_shape_stays_content_free(self):
        result = PreflightResult(
            ready=False,
            reasons=("Telegram conversation context could not be inspected safely.",),
        )
        payload = {
            "schema_version": 1,
            "status": result.status,
            "context_protection": result.context_protection,
            "reasons": list(result.reasons),
        }
        encoded = json.dumps(payload, sort_keys=True)
        self.assertIn('"schema_version": 1', encoded)
        self.assertNotIn("Chat A", encoded)
        self.assertNotIn("message", encoded.lower())


if __name__ == "__main__":
    unittest.main()
