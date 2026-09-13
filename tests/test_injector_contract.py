import unittest

from floatingbar.hardening import HardenedTelegramInjector
from floatingbar.injector import TelegramInjector
from floatingbar.injector_contract import BackgroundInjector
from floatingbar.recovery import ScopeGuardedRecoveryInjector


class InjectorContractTests(unittest.TestCase):
    def test_base_telegram_injector_matches_contract(self):
        self.assertTrue(issubclass(TelegramInjector, BackgroundInjector))

    def test_hardened_injector_matches_contract(self):
        self.assertTrue(issubclass(HardenedTelegramInjector, BackgroundInjector))

    def test_scope_guarded_injector_matches_contract(self):
        self.assertTrue(issubclass(ScopeGuardedRecoveryInjector, BackgroundInjector))

    def test_contract_exposes_only_send_capability(self):
        annotations = getattr(BackgroundInjector.send, "__annotations__", {})
        self.assertEqual(annotations.get("text"), str)
        self.assertEqual(annotations.get("restore_hwnd"), int)
        self.assertEqual(annotations.get("return"), str)


if __name__ == "__main__":
    unittest.main()
