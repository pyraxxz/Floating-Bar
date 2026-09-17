import unittest

from floatingbar.conversation_attention import AttentionState, ConversationAttention
from floatingbar.conversation_picker import (
    ConversationPicker,
    conversation_picker_identity,
    paginate_conversations,
    to_conversation_picker_rows,
)
from floatingbar.conversation_rows import ConversationItem


def _item(number: int) -> ConversationItem:
    return ConversationItem(
        100,
        200,
        f"Chat {number}",
        0,
        10 + number * 20,
        300,
        60 + number * 20,
    )


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

    def test_recent_row_gets_recent_label_without_overriding_attention(self):
        item = _item(1)
        key = conversation_picker_identity(item)
        row = to_conversation_picker_rows([item], [key])[0]
        self.assertTrue(row.recent)
        self.assertEqual(row.suffix, "  Recent")

    def test_picker_merges_recent_rows_before_live_rows_and_deduplicates(self):
        recent = _item(1)
        duplicate = _item(1)
        live = _item(2)
        catalog, recent_keys = ConversationPicker._merge_catalog((recent,), (duplicate, live))
        self.assertEqual([item.name for item in catalog], ["Chat 1", "Chat 2"])
        self.assertIn(conversation_picker_identity(recent), recent_keys)

    def test_picker_title_is_safe_and_reopenable(self):
        picker = ConversationPicker(object(), lambda: (), lambda _item: None)
        self.assertEqual(picker.title, "Conversations")
        picker.set_title("Microsoft Teams")
        self.assertEqual(picker.title, "Microsoft Teams")
        picker.set_title("  ")
        self.assertEqual(picker.title, "Conversations")

    def test_pagination_exposes_next_page_without_reordering(self):
        conversations = tuple(_item(index) for index in range(8))
        page, offset, has_previous, has_next = paginate_conversations(
            conversations,
            0,
            6,
        )
        self.assertEqual([item.name for item in page], [f"Chat {index}" for index in range(6)])
        self.assertEqual(offset, 0)
        self.assertFalse(has_previous)
        self.assertTrue(has_next)

    def test_pagination_exposes_previous_page_and_clamps_end(self):
        conversations = tuple(_item(index) for index in range(8))
        page, offset, has_previous, has_next = paginate_conversations(
            conversations,
            999,
            6,
        )
        self.assertEqual([item.name for item in page], ["Chat 6", "Chat 7"])
        self.assertEqual(offset, 6)
        self.assertTrue(has_previous)
        self.assertFalse(has_next)

    def test_pagination_uses_single_page_for_short_catalog(self):
        conversations = tuple(_item(index) for index in range(3))
        page, offset, has_previous, has_next = paginate_conversations(
            conversations,
            6,
            6,
        )
        self.assertEqual([item.name for item in page], ["Chat 0", "Chat 1", "Chat 2"])
        self.assertEqual(offset, 0)
        self.assertFalse(has_previous)
        self.assertFalse(has_next)


if __name__ == "__main__":
    unittest.main()
