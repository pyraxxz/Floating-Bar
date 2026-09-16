import unittest
from unittest.mock import patch

from floatingbar.conversation_rows import ConversationItem, _refresh_row


class ConversationIdentityDropTests(unittest.TestCase):
    def test_runtime_identity_loss_does_not_fall_back_to_name(self):
        item = ConversationItem(
            123,
            200,
            "Alice",
            20,
            100,
            420,
            160,
            False,
            (9, 9),
            None,
        )
        same_name = ConversationItem(
            123,
            200,
            "Alice",
            20,
            100,
            420,
            160,
            False,
            None,
            None,
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(same_name,)):
            with self.assertRaisesRegex(RuntimeError, "runtime identity disappeared"):
                _refresh_row(item)

    def test_structural_identity_loss_does_not_fall_back_to_name(self):
        item = ConversationItem(
            123,
            200,
            "Alice",
            20,
            100,
            420,
            160,
            False,
            None,
            ("ListItem", "alice", "row", "uia"),
        )
        same_name = ConversationItem(
            123,
            200,
            "Alice",
            20,
            100,
            420,
            160,
            False,
            None,
            None,
        )
        with patch("floatingbar.conversation_rows.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.conversation_rows.enumerate_conversations", return_value=(same_name,)):
            with self.assertRaisesRegex(RuntimeError, "structural identity disappeared"):
                _refresh_row(item)


if __name__ == "__main__":
    unittest.main()
