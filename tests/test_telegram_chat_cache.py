import unittest

import floatingbar.telegram_chats as telegram_chats
from floatingbar.telegram_chats import (
    TelegramChatItem,
    clear_confirmed_telegram_chat_for_scope,
    confirmed_telegram_chat_for_scope,
)


class TelegramChatCacheTests(unittest.TestCase):
    def test_confirmation_cache_can_be_explicitly_cleared_by_scope(self):
        chat = TelegramChatItem(100, 200, "Alice", 0, 0, 100, 40, True, (1, 2))
        telegram_chats._remember_confirmed_chat(chat)
        self.assertIs(confirmed_telegram_chat_for_scope(100, 200), chat)

        clear_confirmed_telegram_chat_for_scope(100, 200)
        self.assertIsNone(confirmed_telegram_chat_for_scope(100, 200))


if __name__ == "__main__":
    unittest.main()
