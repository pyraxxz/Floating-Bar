import unittest
from types import SimpleNamespace

from floatingbar.background_picker import PickerItem, to_picker_items


class BackgroundPickerTests(unittest.TestCase):
    def test_picker_keeps_process_identity_without_window_content(self):
        result = to_picker_items(
            [SimpleNamespace(
                hwnd=10, pid=20, process_name="telegram.exe",
                label="telegram.exe", foreground=True,
            )]
        )
        self.assertEqual(
            result,
            (PickerItem(10, 20, "Telegram", True, True, "telegram.exe"),),
        )

    def test_known_typing_apps_are_actionable(self):
        result = to_picker_items(
            [
                SimpleNamespace(
                    hwnd=10, pid=20, process_name="windowsterminal.exe",
                    label="windowsterminal.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=11, pid=21, process_name="notepad.exe",
                    label="notepad.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=12, pid=22, process_name="discord.exe",
                    label="discord.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=13, pid=23, process_name="slack.exe",
                    label="slack.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=14, pid=24, process_name="ms-teams.exe",
                    label="ms-teams.exe", foreground=False,
                ),
            ]
        )
        self.assertEqual(
            [item.label for item in result],
            ["Terminal", "Notepad", "Discord", "Slack", "Microsoft Teams"],
        )
        self.assertEqual([item.actionable for item in result], [True, False, True, True, True])

    def test_non_submit_editor_is_discovery_only_but_still_labeled(self):
        result = to_picker_items(
            [SimpleNamespace(
                hwnd=10, pid=20, process_name="notepad.exe",
                label="notepad.exe", foreground=False,
            )]
        )
        self.assertEqual(result[0].label, "Notepad")
        self.assertFalse(result[0].actionable)

    def test_known_chat_and_terminal_aliases_share_actionability(self):
        result = to_picker_items(
            [
                SimpleNamespace(
                    hwnd=10, pid=20, process_name="wt.exe",
                    label="wt.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=11, pid=21, process_name="teams.exe",
                    label="teams.exe", foreground=False,
                ),
                SimpleNamespace(
                    hwnd=12, pid=22, process_name="msteams.exe",
                    label="msteams.exe", foreground=False,
                ),
            ]
        )
        self.assertEqual(
            [item.label for item in result],
            ["Terminal", "Microsoft Teams", "Microsoft Teams"],
        )
        self.assertTrue(all(item.actionable for item in result))

    def test_unknown_process_has_title_free_human_label(self):
        result = to_picker_items(
            [SimpleNamespace(
                hwnd=10, pid=20, process_name="myeditor.exe",
                label="myeditor.exe", foreground=False,
            )]
        )
        self.assertEqual(result[0].label, "Myeditor")
        self.assertFalse(result[0].actionable)


if __name__ == "__main__":
    unittest.main()
