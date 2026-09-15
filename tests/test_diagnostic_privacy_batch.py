import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from tools.diagnose import _window_context_summary


class DiagnosticPrivacyBatchTests(unittest.TestCase):
    def test_window_context_summary_never_returns_raw_title(self):
        with patch(
            "tools.diagnose.winapi.get_window_title",
            return_value="Private Chat Name - Telegram",
        ):
            summary = _window_context_summary(100)

        self.assertTrue(summary["title_present"])
        self.assertTrue(summary["title_fingerprint"])
        self.assertNotIn("Private Chat Name", repr(summary))
        self.assertNotEqual(summary["title_fingerprint"], "Private Chat Name - Telegram")

    def test_window_context_summary_marks_missing_title_without_exposing_content(self):
        with patch("tools.diagnose.winapi.get_window_title", return_value=""):
            summary = _window_context_summary(100)

        self.assertFalse(summary["title_present"])
        self.assertEqual(summary["title_fingerprint"], "")

    def test_summary_output_has_no_raw_title(self):
        from tools import diagnose

        class _WindowTarget:
            pass

        fake_target = _WindowTarget()
        with patch("tools.diagnose.winapi.get_window_title", return_value="Private Chat Name"), patch(
            "tools.diagnose.winapi.get_window_pid", return_value=200
        ), patch("tools.diagnose.winapi.get_focused_hwnd", return_value=0), redirect_stdout(io.StringIO()):
            summary = diagnose._window_context_summary(100)

        self.assertNotIn("Private Chat Name", repr(summary))


if __name__ == "__main__":
    unittest.main()
