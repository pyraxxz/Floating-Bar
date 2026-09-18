import unittest
from unittest.mock import patch

from floatingbar.telegram_chats import (
    TelegramChatItem,
    chat_identity_matches,
    select_telegram_chat,
)


class TelegramChatIdentityAmbiguityTests(unittest.TestCase):
    def test_select_rejects_duplicate_name_when_structural_identity_is_unavailable(self):
        requested = TelegramChatItem(100, 200, "Alex", 10, 100, 310, 150)
        first = TelegramChatItem(100, 200, "Alex", 10, 100, 310, 150)
        second = TelegramChatItem(100, 200, "Alex", 10, 150, 310, 200)
        with patch("floatingbar.telegram_chats.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(first, second)), \
             patch("floatingbar.telegram_chats.winapi.post_click") as post_click:
            with self.assertRaisesRegex(RuntimeError, "name is ambiguous"):
                select_telegram_chat(requested)
        post_click.assert_not_called()

    def test_chat_identity_matches_uses_container_identity(self):
        requested = TelegramChatItem(
            100, 200, "Alex", 10, 100, 310, 150, True,
            None, ("ListItem", "shared", "row", "uia"),
            ("ancestor1", "Pane", "workspace-a", "uia"),
        )
        correct = TelegramChatItem(
            100, 200, "Alex", 12, 102, 312, 152, True,
            None, ("ListItem", "shared", "row", "uia"),
            ("ancestor1", "Pane", "workspace-a", "uia"),
        )
        other = TelegramChatItem(
            100, 200, "Alex", 12, 202, 312, 252, True,
            None, ("ListItem", "shared", "row", "uia"),
            ("ancestor1", "Pane", "workspace-b", "uia"),
        )
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(correct, other)):
            self.assertTrue(chat_identity_matches(requested))

    def test_chat_identity_matches_rejects_multiple_selected_same_name_without_identity(self):
        requested = TelegramChatItem(100, 200, "Alex", 10, 100, 310, 150, True)
        first = TelegramChatItem(100, 200, "Alex", 10, 100, 310, 150, True)
        second = TelegramChatItem(100, 200, "Alex", 10, 150, 310, 200, True)
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(first, second)):
            self.assertFalse(chat_identity_matches(requested))

    def test_chat_identity_matches_rejects_same_name_far_from_original_row_without_identity(self):
        requested = TelegramChatItem(100, 200, "Alex", 10, 100, 310, 150, True)
        switched = TelegramChatItem(100, 200, "Alex", 200, 300, 500, 350, True)
        with patch("floatingbar.telegram_chats.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.telegram_chats.enumerate_telegram_chats", return_value=(switched,)):
            self.assertFalse(chat_identity_matches(requested))


if __name__ == "__main__":
    unittest.main()
