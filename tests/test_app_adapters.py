import unittest

from floatingbar.app_adapters import (
    actionable_adapter_for_process,
    adapter_for_process,
    attention_capability,
    generic_adapter_for_process,
    is_actionable_process,
)


class AppAdapterRegistryTests(unittest.TestCase):
    def test_process_aliases_resolve_to_same_adapter(self):
        self.assertEqual(adapter_for_process("WT.EXE").key, "terminal")
        self.assertEqual(adapter_for_process("windowsterminal.exe").key, "terminal")
        self.assertEqual(adapter_for_process("WindowsTerminalPreview.EXE").key, "terminal")
        self.assertEqual(adapter_for_process("conhost.exe").key, "terminal")
        self.assertEqual(adapter_for_process("teams.exe").key, "teams")
        self.assertEqual(adapter_for_process("MS-TEAMS.EXE").key, "teams")
        self.assertEqual(adapter_for_process("PWSh.EXE").key, "powershell")

    def test_capability_metadata_describes_background_contract(self):
        telegram = adapter_for_process("telegram.exe")
        terminal = adapter_for_process("wt.exe")

        self.assertEqual(telegram.action, "Chats")
        self.assertEqual(telegram.chat_picker, "telegram")
        self.assertEqual(telegram.target_mode, "telegram-compose")
        self.assertEqual(telegram.submit_mode, "telegram-send")
        self.assertEqual(telegram.verification_mode, "compose-clear")
        self.assertEqual(telegram.conversation_attention_mode, "telegram-badge")
        self.assertEqual(attention_capability(telegram), "telegram-badge")

        self.assertEqual(terminal.action, "Type")
        self.assertIsNone(terminal.chat_picker)
        self.assertEqual(terminal.target_mode, "terminal-structured-focus")
        self.assertEqual(terminal.submit_mode, "enter")
        self.assertEqual(terminal.verification_mode, "unverified")
        self.assertEqual(terminal.conversation_attention_mode, "none")
        self.assertEqual(attention_capability(terminal), "none")

    def test_supported_chat_apps_expose_conversation_picker_and_verification(self):
        expected_verification = {
            "whatsapp.exe": "compose-clear",
            "discord.exe": "compose-clear",
            "slack.exe": "compose-clear",
            "teams.exe": "compose-clear",
        }
        for process_name, expected_mode in expected_verification.items():
            spec = adapter_for_process(process_name)
            self.assertIsNotNone(spec)
            self.assertEqual(spec.action, "Chats")
            self.assertEqual(spec.chat_picker, "conversations")
            self.assertEqual(spec.verification_mode, expected_mode)
            self.assertEqual(spec.conversation_attention_mode, "none")
            self.assertEqual(attention_capability(spec), "none")
            self.assertTrue(spec.supports_background_type)

    def test_unknown_process_gets_generic_type_capability(self):
        spec = generic_adapter_for_process("my-editor.exe")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.key, "generic:my-editor")
        self.assertEqual(spec.action, "Type")
        self.assertEqual(spec.submit_mode, "enter")
        self.assertEqual(spec.verification_mode, "unverified")
        self.assertIsNone(spec.chat_picker)
        self.assertEqual(actionable_adapter_for_process("my-editor.exe"), spec)
        self.assertTrue(is_actionable_process("my-editor.exe"))

    def test_generic_factory_rejects_malformed_process_names(self):
        self.assertIsNone(generic_adapter_for_process(""))
        self.assertIsNone(generic_adapter_for_process("editor"))
        self.assertIsNone(generic_adapter_for_process("editor\\other.exe"))
        self.assertEqual(attention_capability(None), "none")

    def test_unknown_adapter_lookup_remains_unknown(self):
        self.assertIsNone(adapter_for_process("unknown.exe"))
        self.assertTrue(is_actionable_process("unknown.exe"))
        self.assertIsNotNone(actionable_adapter_for_process("unknown.exe"))
        self.assertTrue(is_actionable_process("discord.exe"))


if __name__ == "__main__":
    unittest.main()
