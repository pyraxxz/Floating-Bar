import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.telegram_chats import TelegramChatItem, enumerate_telegram_chats, select_telegram_chat


class TelegramChatPickerTests(unittest.TestCase):
    def test_enumeration_keeps_only_visible_named_rows(self):
        # Existing test body preserved below.
        item_a = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=20, top=40, right=220, bottom=100, width=lambda: 200, height=lambda: 60),
            element_info=SimpleNamespace(name="Second", runtime_id=(1, 2), control_type="ListItem", automation_id="second", class_name="row", framework_id="uia"),
            is_selected=lambda: False,
        )
        item_b = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=20, top=120, right=220, bottom=180, width=lambda: 200, height=lambda: 60),
            element_info=SimpleNamespace(name="First", runtime_id=(1, 1), control_type="ListItem", automation_id="first", class_name="row", framework_id="uia"),
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

    def test_select_chat_refreshes_row_before_background_click(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        refreshed = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, False, (1, 1), ("ListItem", "alice", "row", "uia"))
        selected = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270, True, (1, 1), ("ListItem", "alice", "row", "uia"))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", side_effect=[(refreshed,), (selected,)]) as enumerate_rows, \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)) as to_client, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            result = select_telegram_chat(chat)
        self.assertEqual(result, selected)
        enumerate_rows.assert_has_calls([
            unittest.mock.call(100, limit=24),
            unittest.mock.call(100, limit=24),
        ])
        self.assertEqual(enumerate_rows.call_count, 2)
        to_client.assert_called_once_with(100, 210, 240)
        post_click.assert_called_once_with(100, 120, 140)

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
        post_click.assert_called_once_with(100, 120, 140)
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
        post_click.assert_called_once_with(100, 120, 140)
        self.assertEqual(sleep.call_count, 4)

    def test_select_chat_rejects_runtime_identity_change(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, False, (1, 2))
        replacement = TelegramChatItem(100, 200, "Bob", 100, 200, 300, 260, False, (1, 2))
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(replacement,)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_chat_identity_matches_only_when_the_same_row_is_selected(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260, True, (1, 2))
        self.assertTrue(chat.selected)


if __name__ == "__main__":
    unittest.main()
