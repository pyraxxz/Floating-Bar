import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
            ]
        )
        self.assertEqual([item.label for item in result], ["Terminal", "Notepad"])
        self.assertEqual([item.actionable for item in result], [True, False])
        self.assertEqual(result[0].process_name, "windowsterminal.exe")

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
