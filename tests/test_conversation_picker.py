import unittest

from floatingbar.conversation_attention import AttentionState, ConversationAttention
from floatingbar.conversation_picker import to_conversation_picker_rows
from floatingbar.conversation_rows import ConversationItem


class ConversationPickerRowTests(unittest.TestCase):
    def test_unread_row_gets_attention_label(self):
        item = ConversationItem(
            100,
            200,
            "Alice",
            0,
            10,
            300,
            60,
            False,
            attention=ConversationAttention(AttentionState.UNREAD, "test"),
        )
        row = to_conversation_picker_rows([item])[0]
        self.assertEqual(row.suffix, "  Needs attention")

    def test_current_row_keeps_current_label_without_attention(self):
        item = ConversationItem(
            100,
            200,
            "Alice",
            0,
            10,
            300,
            60,
            True,
        )
        row = to_conversation_picker_rows([item])[0]
        self.assertEqual(row.attention, AttentionState.UNKNOWN)
        self.assertEqual(row.suffix, "  Current")

    def test_attention_label_takes_precedence_over_current_label(self):
        item = ConversationItem(
            100,
            200,
            "Alice",
            0,
            10,
            300,
            60,
            True,
            attention=ConversationAttention(AttentionState.RELEVANT, "test"),
        )
        row = to_conversation_picker_rows([item])[0]
        self.assertEqual(row.suffix, "  Needs attention")


if __name__ == "__main__":
    unittest.main()
