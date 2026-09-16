import unittest

from floatingbar.app_adapters import adapter_for_process, is_actionable_process


class AppAdapterRegistryTests(unittest.TestCase):
    def test_process_aliases_resolve_to_same_adapter(self):
        self.assertEqual(adapter_for_process("WT.EXE").key, "terminal")
        self.assertEqual(adapter_for_process("windowsterminal.exe").key, "terminal")
        self.assertEqual(adapter_for_process("teams.exe").key, "teams")
        self.assertEqual(adapter_for_process("MS-TEAMS.EXE").key, "teams")

    def test_capability_metadata_describes_background_contract(self):
        telegram = adapter_for_process("telegram.exe")
        terminal = adapter_for_process("wt.exe")

        self.assertEqual(telegram.action, "Chats")
        self.assertEqual(telegram.chat_picker, "telegram")
        self.assertEqual(telegram.target_mode, "telegram-compose")
        self.assertEqual(telegram.submit_mode, "telegram-send")
        self.assertEqual(telegram.verification_mode, "typed")

        self.assertEqual(terminal.action, "Type")
        self.assertIsNone(terminal.chat_picker)
        self.assertEqual(terminal.target_mode, "terminal-structured-focus")
        self.assertEqual(terminal.submit_mode, "enter")
        self.assertEqual(terminal.verification_mode, "unverified")

    def test_unknown_and_non_adapter_processes_fail_closed(self):
        self.assertIsNone(adapter_for_process("unknown.exe"))
        self.assertFalse(is_actionable_process("notepad.exe"))
        self.assertFalse(is_actionable_process("unknown.exe"))
        self.assertTrue(is_actionable_process("discord.exe"))


if __name__ == "__main__":
    unittest.main()
