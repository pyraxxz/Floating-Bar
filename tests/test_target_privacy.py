import unittest
from unittest.mock import patch

from floatingbar.target import TelegramNotFound, TelegramTarget


class TargetPrivacyTests(unittest.TestCase):
    def test_compose_tree_error_does_not_expose_raw_exception_text(self):
        target = TelegramTarget()
        target._hwnd = 100
        target._pid = 200

        with patch.object(target, "_window", side_effect=RuntimeError("private UI content")):
            with self.assertRaises(TelegramNotFound) as raised:
                target.compose_box()

        self.assertEqual(
            str(raised.exception),
            "Could not read Telegram's window tree safely.",
        )
        self.assertIsInstance(raised.exception.__cause__, RuntimeError)
        self.assertEqual(str(raised.exception.__cause__), "private UI content")


if __name__ == "__main__":
    unittest.main()
