import unittest
from types import SimpleNamespace

from floatingbar.app_verification import (
    is_chat_compose_verification,
    is_terminal_input_verification,
    registry_validation_errors,
    verification_contract,
    verification_proof_kind,
)


class AppVerificationContractTests(unittest.TestCase):
    def _spec(self, key, mode):
        defaults = {
            "telegram": ("telegram-compose", "telegram-send"),
            "whatsapp": ("chat-structured-focus", "enter"),
            "discord": ("chat-structured-focus", "enter"),
            "slack": ("chat-structured-focus", "enter"),
            "teams": ("chat-structured-focus", "enter"),
            "terminal": ("terminal-structured-focus", "enter"),
            "cmd": ("terminal-structured-focus", "enter"),
            "powershell": ("terminal-structured-focus", "enter"),
        }
        target_mode, submit_mode = defaults[key]
        return SimpleNamespace(
            key=key,
            verification_mode=mode,
            target_mode=target_mode,
            submit_mode=submit_mode,
        )

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
                spec = self._spec(key, mode)
                contract = verification_contract(spec)
                self.assertIsNotNone(contract)
                self.assertEqual(contract.mode, mode)
                self.assertEqual(contract.family, "chat-compose-clear")
                self.assertTrue(is_chat_compose_verification(spec))
                self.assertEqual(verification_proof_kind(spec), "input-acceptance")

    def test_terminal_contract_covers_all_terminal_adapters(self):
        for key in ("terminal", "cmd", "powershell"):
            with self.subTest(key=key):
                spec = self._spec(key, "terminal-input-clear")
                contract = verification_contract(spec)
                self.assertIsNotNone(contract)
                self.assertEqual(contract.family, "terminal-input-clear")
                self.assertTrue(is_terminal_input_verification(spec))
                self.assertEqual(verification_proof_kind(spec), "input-acceptance")

    def test_contract_rejects_unsupported_proof_scope(self):
        from floatingbar.app_verification import VerificationContract

        spec = self._spec("discord", "discord-compose-clear")
        contract = verification_contract(spec)
        self.assertEqual(contract.proof_kind, "input-acceptance")

        invalid = VerificationContract(
            mode="future",
            family="future",
            adapter_keys=frozenset({"discord"}),
            target_mode="chat-structured-focus",
            submit_mode="enter",
            proof_kind="terminal-output",
        )
        self.assertNotIn(invalid.proof_kind, {"input-acceptance", "semantic-delivery", "semantic-execution"})

    def test_wrong_app_key_cannot_borrow_another_apps_contract(self):
        spec = self._spec("discord", "whatsapp-compose-clear")
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
        specs = tuple(
            self._spec(key, mode)
            for key, mode in (
                ("telegram", "telegram-compose-clear"),
                ("whatsapp", "whatsapp-compose-clear"),
                ("discord", "discord-compose-clear"),
                ("slack", "slack-compose-clear"),
                ("teams", "teams-compose-clear"),
                ("terminal", "terminal-input-clear"),
                ("cmd", "terminal-input-clear"),
                ("powershell", "terminal-input-clear"),
            )
        )
        self.assertEqual(registry_validation_errors(specs), ())

    def test_registry_rejects_wrong_concrete_contract(self):
        specs = (self._spec("discord", "whatsapp-compose-clear"),)
        errors = registry_validation_errors(specs)
        self.assertIn(
            "verification contract mismatch: discord/whatsapp-compose-clear",
            errors,
        )

    def test_registry_rejects_target_policy_drift(self):
        spec = self._spec("whatsapp", "whatsapp-compose-clear")
        spec.target_mode = "focused-child"
        errors = registry_validation_errors((spec,))
        self.assertIn(
            "verification target contract mismatch: whatsapp/focused-child",
            errors,
        )

    def test_registry_rejects_submit_policy_drift(self):
        spec = self._spec("teams", "teams-compose-clear")
        spec.submit_mode = "telegram-send"
        errors = registry_validation_errors((spec,))
        self.assertIn(
            "verification submit contract mismatch: teams/telegram-send",
            errors,
        )

    def test_verification_predicate_fails_closed_when_routing_drifts(self):
        spec = self._spec("discord", "discord-compose-clear")
        spec.target_mode = "focused-child"
        self.assertFalse(is_chat_compose_verification(spec))


if __name__ == "__main__":
    unittest.main()
