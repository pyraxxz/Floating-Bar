import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.context import _selected_chat_anchor, title_fingerprint


class _Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class _Item:
    def __init__(self, rect, selected, runtime_id=(), name="", automation_id=""):
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


class ChatAnchorBatchTests(unittest.TestCase):
    def _window(self, items):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.return_value = items
        return window

    def _app_patch(self, window):
        application = Mock()
        application.return_value.connect.return_value.window.return_value.wrapper_object.return_value = window
        fake_pywinauto = SimpleNamespace(Application=application)
        return patch.dict(sys.modules, {"pywinauto": fake_pywinauto})

    def test_unique_selected_left_chat_exposes_runtime_and_name_anchors(self):
        item = _Item(
            _Rect(20, 100, 420, 180),
            True,
            runtime_id=(1, 2, 3),
            name="Private Chat",
            automation_id="chat-row-17",
        )
        with self._app_patch(self._window([item])):
            result = _selected_chat_anchor(123)

        self.assertEqual(result[0], (1, 2, 3))
        self.assertEqual(result[1], title_fingerprint("Private Chat"))

    def test_automation_id_is_ignored_as_a_content_source(self):
        named = _Item(
            _Rect(20, 100, 420, 180),
            True,
            runtime_id=(1, 2, 3),
            name="Private Chat",
            automation_id="chat-row-17",
        )
        renamed = _Item(
            _Rect(20, 100, 420, 180),
            True,
            runtime_id=(1, 2, 3),
            name="Private Chat",
            automation_id="different-id",
        )
        with self._app_patch(self._window([named])):
            first = _selected_chat_anchor(123)
        with self._app_patch(self._window([renamed])):
            second = _selected_chat_anchor(123)

        self.assertEqual(first, second)

    def test_unselected_left_chat_is_not_an_anchor(self):
        item = _Item(
            _Rect(20, 100, 420, 180),
            False,
            runtime_id=(1, 2, 3),
            name="Private Chat",
            automation_id="chat-row-17",
        )
        with self._app_patch(self._window([item])):
            result = _selected_chat_anchor(123)

        self.assertEqual(result, ((), ""))

    def test_selected_right_side_control_is_not_an_anchor(self):
        item = _Item(
            _Rect(700, 100, 980, 180),
            True,
            runtime_id=(1, 2, 3),
            name="Private Chat",
            automation_id="chat-row-17",
        )
        with self._app_patch(self._window([item])):
            result = _selected_chat_anchor(123)

        self.assertEqual(result, ((), ""))

    def test_multiple_selected_left_rows_are_ambiguous(self):
        items = [
            _Item(
                _Rect(20, 100, 420, 180),
                True,
                runtime_id=(1, 2, 3),
                name="First",
                automation_id="chat-row-1",
            ),
            _Item(
                _Rect(20, 200, 420, 280),
                True,
                runtime_id=(4, 5, 6),
                name="Second",
                automation_id="chat-row-2",
            ),
        ]
        with self._app_patch(self._window(items)):
            result = _selected_chat_anchor(123)

        self.assertEqual(result, ((), ""))

    def test_runtime_id_can_be_missing_when_name_exists(self):
        item = _Item(
            _Rect(20, 100, 420, 180),
            True,
            runtime_id=(),
            name="Private Chat",
            automation_id="chat-row-17",
        )
        with self._app_patch(self._window([item])):
            result = _selected_chat_anchor(123)

        self.assertEqual(result[0], ())
        self.assertTrue(result[1])

    def test_exception_during_enumeration_degrades_to_empty_anchor(self):
        window = self._window([])
        window.descendants.side_effect = RuntimeError("uia unavailable")
        with self._app_patch(window):
            result = _selected_chat_anchor(123)

        self.assertEqual(result, ((), ""))

    def test_zero_window_is_content_free_and_side_effect_free(self):
        with patch("pywinauto.Application") as application:
            result = _selected_chat_anchor(0)

        self.assertEqual(result, ((), ""))
        application.assert_not_called()


if __name__ == "__main__":
    unittest.main()
