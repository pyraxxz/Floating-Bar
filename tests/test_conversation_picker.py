import unittest

from floatingbar.conversation_attention import AttentionState, ConversationAttention
from floatingbar.conversation_picker import (
    ConversationPicker,
    empty_state_copy,
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
    def test_empty_state_copy_preserves_safe_title_and_recovery(self):
        self.assertEqual(
            empty_state_copy("Microsoft Teams"),
            (
                "No safe microsoft teams found",
                "No safe conversation rows are available right now.",
            ),
        )
        self.assertEqual(
            empty_state_copy("Microsoft Teams", True),
            (
                "Microsoft Teams unavailable",
                "The conversation list could not be read safely. You can try again.",
            ),
        )
        self.assertEqual(
            empty_state_copy("  "),
            (
                "No safe conversations found",
                "No safe conversation rows are available right now.",
            ),
        )


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

    def test_pinned_row_gets_pinned_label(self):
        item = _item(1)
        key = conversation_picker_identity(item)
        row = to_conversation_picker_rows([item], pinned_keys=[key])[0]
        self.assertTrue(row.pinned)
        self.assertEqual(row.suffix, "  Pinned")

    def test_structural_identity_survives_geometry_reflow(self):
        original = ConversationItem(
            100, 200, "Alice", 0, 100, 300, 150,
            runtime_id=(1, 42),
            control_identity=("ListItem", "row", "uia"),
        )
        moved = ConversationItem(
            100, 200, "Alice", 80, 500, 400, 560,
            runtime_id=(1, 42),
            control_identity=("ListItem", "alice", "row", "uia"),
        )
        self.assertEqual(conversation_picker_identity(original), conversation_picker_identity(moved))

    def test_runtime_identity_is_stable_when_display_name_changes(self):
        original = ConversationItem(
            100, 200, "general", 0, 100, 300, 150,
            runtime_id=(9, 9),
            control_identity=("ListItem", "row", "uia"),
        )
        renamed = ConversationItem(
            100, 200, "general renamed", 0, 100, 300, 150,
            runtime_id=(9, 9),
            control_identity=("ListItem", "same", "row", "uia"),
        )
        self.assertEqual(
            conversation_picker_identity(original),
            conversation_picker_identity(renamed),
        )

    def test_runtime_identity_ignores_ancestor_reflow(self):
        original = ConversationItem(
            100, 200, "general", 0, 100, 300, 150,
            runtime_id=(9, 9),
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        moved = ConversationItem(
            100, 200, "general", 0, 500, 300, 550,
            runtime_id=(9, 9),
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-b", "uia"),
        )
        self.assertEqual(
            conversation_picker_identity(original),
            conversation_picker_identity(moved),
        )

    def test_structural_identity_is_stable_when_display_name_changes(self):
        original = ConversationItem(
            100, 200, "general", 0, 100, 300, 150,
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        renamed = ConversationItem(
            100, 200, "general renamed", 0, 100, 300, 150,
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        self.assertEqual(
            conversation_picker_identity(original),
            conversation_picker_identity(renamed),
        )

    def test_container_identity_disambiguates_duplicate_structural_rows(self):
        first = ConversationItem(
            100, 200, "general", 0, 100, 300, 150,
            runtime_id=None,
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-a", "uia"),
        )
        second = ConversationItem(
            100, 200, "general", 0, 160, 300, 210,
            runtime_id=None,
            control_identity=("ListItem", "same", "row", "uia"),
            container_identity=("ancestor1", "Pane", "workspace-b", "uia"),
        )
        self.assertNotEqual(
            conversation_picker_identity(first),
            conversation_picker_identity(second),
        )

    def test_geometry_remains_fallback_when_structural_identity_is_missing(self):
        first = _item(1)
        moved = ConversationItem(
            100, 200, first.name, 5, first.top, first.right + 20, first.bottom,
        )
        self.assertNotEqual(conversation_picker_identity(first), conversation_picker_identity(moved))

    def test_picker_merges_pinned_then_recent_then_live_and_deduplicates(self):
        pinned = _item(1)
        recent = _item(2)
        duplicate_live = _item(1)
        live = _item(3)
        catalog, recent_keys, pinned_keys = ConversationPicker._merge_catalog(
            (pinned,), (recent,), (duplicate_live, live)
        )
        self.assertEqual([item.name for item in catalog], ["Chat 1", "Chat 2", "Chat 3"])
        self.assertIn(conversation_picker_identity(recent), recent_keys)
        self.assertIn(conversation_picker_identity(pinned), pinned_keys)

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
