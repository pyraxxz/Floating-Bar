import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.conversation_attention import AttentionState, ConversationAttention
from floatingbar.telegram_chat_picker import ChatPickerRow, TelegramChatPicker, to_chat_picker_rows
from floatingbar.telegram_chats import (
    TelegramChatItem,
    chat_identity_matches,
    confirmed_telegram_chat_for_scope,
    enumerate_telegram_chats,
    select_telegram_chat,
)


class TelegramChatPickerTests(unittest.TestCase):
    def test_picker_rows_preserve_chat_name_and_selection_without_extra_content(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60, True)
        self.assertEqual(
            to_chat_picker_rows([chat]),
            (ChatPickerRow("Alice", True, chat),),
        )

    def test_unread_row_exposes_attention_without_message_content(self):
        chat = TelegramChatItem(
            100, 200, "Alice", 0, 10, 300, 60,
            False, None, None,
            ConversationAttention(AttentionState.UNREAD, "telegram-uia-badge"),
        )
        row = to_chat_picker_rows([chat])[0]
        self.assertTrue(row.needs_attention)
        self.assertEqual(row.name, "Alice")

    def test_chat_catalog_prioritizes_explicit_unread_before_current_and_visual_order(self):
        unread = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=80, right=320, bottom=120, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Unread", item_status="2", runtime_id=(1, 2), control_type="ListItem"),
            is_selected=lambda: False,
        )
        selected = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Current", item_status="0", runtime_id=(1, 1), control_type="ListItem"),
            is_selected=lambda: True,
        )
        normal = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=40, right=320, bottom=80, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Normal", item_status="0", runtime_id=(1, 3), control_type="ListItem"),
            is_selected=lambda: False,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, bottom=500)
        window.descendants.return_value = [normal, selected, unread]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=3)
        self.assertEqual([item.name for item in result], ["Unread", "Current", "Normal"])
        self.assertEqual(result[0].attention.state, AttentionState.UNREAD)

    def test_chat_catalog_captures_process_instance_identity(self):
        item = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Private Chat", runtime_id=(1, 2), control_type="ListItem", item_status="0"),
            is_selected=lambda: False,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, bottom=500)
        window.descendants.return_value = [item]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.get_process_creation_time", return_value=123), \
             patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=1)
        self.assertEqual(result[0].process_start, 123)

    def test_select_chat_prefers_uia_selection_before_posted_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        refreshed = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270)
        selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True)
        wrapper = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=110, top=210),
            element_info=SimpleNamespace(name="Alice"),
            select=Mock(),
            is_selected=Mock(return_value=True),
        )
        window = Mock()
        window.descendants.return_value = [wrapper]
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(refreshed,), (selected,)]), \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)), \
             patch("floatingbar.telegram_chats.Application") as app_cls, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            app_cls.return_value.connect.return_value.window.return_value.wrapper_object.return_value = window
            result = select_telegram_chat(chat)
        self.assertEqual(result, selected)
        wrapper.select.assert_called_once_with()
        post_click.assert_not_called()

    def test_select_chat_rejects_same_pid_after_process_restart(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60, process_start=123)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.get_process_creation_time", return_value=456), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "process instance changed"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_select_chat_forwards_process_instance_identity_to_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, process_start=123)
        refreshed = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 1), ("ListItem", "row", "uia"), process_start=123)
        selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True, (1, 1), ("ListItem", "row", "uia"), process_start=123)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.get_process_creation_time", return_value=123), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(refreshed,), (selected,)]), \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            result = select_telegram_chat(chat)
        self.assertEqual(result, selected)
        post_click.assert_called_once_with(
            100, 120, 140,
            expected_pid=200,
            expected_process_start=123,
        )

    def test_chat_identity_matches_rejects_same_pid_after_process_restart(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, True, (1, 2), process_start=123)
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.get_process_creation_time", return_value=456), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats") as enumerate_rows:
            self.assertFalse(chat_identity_matches(chat))
        enumerate_rows.assert_not_called()

    def test_chat_catalog_excludes_automation_id_from_control_identity(self):
        item = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(
                name="Private Chat",
                runtime_id=(1, 2),
                control_type="ListItem",
                automation_id="Private Chat",
                class_name="ChatRow",
                framework_id="uia",
                item_status="0",
            ),
            is_selected=lambda: False,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, bottom=500)
        window.descendants.return_value = [item]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200),              patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True),              patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=1)
        self.assertEqual(result[0].control_identity, ("ListItem", "ChatRow", "uia"))

    def test_chat_catalog_keeps_selected_chat_ahead_of_visual_order_without_attention(self):
        lower = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=40, right=320, bottom=80, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Second", runtime_id=(1, 2), control_type="ListItem", automation_id="second", class_name="row", framework_id="uia", item_status="0"),
            is_selected=lambda: False,
        )
        selected = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="First", runtime_id=(1, 1), control_type="ListItem", automation_id="first", class_name="row", framework_id="uia", item_status="0"),
            is_selected=lambda: True,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, bottom=500)
        window.descendants.return_value = [lower, selected]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "First")
        self.assertTrue(result[0].selected)
        self.assertEqual(result[0].runtime_id, (1, 1))
        self.assertIsNotNone(result[0].control_identity)

    def test_chat_catalog_preserves_visual_order_for_unselected_rows(self):
        item_a = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=40, right=320, bottom=80, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Second", item_status="0"),
            is_selected=lambda: False,
        )
        item_b = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="First", item_status="0"),
            is_selected=lambda: False,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, bottom=500)
        window.descendants.return_value = [item_a, item_b]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=2)
        self.assertEqual([item.name for item in result], ["First", "Second"])

    def test_select_chat_rejects_recycled_window_scope(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=201), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_select_chat_rejects_ambiguous_runtime_identity(self):
        requested = TelegramChatItem(
            100, 200, "Alex", 10, 100, 310, 150,
            runtime_id=(1, 2, 3),
        )
        first = TelegramChatItem(
            100, 200, "Alex", 12, 102, 312, 152,
            runtime_id=(1, 2, 3),
        )
        second = TelegramChatItem(
            100, 200, "Alex", 12, 202, 312, 252,
            runtime_id=(1, 2, 3),
        )
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(first, second)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "runtime identity is ambiguous"):
                select_telegram_chat(requested)
        post_click.assert_not_called()

    def test_select_chat_refreshes_row_before_background_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        refreshed = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 1), ("ListItem", "row", "uia"))
        selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True, (1, 1), ("ListItem", "row", "uia"))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(refreshed,), (selected,)]) as enumerate_rows, \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)) as to_client, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            result = select_telegram_chat(chat)
        self.assertEqual(result, selected)
        self.assertEqual(confirmed_telegram_chat_for_scope(100, 200), selected)
        enumerate_rows.assert_has_calls([
            unittest.mock.call(100, limit=None),
            unittest.mock.call(100, limit=None),
        ])
        self.assertEqual(enumerate_rows.call_count, 2)
        to_client.assert_called_once_with(100, 210, 240)
        post_click.assert_called_once_with(100, 120, 140, expected_pid=200)

    def test_select_chat_waits_for_selection_after_background_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, False, (1, 1), ("ListItem", "alice", "row", "uia"))
        waiting = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 1), ("ListItem", "alice", "row", "uia"))
        selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True, (1, 1), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(waiting,), (waiting,), (selected,)]) as enumerate_rows, \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)), \
             patch("floatingbar.telegram_chats.time.sleep") as sleep, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            result = select_telegram_chat(chat)
        self.assertEqual(result, selected)
        self.assertEqual(confirmed_telegram_chat_for_scope(100, 200), selected)
        post_click.assert_called_once_with(100, 120, 140, expected_pid=200)
        self.assertEqual(sleep.call_count, 1)
        self.assertEqual(enumerate_rows.call_count, 3)

    def test_select_chat_rejects_click_that_never_becomes_selected(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, False, (1, 1), ("ListItem", "alice", "row", "uia"))
        waiting = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 1), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(waiting,)] * 6), \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)), \
             patch("floatingbar.telegram_chats.time.sleep") as sleep, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "was not selected"):
                select_telegram_chat(chat)
        post_click.assert_called_once_with(100, 120, 140, expected_pid=200)
        self.assertEqual(sleep.call_count, 4)

    def test_select_chat_rejects_runtime_identity_change(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, False, (1, 2))
        replacement = TelegramChatItem(100, 200, "Bob", 100, 200, 300, 260, False, (9, 9))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(replacement,)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "runtime identity disappeared"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_chat_identity_matches_only_when_the_same_row_is_selected(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, True, (1, 2))
        same_selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True, (1, 2))
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(same_selected,)):
            self.assertTrue(chat_identity_matches(chat))

        switched = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 2))
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(switched,)):
            self.assertFalse(chat_identity_matches(chat))

    def test_select_chat_rejects_missing_row_before_background_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=()), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "no longer available"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_select_chat_allows_large_move_when_runtime_identity_stays_stable(self):
        chat = TelegramChatItem(
            100, 200, "Alice", 100, 200, 300, 260,
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "ChatRow", "uia"),
        )
        moved = TelegramChatItem(
            100, 200, "Alice", 260, 420, 460, 480,
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "ChatRow", "uia"),
        )
        selected = TelegramChatItem(
            100, 200, "Alice", 260, 420, 460, 480, True,
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "ChatRow", "uia"),
        )
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(moved,), (selected,)]), \
             patch("floatingbar.telegram_chats._try_uia_select", return_value=False), \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(300, 450)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            result = select_telegram_chat(chat)

        self.assertEqual(result, selected)
        post_click.assert_called_once_with(100, 300, 450, expected_pid=200)

    def test_select_chat_rejects_large_row_move_before_background_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        moved = TelegramChatItem(100, 200, "Alice", 200, 260, 400, 320)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(moved,)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "moved"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_picker_show_hides_existing_popup_when_refresh_fails(self):
        picker = TelegramChatPicker.__new__(TelegramChatPicker)
        picker.owner = Mock()
        picker.refresh = Mock(side_effect=RuntimeError("UIA unavailable"))
        picker.on_select = Mock()
        stale_popup = Mock()
        picker.window = stale_popup
        picker.hide()
        self.assertIsNone(picker.window)
        stale_popup.destroy.assert_called_once()


    def test_chat_identity_revalidation_requests_unbounded_rows(self):
        chat = TelegramChatItem(
            100, 200, "Alice", 10, 100, 310, 150, True,
            runtime_id=(1, 2, 3),
        )
        same = TelegramChatItem(
            100, 200, "Alice", 10, 100, 310, 150, True,
            runtime_id=(1, 2, 3),
        )
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(same,)) as enumerate_rows:
            self.assertTrue(chat_identity_matches(chat))
        enumerate_rows.assert_called_once_with(100, limit=None)


if __name__ == "__main__":
    unittest.main()
