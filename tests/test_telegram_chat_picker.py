import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.telegram_chat_picker import ChatPickerRow, TelegramChatPicker, to_chat_picker_rows
from floatingbar.telegram_chats import TelegramChatItem, chat_identity_matches, enumerate_telegram_chats, select_telegram_chat


class TelegramChatPickerTests(unittest.TestCase):
    def test_picker_rows_preserve_chat_name_and_selection_without_extra_content(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60, True)
        self.assertEqual(
            to_chat_picker_rows([chat]),
            (ChatPickerRow("Alice", True, chat),),
        )

    def test_chat_catalog_keeps_selected_chat_ahead_of_visual_order(self):
        lower = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=40, right=320, bottom=80, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Second", runtime_id=(1, 2), control_type="ListItem", automation_id="second", class_name="row", framework_id="uia"),
            is_selected=lambda: False,
        )
        selected = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="First", runtime_id=(1, 1), control_type="ListItem", automation_id="first", class_name="row", framework_id="uia"),
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
            element_info=SimpleNamespace(name="Second"),
            is_selected=lambda: False,
        )
        item_b = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="First"),
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
        refreshed = TelegramChatItem(100, 200, "Alice", 110, 210, 310, 270)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(refreshed,)) as enumerate_rows, \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)) as to_client, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            select_telegram_chat(chat)
        enumerate_rows.assert_called_once_with(100, limit=24)
        to_client.assert_called_once_with(100, 210, 240)
        post_click.assert_called_once_with(100, 120, 140)

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


if __name__ == "__main__":
    unittest.main()
