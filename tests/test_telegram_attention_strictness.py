import unittest
from types import SimpleNamespace

from floatingbar.conversation_attention import AttentionState
from floatingbar.telegram_attention import telegram_badge_attention


class TelegramAttentionStrictnessTests(unittest.TestCase):
    def test_positive_item_status_is_unread(self):
        item = SimpleNamespace(element_info=SimpleNamespace(item_status="3"))
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNREAD)

    def test_class_name_unread_is_not_sufficient_evidence(self):
        item = SimpleNamespace(
            element_info=SimpleNamespace(item_status="0", class_name="Unread")
        )
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNKNOWN)

    def test_automation_id_unread_is_not_sufficient_evidence(self):
        item = SimpleNamespace(
            element_info=SimpleNamespace(item_status="0", automation_id="Unread")
        )
        result = telegram_badge_attention(item)
        self.assertEqual(result.state, AttentionState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
