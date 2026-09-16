import unittest
from types import SimpleNamespace

from floatingbar.conversation_attention import AttentionState
from floatingbar.telegram_attention import telegram_badge_attention


class TelegramAttentionTests(unittest.TestCase):
    def test_positive_numeric_item_status_is_unread(self):
        item = SimpleNamespace(element_info=SimpleNamespace(item_status="3"))
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNREAD)
        self.assertEqual(result.source, "telegram-uia-badge")
        self.assertTrue(result.actionable)

    def test_zero_numeric_item_status_is_not_unread(self):
        item = SimpleNamespace(element_info=SimpleNamespace(item_status="0"))
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNKNOWN)
        self.assertFalse(result.actionable)

    def test_explicit_accessibility_unread_marker_is_supported(self):
        item = SimpleNamespace(
            element_info=SimpleNamespace(item_status="New messages")
        )
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNREAD)
        self.assertEqual(result.source, "telegram-uia-marker")

    def test_arbitrary_status_text_is_not_treated_as_unread(self):
        item = SimpleNamespace(
            element_info=SimpleNamespace(item_status="latest message preview")
        )
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNKNOWN)
        self.assertFalse(result.actionable)

    def test_missing_metadata_fails_closed(self):
        result = telegram_badge_attention(object())
        self.assertEqual(result.state, AttentionState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
