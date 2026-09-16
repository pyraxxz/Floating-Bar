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
    def __init__(self, rect, name, selected=False, runtime_id=None):
        self._rect = rect
        self.element_info = SimpleNamespace(name=name, runtime_id=runtime_id)
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
                _Item(_Rect(20, 100, 420, 160), "Alice", True, (1, 10)),
                _Item(_Rect(30, 180, 430, 240), "Bob", False, (1, 11)),
                _Item(_Rect(700, 180, 980, 240), "Right side", False, (1, 12)),
            ],
            [],
        ]
        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123)

        self.assertEqual([row.name for row in rows], ["Alice", "Bob"])
        self.assertTrue(rows[0].selected)
        self.assertEqual(rows[0].runtime_id, (1, 10))
        self.assertEqual(rows[0].hwnd, 123)
        self.assertEqual(rows[0].pid, 200)

    def test_selected_row_is_presented_before_unselected_rows(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.side_effect = [
            [
                _Item(_Rect(20, 300, 420, 360), "Later", False, (1, 20)),
                _Item(_Rect(20, 100, 420, 160), "Current", True, (1, 21)),
            ],
            [],
        ]
        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123, limit=2)

        self.assertEqual([row.name for row in rows], ["Current", "Later"])

    def test_selection_revalidates_row_before_background_click(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, True, (1, 10))
        fresh = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, True, (1, 10))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.conversation_rows._refresh_row", return_value=fresh), \
             patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)), \
             patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            select_conversation(item)

        post_click.assert_called_once_with(123, 220, 134)

    def test_runtime_identity_takes_precedence_over_duplicate_names(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (9, 9))
        fresh = ConversationItem(123, 200, "Alice", 22, 102, 422, 162, False, (9, 9))
        wrong = ConversationItem(123, 200, "Alice", 21, 300, 421, 360, False, (9, 10))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(wrong, fresh)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), fresh)

    def test_runtime_identity_change_is_rejected(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (9, 9))
        changed = ConversationItem(123, 200, "Bob", 20, 100, 420, 160, False, (9, 9))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(changed,)):
            from floatingbar.conversation_rows import _refresh_row
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                _refresh_row(item)

    def test_selection_rejects_replaced_process(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160)
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=999), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                from floatingbar.conversation_rows import _refresh_row
                _refresh_row(item)


if __name__ == "__main__":
    unittest.main()
