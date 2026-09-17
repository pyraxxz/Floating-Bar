import unittest
from types import SimpleNamespace

from floatingbar.background_picker import (
    HoverState,
    PickerItem,
    action_for_item,
    to_picker_items,
)


class BackgroundPickerTests(unittest.TestCase):
    def test_hover_state_stays_open_across_owner_to_popup_transition(self):
        state = HoverState()
        state.enter_owner()
        state.enter_popup()
        state.leave_owner()
        self.assertFalse(state.outside)
        state.leave_popup()
        self.assertTrue(state.outside)

    def test_hover_state_stays_open_across_popup_to_actions_transition(self):
        state = HoverState()
        state.enter_popup()
        state.enter_actions()
        state.leave_popup()
        self.assertFalse(state.outside)
        state.leave_actions()
        self.assertTrue(state.outside)

    def test_hover_state_is_outside_only_after_all_regions_are_left(self):
        state = HoverState(owner=True, popup=True, actions=True)
        state.leave_owner()
        state.leave_popup()
        self.assertFalse(state.outside)
        state.leave_actions()
        self.assertTrue(state.outside)

    def test_hover_state_reentry_is_idempotent(self):
        state = HoverState()
        state.enter_owner()
        state.enter_owner()
        state.leave_popup()
        self.assertFalse(state.outside)
        state.leave_owner()
        self.assertTrue(state.outside)

    def test_picker_keeps_process_identity_without_window_content(self):
        result = to_picker_items(
            [SimpleNamespace(
                hwnd=10, pid=20, process_name="telegram.exe",
                label="telegram.exe", foreground=True,
            )]
        )
        self.assertEqual(
            result,
            (PickerItem(10, 20, "Telegram", True, True, "telegram.exe", "telegram"),),
        )

    def test_multiple_same_app_windows_get_content_free_ordinals(self):
        result = to_picker_items([
            SimpleNamespace(hwnd=10, pid=20, process_name="telegram.exe", label="telegram.exe", foreground=True),
            SimpleNamespace(hwnd=11, pid=21, process_name="telegram.exe", label="telegram.exe", foreground=False),
        ])
        self.assertEqual([item.label for item in result], ["Telegram 1", "Telegram 2"])
        self.assertEqual([item.hwnd for item in result], [10, 11])
        self.assertEqual([item.adapter_key for item in result], ["telegram", "telegram"])

    def test_multiple_alias_windows_share_the_same_safe_label_ordinal(self):
        result = to_picker_items([
            SimpleNamespace(hwnd=10, pid=20, process_name="teams.exe", label="teams.exe", foreground=False),
            SimpleNamespace(hwnd=11, pid=21, process_name="ms-teams.exe", label="ms-teams.exe", foreground=False),
        ])
        self.assertEqual([item.label for item in result], ["Microsoft Teams 1", "Microsoft Teams 2"])

    def test_known_typing_apps_are_actionable(self):
        result = to_picker_items(
            [
                SimpleNamespace(hwnd=10, pid=20, process_name="windowsterminal.exe", label="windowsterminal.exe", foreground=False),
                SimpleNamespace(hwnd=11, pid=21, process_name="notepad.exe", label="notepad.exe", foreground=False),
                SimpleNamespace(hwnd=12, pid=22, process_name="discord.exe", label="discord.exe", foreground=False),
                SimpleNamespace(hwnd=13, pid=23, process_name="slack.exe", label="slack.exe", foreground=False),
                SimpleNamespace(hwnd=14, pid=24, process_name="ms-teams.exe", label="ms-teams.exe", foreground=False),
            ]
        )
        self.assertEqual([item.label for item in result], ["Terminal", "Notepad", "Discord", "Slack", "Microsoft Teams"])
        self.assertEqual([item.actionable for item in result], [True, True, True, True, True])
        self.assertEqual([item.adapter_key for item in result], ["terminal", "generic:notepad", "discord", "slack", "teams"])

    def test_generic_editor_is_actionable_but_still_structurally_gated_later(self):
        result = to_picker_items([
            SimpleNamespace(hwnd=10, pid=20, process_name="notepad.exe", label="notepad.exe", foreground=False)
        ])
        self.assertEqual(result[0].label, "Notepad")
        self.assertTrue(result[0].actionable)
        self.assertEqual(result[0].adapter_key, "generic:notepad")
        self.assertEqual(action_for_item(result[0]), "Type")

    def test_known_chat_and_terminal_aliases_share_actionability(self):
        result = to_picker_items([
            SimpleNamespace(hwnd=10, pid=20, process_name="wt.exe", label="wt.exe", foreground=False),
            SimpleNamespace(hwnd=11, pid=21, process_name="teams.exe", label="teams.exe", foreground=False),
            SimpleNamespace(hwnd=12, pid=22, process_name="msteams.exe", label="msteams.exe", foreground=False),
        ])
        self.assertEqual([item.label for item in result], ["Terminal", "Microsoft Teams 1", "Microsoft Teams 2"])
        self.assertEqual([item.adapter_key for item in result], ["terminal", "teams", "teams"])
        self.assertTrue(all(item.actionable for item in result))

    def test_action_menu_label_distinguishes_telegram(self):
        telegram = PickerItem(10, 20, "Telegram", True, False, "telegram.exe", "telegram")
        terminal = PickerItem(11, 21, "Terminal", True, False, "wt.exe", "terminal")
        editor = PickerItem(12, 22, "Notepad", True, False, "notepad.exe", "generic:notepad")
        self.assertEqual(action_for_item(telegram), "Chats")
        self.assertEqual(action_for_item(terminal), "Type")
        self.assertEqual(action_for_item(editor), "Type")

    def test_unknown_process_has_title_free_generic_type_label(self):
        result = to_picker_items([SimpleNamespace(hwnd=10, pid=20, process_name="myeditor.exe", label="myeditor.exe", foreground=False)])
        self.assertEqual(result[0].label, "Myeditor")
        self.assertTrue(result[0].actionable)
        self.assertEqual(result[0].adapter_key, "generic:myeditor")
        self.assertEqual(action_for_item(result[0]), "Type")


if __name__ == "__main__":
    unittest.main()
