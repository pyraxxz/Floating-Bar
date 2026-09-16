import unittest
from unittest.mock import patch

from floatingbar.conversation_rows import ConversationItem, _refresh_row


class ConversationNameAmbiguityTests(unittest.TestCase):
    def test_name_only_fallback_rejects_duplicate_names(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160)
        first = ConversationItem(123, 200, "Alice", 22, 102, 422, 162)
        second = ConversationItem(123, 200, "Alice", 24, 300, 424, 360)
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(first, second)):
            with self.assertRaisesRegex(RuntimeError, "name is ambiguous"):
                _refresh_row(item)

    def test_name_only_fallback_accepts_one_stable_row(self):
        item = ConversationItem(123, 200, "Alice", 20, 100, 420, 160)
        fresh = ConversationItem(123, 200, "Alice", 22, 102, 422, 162)
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(fresh,)):
            self.assertEqual(_refresh_row(item), fresh)


if __name__ == "__main__":
    unittest.main()
