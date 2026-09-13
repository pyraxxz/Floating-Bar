import io
import sys
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from tools.diagnose import _run_context_diagnostic


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom

    def width(self):
        return self.right - self.left


class _Item:
    def __init__(self, rect, selected, runtime_id, name, automation_id=""):
        self._rect = rect
        self._selected = selected
        self.element_info = SimpleNamespace(
            runtime_id=runtime_id,
            name=name,
            automation_id=automation_id,
        )

    def rectangle(self):
        return self._rect

    def is_selected(self):
        return self._selected


class _Window:
    def __init__(self, items):
        self._items = items

    def rectangle(self):
        return _Rect(0, 0, 1000, 800)

    def descendants(self, control_type=None):
        self.last_control_type = control_type
        return self._items


class _App:
    def __init__(self, window):
        self._window = window

    def window(self, handle):
        return self

    def wrapper_object(self):
        return self._window


class ContextDiagnosticTests(unittest.TestCase):
    def test_probe_reports_selected_structure_without_raw_names(self):
        window = _Window(
            [
                _Item(
                    _Rect(10, 100, 290, 160),
                    True,
                    (7, 8, 9),
                    "Private Chat Name",
                    "ChatRow42",
                ),
                _Item(
                    _Rect(700, 120, 960, 180),
                    True,
                    (10, 11, 12),
                    "Message Selection",
                ),
            ]
        )
        fake_pywinauto = SimpleNamespace(
            Application=lambda backend: _App(window),
        )

        output = io.StringIO()
        with patch.dict(sys.modules, {"pywinauto": fake_pywinauto}), patch(
            "tools.diagnose.winapi.get_window_pid", return_value=200
        ), patch("tools.diagnose.trace.path", return_value="trace.log"), redirect_stdout(output):
            status = _run_context_diagnostic(100)

        text = output.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("selected=True", text)
        self.assertIn("runtime_id=(7, 8, 9)", text)
        self.assertIn("automation_id='ChatRow42'", text)
        self.assertIn("name_fp=", text)
        self.assertNotIn("Private Chat Name", text)
        self.assertNotIn("Message Selection", text)
        self.assertIn("selected_left_pane_candidates=1", text)
        self.assertIn("unique selected left-pane ListItem", text)

    def test_probe_handles_missing_items_without_side_effects(self):
        window = _Window([])
        fake_pywinauto = SimpleNamespace(
            Application=lambda backend: _App(window),
        )

        output = io.StringIO()
        with patch.dict(sys.modules, {"pywinauto": fake_pywinauto}), patch(
            "tools.diagnose.winapi.get_window_pid", return_value=200
        ), redirect_stdout(output):
            status = _run_context_diagnostic(100)

        self.assertEqual(status, 0)
        self.assertIn("no candidate ListItem controls found", output.getvalue())


if __name__ == "__main__":
    unittest.main()
