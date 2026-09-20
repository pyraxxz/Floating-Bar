import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from floatingbar.background_picker import (
    BackgroundAppPicker,
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


    def test_picker_carries_process_instance_identity(self):
        result = to_picker_items([
            SimpleNamespace(
                hwnd=10,
                pid=20,
                process_name="telegram.exe",
                label="telegram.exe",
                foreground=True,
                process_start=123,
            )
        ])
        self.assertEqual(result[0].process_start, 123)

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

    def test_non_actionable_live_windows_do_not_crowd_out_actionable_apps(self):
        unsupported = tuple(
            PickerItem(index, 100 + index, f"Unknown {index}", False, False, "unknown.exe")
            for index in range(1, 5)
        )
        actionable = (
            PickerItem(20, 200, "Telegram", True, False, "telegram.exe", "telegram"),
            PickerItem(21, 201, "Slack", True, False, "slack.exe", "slack"),
        )
        merged = BackgroundAppPicker._merge_items((), (), unsupported + actionable)
        self.assertEqual(
            [item.label for item in merged],
            ["Telegram", "Slack", "Unknown 1", "Unknown 2", "Unknown 3", "Unknown 4"],
        )
        self.assertTrue(all(item.actionable for item in merged[:2]))
        self.assertFalse(merged[-1].actionable)

    def test_non_actionable_row_explains_why_it_cannot_be_used(self):
        item = PickerItem(10, 20, "Calculator", False, False, "calculator.exe")
        self.assertEqual(action_for_item(item), "No safe input")

    def test_recent_items_are_shown_after_pinned_items_and_duplicates_are_removed(self):
        pinned = PickerItem(10, 20, "Telegram", True, False, "telegram.exe", "telegram", False, True)
        recent = PickerItem(10, 20, "Telegram", True, False, "telegram.exe", "telegram", True, False)
        live = PickerItem(11, 21, "Slack", True, False, "slack.exe", "slack")
        merged = BackgroundAppPicker._merge_items((pinned,), (recent,), (live,))
        self.assertEqual([item.label for item in merged], ["Telegram", "Slack"])
        self.assertTrue(merged[0].pinned)
        self.assertFalse(merged[0].recent)
        self.assertFalse(merged[1].pinned)


    def test_live_refresh_rebuilds_picker_when_new_app_appears(self):
        owner = SimpleNamespace(
            after=lambda _delay, _callback: "refresh-job",
            after_cancel=lambda _job: None,
        )
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker.window = object()
        picker._hover = HoverState(owner=True, popup=True)
        picker._live_refresh_job = None
        picker._live_snapshot = ((10, 20, 30, "notepad.exe", "Edit", False),)
        picker.refresh = lambda: [
            SimpleNamespace(
                hwnd=10,
                pid=20,
                process_name="notepad.exe",
                process_start=30,
                window_class="Edit",
                foreground=False,
            ),
            SimpleNamespace(
                hwnd=11,
                pid=21,
                process_name="telegram.exe",
                process_start=31,
                window_class="TelegramMainWindow",
                foreground=False,
            ),
        ]
        picker.show = Mock()
        picker._schedule_live_refresh = Mock()
        picker._refresh_open_picker()
        picker.show.assert_called_once_with()

    def test_action_hide_timer_is_replaced_when_hover_reenters(self):
        class Owner:
            def __init__(self):
                self.scheduled = []
                self.cancelled = []

            def after(self, delay, callback):
                token = f"job-{len(self.scheduled) + 1}"
                self.scheduled.append((token, delay, callback))
                return token

            def after_cancel(self, token):
                self.cancelled.append(token)

        owner = Owner()
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker._action_hide_job = None

        picker._schedule_action_hide()
        first = picker._action_hide_job
        picker._schedule_action_hide()
        second = picker._action_hide_job

        self.assertNotEqual(first, second)
        self.assertEqual(owner.cancelled, [first])
        self.assertEqual(second, "job-2")

    def test_hide_actions_cancels_pending_action_hide_timer(self):
        class Owner:
            def __init__(self):
                self.cancelled = []

            def after_cancel(self, token):
                self.cancelled.append(token)

        owner = Owner()
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker._action_hide_job = "job-17"
        picker._action_window = None
        picker._action_item = PickerItem(10, 20, "Slack", True, False, "slack.exe", "slack")
        picker._hover = HoverState(actions=True)

        picker._hide_actions()

        self.assertEqual(owner.cancelled, ["job-17"])
        self.assertIsNone(picker._action_hide_job)
        self.assertIsNone(picker._action_item)
        self.assertFalse(picker._hover.actions)


if __name__ == "__main__":
    unittest.main()
