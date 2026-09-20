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

    def test_live_apps_reserve_space_when_history_would_crowd_picker(self):
        pinned = tuple(
            PickerItem(
                index,
                100 + index,
                f"Pinned {index}",
                True,
                False,
                "demo.exe",
                "demo",
                False,
                True,
            )
            for index in range(1, 4)
        )
        recent = tuple(
            PickerItem(
                10 + index,
                200 + index,
                f"Recent {index}",
                True,
                False,
                "demo.exe",
                "demo",
                True,
                False,
            )
            for index in range(1, 3)
        )
        live = tuple(
            PickerItem(
                20 + index,
                300 + index,
                label,
                True,
                False,
                process,
                key,
            )
            for index, (label, process, key) in enumerate(
                (
                    ("Telegram", "telegram.exe", "telegram"),
                    ("Slack", "slack.exe", "slack"),
                    ("Terminal", "wt.exe", "terminal"),
                    ("Notepad", "notepad.exe", "generic:notepad"),
                ),
                start=1,
            )
        )

        merged = BackgroundAppPicker._merge_items(pinned, recent, live)

        self.assertEqual(
            [item.label for item in merged],
            ["Pinned 1", "Pinned 2", "Pinned 3", "Telegram", "Slack", "Terminal"],
        )
        self.assertEqual(
            len([item for item in merged if item.label in {"Telegram", "Slack", "Terminal", "Notepad"}]),
            3,
        )

    def test_duplicate_window_ordinals_follow_stable_identity_not_enumeration_order(self):
        first_window = SimpleNamespace(
            hwnd=200,
            pid=20,
            process_name="code.exe",
            process_start=2000,
            label="code.exe",
            foreground=False,
        )
        second_window = SimpleNamespace(
            hwnd=100,
            pid=20,
            process_name="code.exe",
            process_start=2000,
            label="code.exe",
            foreground=True,
        )

        original = to_picker_items((first_window, second_window))
        reordered = to_picker_items((second_window, first_window))

        original_by_hwnd = {item.hwnd: item.label for item in original}
        reordered_by_hwnd = {item.hwnd: item.label for item in reordered}

        self.assertEqual(original_by_hwnd, reordered_by_hwnd)
        self.assertEqual(reordered_by_hwnd[100], "VS Code 1")
        self.assertEqual(reordered_by_hwnd[200], "VS Code 2")

    def test_recent_items_are_shown_after_pinned_items_and_duplicates_are_removed(self):
        pinned = PickerItem(10, 20, "Telegram", True, False, "telegram.exe", "telegram", False, True)
        recent = PickerItem(10, 20, "Telegram", True, False, "telegram.exe", "telegram", True, False)
        live = PickerItem(11, 21, "Slack", True, False, "slack.exe", "slack")
        merged = BackgroundAppPicker._merge_items((pinned,), (recent,), (live,))
        self.assertEqual([item.label for item in merged], ["Telegram", "Slack"])
        self.assertTrue(merged[0].pinned)
        self.assertFalse(merged[0].recent)
        self.assertFalse(merged[1].pinned)


    def test_live_snapshot_ignores_enumeration_order_but_tracks_meaningful_changes(self):
        first = [
            SimpleNamespace(
                hwnd=12,
                pid=20,
                process_start=200,
                process_name="telegram.exe",
                window_class="TelegramMainWindow",
                area=50000,
                foreground=False,
            ),
            SimpleNamespace(
                hwnd=11,
                pid=19,
                process_start=190,
                process_name="slack.exe",
                window_class="SlackMainWindow",
                area=60000,
                foreground=False,
            ),
        ]
        reordered = list(reversed(first))
        self.assertEqual(
            BackgroundAppPicker._live_snapshot_for(first),
            BackgroundAppPicker._live_snapshot_for(reordered),
        )

        resized = [
            SimpleNamespace(
                hwnd=12,
                pid=20,
                process_start=200,
                process_name="telegram.exe",
                window_class="TelegramMainWindow",
                area=50001,
                foreground=False,
            ),
            first[1],
        ]
        self.assertNotEqual(
            BackgroundAppPicker._live_snapshot_for(first),
            BackgroundAppPicker._live_snapshot_for(resized),
        )

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

    def test_live_refresh_rebuilds_when_pointer_is_inside_picker_popup(self):
        owner = SimpleNamespace(
            after=lambda _delay, _callback: "refresh-job",
            after_cancel=lambda _job: None,
        )
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker.window = object()
        picker._hover = HoverState(owner=False, popup=True, actions=False)
        picker._live_refresh_job = None
        picker._live_snapshot = ((10, 20, 30, "notepad.exe", "Edit", False),)
        picker.refresh = lambda: [
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

        picker.show.assert_called_once_with(preserve_popup_hover=True)
        picker._schedule_live_refresh.assert_not_called()

    def test_live_refresh_schedules_while_pointer_is_inside_picker_popup(self):
        owner = SimpleNamespace(
            after=lambda _delay, _callback: "refresh-job",
            after_cancel=lambda _job: None,
        )
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker.window = object()
        picker._hover = HoverState(owner=False, popup=True, actions=False)
        picker._live_refresh_job = None

        picker._schedule_live_refresh()

        self.assertEqual(picker._live_refresh_job, "refresh-job")

    def test_live_refresh_preserves_focused_app_identity(self):
        focused_row = object()
        owner = SimpleNamespace(
            after=lambda _delay, _callback: "refresh-job",
            after_cancel=lambda _job: None,
            focus_get=lambda: focused_row,
        )
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker.window = object()
        picker._hover = HoverState(owner=True, popup=False, actions=False)
        picker._live_refresh_job = None
        picker._live_snapshot = ((10, 20, 30, "notepad.exe", "Edit", False),)
        picker._row_identity_by_widget = {focused_row: (10, 20, 30)}
        picker.refresh = lambda: [
            SimpleNamespace(
                hwnd=10,
                pid=20,
                process_name="notepad.exe",
                process_start=30,
                window_class="Edit",
                foreground=True,
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

        picker.show.assert_called_once_with(
            preserve_focus_key=(10, 20, 30),
        )
        picker._schedule_live_refresh.assert_not_called()

    def test_hide_clears_live_row_identity_cache(self):
        owner = SimpleNamespace(
            after_cancel=lambda _job: None,
        )
        picker = BackgroundAppPicker.__new__(BackgroundAppPicker)
        picker.owner = owner
        picker.window = None
        picker._show_job = None
        picker._hide_job = None
        picker._live_refresh_job = None
        picker._action_hide_job = None
        picker._action_window = None
        picker._action_item = None
        picker._row_identity_by_widget = {object(): (10, 20, 30)}
        picker._hover = HoverState(popup=True)

        picker.hide()

        self.assertEqual(picker._row_identity_by_widget, {})

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
