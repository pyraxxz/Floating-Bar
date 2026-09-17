import unittest
from types import SimpleNamespace

from floatingbar.app_verification import (
    is_chat_compose_verification,
    is_terminal_input_verification,
    registry_validation_errors,
    verification_contract,
)


class AppVerificationContractTests(unittest.TestCase):
    def test_each_supported_chat_has_its_own_contract(self):
        expected = {
            "telegram": "telegram-compose-clear",
            "whatsapp": "whatsapp-compose-clear",
            "discord": "discord-compose-clear",
            "slack": "slack-compose-clear",
            "teams": "teams-compose-clear",
        }
        for key, mode in expected.items():
            with self.subTest(key=key):
                spec = SimpleNamespace(key=key, verification_mode=mode)
                contract = verification_contract(spec)
                self.assertIsNotNone(contract)
                self.assertEqual(contract.mode, mode)
                self.assertEqual(contract.family, "chat-compose-clear")
                self.assertTrue(is_chat_compose_verification(spec))

    def test_terminal_contract_covers_all_terminal_adapters(self):
        for key in ("terminal", "cmd", "powershell"):
            with self.subTest(key=key):
                spec = SimpleNamespace(key=key, verification_mode="terminal-input-clear")
                contract = verification_contract(spec)
                self.assertIsNotNone(contract)
                self.assertEqual(contract.family, "terminal-input-clear")
                self.assertTrue(is_terminal_input_verification(spec))

    def test_wrong_app_key_cannot_borrow_another_apps_contract(self):
        spec = SimpleNamespace(
            key="discord",
            verification_mode="whatsapp-compose-clear",
        )
        self.assertIsNone(verification_contract(spec))
        self.assertFalse(is_chat_compose_verification(spec))

    def test_generic_and_unknown_contracts_fail_closed(self):
        for spec in (
            SimpleNamespace(key="generic:editor", verification_mode="unverified"),
            SimpleNamespace(key="future", verification_mode="not-supported"),
            None,
        ):
            with self.subTest(spec=spec):
                self.assertIsNone(verification_contract(spec))
                self.assertFalse(is_chat_compose_verification(spec))
                self.assertFalse(is_terminal_input_verification(spec))

    def test_registry_contracts_are_structurally_valid(self):
        specs = (
            SimpleNamespace(key="telegram", verification_mode="telegram-compose-clear"),
            SimpleNamespace(key="whatsapp", verification_mode="whatsapp-compose-clear"),
            SimpleNamespace(key="discord", verification_mode="discord-compose-clear"),
            SimpleNamespace(key="slack", verification_mode="slack-compose-clear"),
            SimpleNamespace(key="teams", verification_mode="teams-compose-clear"),
            SimpleNamespace(key="terminal", verification_mode="terminal-input-clear"),
            SimpleNamespace(key="cmd", verification_mode="terminal-input-clear"),
            SimpleNamespace(key="powershell", verification_mode="terminal-input-clear"),
        )
        self.assertEqual(registry_validation_errors(specs), ())

    def test_registry_rejects_wrong_concrete_contract(self):
        specs = (
            SimpleNamespace(key="discord", verification_mode="whatsapp-compose-clear"),
        )
        errors = registry_validation_errors(specs)
        self.assertIn(
            "verification contract mismatch: discord/whatsapp-compose-clear",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
