import unittest

from floatingbar.target import TelegramTarget
from floatingbar.target_contract import BackgroundTarget
from floatingbar.transaction import TargetScope


class TargetContractTests(unittest.TestCase):
    def test_telegram_target_matches_background_target_contract(self):
        target = TelegramTarget()
        self.assertIsInstance(target, BackgroundTarget)

    def test_target_scope_is_tuple_compatible_and_named(self):
        scope = TargetScope(123, 456)
        self.assertTrue(scope.valid)
        self.assertEqual(scope, (123, 456))
        hwnd, pid = scope
        self.assertEqual(hwnd, 123)
        self.assertEqual(pid, 456)


if __name__ == "__main__":
    unittest.main()
