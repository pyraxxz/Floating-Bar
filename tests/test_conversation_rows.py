import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.conversation_attention import AttentionState, ConversationAttention
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
    def __init__(self, rect, name, selected=False, runtime_id=None, control_identity=None, parent=None):
        self._rect = rect
        self.element_info = SimpleNamespace(
            name=name,
            runtime_id=runtime_id,
            control_type=(control_identity[0] if control_identity else "ListItem"),
            automation_id=(control_identity[1] if control_identity and len(control_identity) > 1 else ""),
            class_name=(control_identity[2] if control_identity and len(control_identity) > 2 else ""),
            framework_id=(control_identity[3] if control_identity and len(control_identity) > 3 else ""),
        )
        self._selected = selected
        self._parent = parent

    def rectangle(self):
        return self._rect

    def is_selected(self):
        return self._selected

    def parent(self):
        if self._parent is None:
            raise RuntimeError("no parent")
        return self._parent


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
        self.assertIsNotNone(rows[0].control_identity)
        self.assertEqual(rows[0].attention.state, AttentionState.SELECTED)


    def test_enumeration_captures_process_instance_identity(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.side_effect = [[
            _Item(_Rect(20, 100, 420, 160), "Alice", True, (1, 10)),
        ], []]
        with self._app_patch(window),              patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200),              patch("floatingbar.conversation_rows.winapi.get_process_creation_time", return_value=123),              patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123)
        self.assertEqual(rows[0].process_start, 123)

    def test_selection_rejects_same_pid_after_process_restart(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            process_start=123,
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200),              patch("floatingbar.conversation_rows.winapi.get_process_creation_time", return_value=456),              patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "process instance changed"):
                from floatingbar.conversation_rows import _refresh_row
                _refresh_row(item)

    def test_selection_forwards_process_instance_identity_to_click(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            True, (1, 10), ("ListItem", "row", "uia"),
            process_start=123,
        )
        fresh = ConversationItem(
            123, 200, "Alice", 24, 104, 424, 164,
            True, (1, 10), ("ListItem", "row", "uia"),
            process_start=123,
        )
        with patch("floatingbar.conversation_rows.refresh_conversation", return_value=fresh),              patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)),              patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            confirmed = select_conversation(item)
        self.assertEqual(confirmed, fresh)
        post_click.assert_called_once_with(
            123,
            220,
            134,
            expected_pid=200,
            expected_process_start=123,
        )

    def test_enumeration_excludes_automation_id_from_control_identity(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.side_effect = [[
            _Item(
                _Rect(20, 100, 420, 160),
                "Alice",
                False,
                None,
                ("ListItem", "Alice", "ChatRow", "uia"),
            )
        ], []]
        with self._app_patch(window),              patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200),              patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123)
        self.assertEqual(rows[0].control_identity, ("ListItem", "ChatRow", "uia"))

    def test_enumeration_captures_content_free_parent_identity(self):
        parent = _Item(_Rect(0, 0, 500, 900), "ignored")
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        window.descendants.side_effect = [[
            _Item(_Rect(20, 100, 420, 160), "Alice", False, None,
                  ("ListItem", "row", "uia"), parent=parent)
        ], []]
        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123)

        self.assertEqual(rows[0].container_identity[:1], ("ancestor1",))
        self.assertIn("ListItem", rows[0].container_identity)

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

    def test_explicit_attention_detector_prioritizes_unread_rows(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        first = _Item(_Rect(20, 100, 420, 160), "Normal", False, (1, 10))
        second = _Item(_Rect(20, 200, 420, 260), "Unread", False, (1, 11))
        window.descendants.side_effect = [[first, second], []]

        def detector(item):
            if item.element_info.name == "Unread":
                return ConversationAttention(AttentionState.UNREAD, "test-detector")
            return ConversationAttention()

        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123, limit=2, attention_detector=detector)

        self.assertEqual([row.name for row in rows], ["Unread", "Normal"])
        self.assertTrue(rows[0].needs_attention)
        self.assertEqual(rows[0].attention.source, "test-detector")

    def test_attention_detector_failure_fails_closed_to_unknown(self):
        window = Mock()
        window.rectangle.return_value = _Rect(0, 0, 1000, 900)
        item = _Item(_Rect(20, 100, 420, 160), "Chat", False, (1, 10))
        window.descendants.side_effect = [[item], []]

        def detector(_item):
            raise RuntimeError("ambiguous UIA state")

        with self._app_patch(window), \
             patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True):
            rows = enumerate_conversations(123, attention_detector=detector)

        self.assertEqual(rows[0].attention.state, AttentionState.UNKNOWN)
        self.assertFalse(rows[0].needs_attention)

    def test_selection_revalidates_row_before_background_click(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, True, (1, 10), ("ListItem", "row", "uia"))
        fresh = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, True, (1, 10), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.conversation_rows.refresh_conversation", return_value=fresh), \
             patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)), \
             patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            confirmed = select_conversation(item)

        self.assertEqual(confirmed, fresh)
        self.assertTrue(confirmed.selected)
        post_click.assert_called_once_with(123, 220, 134, expected_pid=200)

    def test_selection_waits_for_selected_state_after_background_click(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (1, 10), ("ListItem", "alice", "row", "uia"))
        waiting = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, False, (1, 10), ("ListItem", "alice", "row", "uia"))
        selected = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, True, (1, 10), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.conversation_rows.refresh_conversation", side_effect=[waiting, waiting, selected]), \
             patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)), \
             patch("floatingbar.conversation_rows.time.sleep") as sleep, \
             patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            confirmed = select_conversation(item)

        self.assertEqual(confirmed, selected)
        self.assertTrue(confirmed.selected)
        post_click.assert_called_once_with(123, 220, 134, expected_pid=200)
        self.assertEqual(sleep.call_count, 1)

    def test_selection_rejects_click_that_never_becomes_selected(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (1, 10), ("ListItem", "alice", "row", "uia"))
        waiting = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, False, (1, 10), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.conversation_rows.refresh_conversation", side_effect=[waiting] * 6), \
             patch("floatingbar.conversation_rows._screen_to_client", return_value=(220, 134)), \
             patch("floatingbar.conversation_rows.time.sleep") as sleep, \
             patch("floatingbar.conversation_rows.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "was not selected"):
                select_conversation(item)

        post_click.assert_called_once_with(123, 220, 134, expected_pid=200)
        self.assertEqual(sleep.call_count, 4)

    def test_runtime_identity_takes_precedence_over_duplicate_names(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (9, 9), ("ListItem", "alice", "row", "uia"))
        fresh = ConversationItem(123, 200, "Alice", 22, 102, 422, 162, False, (9, 9), ("ListItem", "alice", "row", "uia"))
        wrong = ConversationItem(123, 200, "Alice", 21, 300, 421, 360, False, (9, 10), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(wrong, fresh)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), fresh)

    def test_runtime_identity_ambiguity_is_rejected(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            runtime_id=(9, 9),
        )
        first = ConversationItem(
            123, 200, "Alice", 22, 102, 422, 162,
            runtime_id=(9, 9),
        )
        second = ConversationItem(
            123, 200, "Alice", 24, 300, 424, 360,
            runtime_id=(9, 9),
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(first, second)):
            from floatingbar.conversation_rows import _refresh_row
            with self.assertRaisesRegex(RuntimeError, "runtime identity is ambiguous"):
                _refresh_row(item)

    def test_runtime_identity_with_changed_structure_is_rejected(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            runtime_id=(9, 9),
            control_identity=("ListItem", "alice", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        changed = ConversationItem(
            123, 200, "Alice", 22, 102, 422, 162,
            runtime_id=(9, 9),
            control_identity=("ListItem", "alice", "changed", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-b", "uia"),
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(changed,)):
            from floatingbar.conversation_rows import _refresh_row
            with self.assertRaisesRegex(RuntimeError, "control identity changed"):
                _refresh_row(item)

    def test_runtime_identity_allows_ancestor_reflow(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            runtime_id=(9, 9),
            control_identity=("ListItem", "alice", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        moved = ConversationItem(
            123, 200, "Alice", 24, 110, 424, 170,
            runtime_id=(9, 9),
            control_identity=("ListItem", "alice", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-b", "uia"),
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(moved,)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), moved)

    def test_runtime_identity_allows_display_name_change(self):
        item = ConversationItem(
            123, 200, "Alice", 20, 100, 420, 160,
            False, (9, 9), ("ListItem", "alice", "row", "uia")
        )
        renamed = ConversationItem(
            123, 200, "Alice Cooper", 20, 100, 420, 160,
            False, (9, 9), ("ListItem", "alice", "row", "uia")
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200),              patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(renamed,)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), renamed)

    def test_structural_identity_allows_display_name_change(self):
        item = ConversationItem(
            123, 200, "general", 20, 100, 420, 160,
            False, None, ("ListItem", "general", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace", "uia"),
        )
        renamed = ConversationItem(
            123, 200, "general-renamed", 20, 100, 420, 160,
            False, None, ("ListItem", "general", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace", "uia"),
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200),              patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(renamed,)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), renamed)

    def test_runtime_identity_change_is_rejected(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, (9, 9))
        changed = ConversationItem(
            123, 200, "Alice Cooper", 20, 100, 420, 160,
            False, (9, 10), ("ListItem", "different", "row", "uia")
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(changed,)):
            from floatingbar.conversation_rows import _refresh_row
            with self.assertRaisesRegex(RuntimeError, "runtime identity disappeared"):
                _refresh_row(item)

    def test_structural_identity_prevents_duplicate_name_ambiguity(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, None, ("ListItem", "alice-1", "row", "uia"))
        correct = ConversationItem(123, 200, "Alice", 22, 102, 422, 162, False, None, ("ListItem", "alice-1", "row", "uia"))
        duplicate_name = ConversationItem(123, 200, "Alice", 24, 300, 424, 360, False, None, ("ListItem", "alice-2", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(duplicate_name, correct)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), correct)

    def test_container_identity_disambiguates_duplicate_control_identity(self):
        item = ConversationItem(
            123, 200, "general", 20, 100, 420, 160, False, None,
            ("ListItem", "shared", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        correct = ConversationItem(
            123, 200, "general", 22, 102, 422, 162, False, None,
            ("ListItem", "shared", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        duplicate = ConversationItem(
            123, 200, "general", 24, 300, 424, 360, False, None,
            ("ListItem", "shared", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-b", "uia"),
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(duplicate, correct)):
            from floatingbar.conversation_rows import _refresh_row
            self.assertEqual(_refresh_row(item), correct)

    def test_ambiguous_structural_identity_is_rejected(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160, False, None, ("ListItem", "shared", "row", "uia"))
        first = ConversationItem(123, 200, "Alice", 22, 102, 422, 162, False, None, ("ListItem", "shared", "row", "uia"))
        second = ConversationItem(123, 200, "Alice", 24, 104, 424, 164, False, None, ("ListItem", "shared", "row", "uia"))
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(first, second)):
            from floatingbar.conversation_rows import _refresh_row
            with self.assertRaisesRegex(RuntimeError, "ambiguous"):
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
