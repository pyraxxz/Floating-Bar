import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.conversation_rows import (
    ConversationItem,
    enumerate_conversations,
    select_conversation,
)


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
    def __init__(self, rect, name, selected=False):
        self._rect = rect
        self.element_info = SimpleNamespace(name=name)
        self._selected = selected

    def rectangle(self):
        return self._rect

    def is_selected(self):
        return self._selected


class ConversationRowTests(unittest.TestCase):
    def _app_patch(self, window):
        application = Mock()
        application.return_value.connect.return_value.window.return_value.wrapper_object.return_value = window
        fake_pywinauto = SimpleNamespace(Application=application)
        return patch.dict(sys.modules, {"pywinauto": fake_pywinauto})

    def test_enumeration_keeps_left_visible_named_rows_only(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.side_effect = [
            [
                _Item(_Rect(20, 100, 420, 160), "Alice", True),
                _Item(_Rect(30, 180, 430, 240), "Bob"),
                _Item(_Rect(700, 180, 980, 240), "Right side"),
            ],
            [],
        ]
        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123)

        self.assertEqual([row.name for row in rows], ["Alice", "Bob"])
        self.assertTrue(rows[0].selected)
        self.assertEqual(rows[0].hwnd, 123)
        self.assertEqual(rows[0].pid, 200)

    def test_selection_revalidates_row_before_background_click(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, True)
        fresh = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, True)
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.conversation_rows._refresh_row", return_value=fresh), \
             patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)), \
             patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            select_conversation(item)

        post_click.assert_called_once_with(123, 220, 134)

    def test_selection_rejects_replaced_process(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160)
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=999), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                from floatingbar.conversation_rows import _refresh_row
                _refresh_row(item)


if __name__ == "__main__":
    unittest.main()
