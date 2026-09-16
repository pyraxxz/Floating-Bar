import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.telegram_chat_picker import ChatPickerRow, TelegramChatPicker, to_chat_picker_rows
from floatingbar.telegram_chats import TelegramChatItem, enumerate_telegram_chats, select_telegram_chat


class TelegramChatPickerTests(unittest.TestCase):
    def test_picker_rows_preserve_chat_name_and_selection_without_extra_content(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60, True)
        self.assertEqual(
            to_chat_picker_rows([chat]),
            (ChatPickerRow("Alice", True, chat),),
        )

    def test_chat_catalog_sorts_visible_rows_and_limits_results(self):
        item_a = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=40, right=320, bottom=80, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="Second"),
            is_selected=lambda: False,
        )
        item_b = SimpleNamespace(
            rectangle=lambda: SimpleNamespace(left=10, top=10, right=320, bottom=50, width=lambda: 310, height=lambda: 40),
            element_info=SimpleNamespace(name="First"),
            is_selected=lambda: True,
        )
        window = Mock()
        window.rectangle.return_value = SimpleNamespace(left=0, top=0, width=lambda: 500, top=0, bottom=500)
        window.descendants.return_value = [item_a, item_b]
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.Application") as app_cls:
            connected = app_cls.return_value.connect.return_value
            connected.window.return_value.wrapper_object.return_value = window
            result = enumerate_telegram_chats(100, limit=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "First")
        self.assertTrue(result[0].selected)

    def test_select_chat_rejects_recycled_window_scope(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 10, 300, 60)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=201), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                select_telegram_chat(chat)
        post_click.assert_not_called()

    def test_select_chat_posts_background_click_without_foreground_helper(self):
        chat = TelegramChatItem(100, 200, "Alice", 100, 200, 300, 260)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats._screen_to_client", return_value=(120, 140)) as to_client, \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            select_telegram_chat(chat)
        to_client.assert_called_once_with(100, 200, 230)
        post_click.assert_called_once_with(100, 120, 140)

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
