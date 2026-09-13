import json
import unittest
from types import SimpleNamespace

from tools.diagnose import _preflight_payload


class DiagnoseJsonTests(unittest.TestCase):
    def test_preflight_payload_is_json_serializable_and_content_free(self):
        result = SimpleNamespace(
            status="ready",
            ready=True,
            hwnd=100,
            pid=200,
            minimized=False,
            scope_stable=True,
            focused_hwnd=101,
            focused_pid=200,
            compose_click=(20, 30),
            submission_path="send-button",
            send_name="Send",
            send_point=(80, 30),
            send_evidence_score=123.5,
            context_guard_available=True,
            context_stable=True,
            context=SimpleNamespace(compose_runtime_id=(7, 8, 9)),
            reasons=("example diagnostic note",),
        )

        payload = _preflight_payload(result)
        encoded = json.dumps(payload, sort_keys=True)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["status"], "ready")
        self.assertTrue(decoded["ready"])
        self.assertEqual(decoded["telegram_hwnd"], 100)
        self.assertEqual(decoded["pid"], 200)
        self.assertEqual(decoded["compose_click"], [20, 30])
        self.assertEqual(decoded["send_candidate"]["point"], [80, 30])
        self.assertEqual(decoded["send_candidate"]["evidence_score"], 123.5)
        self.assertTrue(decoded["compose_runtime_anchor_available"])
        self.assertNotIn("title", decoded)
        self.assertNotIn("message", decoded)
        self.assertNotIn("text", decoded)

    def test_preflight_payload_handles_missing_send_and_context(self):
        result = SimpleNamespace(
            status="ready-with-degraded-context",
            ready=True,
            hwnd=100,
            pid=200,
            minimized=False,
            scope_stable=True,
            focused_hwnd=0,
            focused_pid=0,
            compose_click=(20, 30),
            submission_path="enter-fallback",
            send_name="",
            send_point=None,
            send_evidence_score=0.0,
            context_guard_available=False,
            context_stable=False,
            context=None,
            reasons=("generic title",),
        )

        payload = _preflight_payload(result)

        self.assertIsNone(payload["send_candidate"])
        self.assertFalse(payload["context_guard_available"])
        self.assertFalse(payload["compose_runtime_anchor_available"])


if __name__ == "__main__":
    unittest.main()
