import unittest
from types import SimpleNamespace

from floatingbar.conversation_attention import (
    AttentionState,
    ConversationAttention,
    safe_detect,
    selected_attention,
)


class ConversationAttentionTests(unittest.TestCase):
    def test_selected_attention_uses_only_selection_semantics(self):
        item = SimpleNamespace(is_selected=lambda: True)
        result = selected_attention(item)
        self.assertEqual(result.state, AttentionState.SELECTED)
        self.assertEqual(result.source, "uia-selection")
        self.assertFalse(result.actionable)

    def test_unselected_row_is_unknown_without_app_specific_detector(self):
        item = SimpleNamespace(is_selected=lambda: False)
        result = safe_detect(item, None)
        self.assertEqual(result.state, AttentionState.UNKNOWN)
        self.assertEqual(result.source, "none")
        self.assertFalse(result.actionable)

    def test_explicit_unread_detector_is_preserved(self):
        item = object()
        expected = ConversationAttention(AttentionState.UNREAD, "structural-badge")
        result = safe_detect(item, lambda _item: expected)
        self.assertEqual(result, expected)
        self.assertTrue(result.actionable)

    def test_bad_detector_result_fails_closed(self):
        result = safe_detect(object(), lambda _item: "unread")
        self.assertEqual(result.state, AttentionState.UNKNOWN)
        self.assertFalse(result.actionable)

    def test_detector_exception_fails_closed(self):
        def detector(_item):
            raise RuntimeError("ambiguous")

        result = safe_detect(object(), detector)
        self.assertEqual(result.state, AttentionState.UNKNOWN)
        self.assertFalse(result.actionable)


if __name__ == "__main__":
    unittest.main()
