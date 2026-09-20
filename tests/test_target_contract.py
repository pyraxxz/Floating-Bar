import unittest

from floatingbar.bound_target import BoundTelegramTarget
from floatingbar.generic_target import BackgroundTypingTarget
from floatingbar.target import TelegramTarget
from floatingbar.target_contract import BackgroundTarget
from floatingbar.transaction import TargetScope


class TargetContractTests(unittest.TestCase):
    def test_bound_telegram_target_matches_background_target_contract(self):
        target = BoundTelegramTarget(TelegramTarget())
        self.assertIsInstance(target, BackgroundTarget)

    def test_background_target_contract_requires_explicit_release(self):
        target = BoundTelegramTarget(TelegramTarget())
        self.assertTrue(callable(target.release))

    def test_generic_background_target_matches_background_target_contract(self):
        target = BackgroundTypingTarget(123, 456)
        self.assertIsInstance(target, BackgroundTarget)

    def test_background_target_scope_guard_remains_available_outside_minimum_contract(self):
        target = TelegramTarget()
        self.assertTrue(hasattr(target, "scope_matches"))
        self.assertTrue(callable(target.scope_matches))

    def test_target_scope_is_tuple_compatible_and_named(self):
        scope = TargetScope(123, 456)
        self.assertTrue(scope.valid)
        self.assertEqual(scope, (123, 456))
        hwnd, pid = scope
        self.assertEqual(hwnd, 123)
        self.assertEqual(pid, 456)


if __name__ == "__main__":
    unittest.main()
