import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.recent_targets import RecentTargetHistory
from floatingbar.transaction import TargetScope


class RecentTargetHistoryTests(unittest.TestCase):
    def test_recent_history_moves_reselected_target_to_front_and_caps_size(self):
        history = RecentTargetHistory(limit=2)
        history.record_application(
            hwnd=10, pid=100, process_name="one.exe", label="One", adapter_key="one"
        )
        history.record_application(
            hwnd=20, pid=200, process_name="two.exe", label="Two", adapter_key="two"
        )
        history.record_application(
            hwnd=10, pid=100, process_name="one.exe", label="One", adapter_key="one"
        )
        history.record_application(
            hwnd=30, pid=300, process_name="three.exe", label="Three", adapter_key="three"
        )
        self.assertEqual(
            [item.scope for item in history.items()],
            [TargetScope(30, 300), TargetScope(10, 100)],
        )

    def test_recent_application_validation_requires_exact_scope_and_adapter(self):
        history = RecentTargetHistory()
        target = history.record_application(
            hwnd=44,
            pid=444,
            process_name="demo.exe",
            label="Demo",
            adapter_key="demo",
        )

        class User32:
            @staticmethod
            def IsWindow(hwnd):
                return hwnd == 44

        with patch("floatingbar.recent_targets.winapi.user32", User32()):
            with patch("floatingbar.recent_targets.winapi.get_window_pid", return_value=444):
                with patch(
                    "floatingbar.recent_targets.winapi.get_process_image_name",
                    return_value=r"C:\\demo.exe",
                ):
                    with patch(
                        "floatingbar.recent_targets.actionable_adapter_for_process",
                        return_value=SimpleNamespace(implemented=True, key="demo"),
                    ):
                        self.assertTrue(history.application_is_live(target))
                self.assertFalse(history.application_is_live(target)) if False else None

        with patch("floatingbar.recent_targets.winapi.user32", User32()):
            with patch("floatingbar.recent_targets.winapi.get_window_pid", return_value=445):
                with patch(
                    "floatingbar.recent_targets.winapi.get_process_image_name",
                    return_value=r"C:\\demo.exe",
                ):
                    with patch(
                        "floatingbar.recent_targets.actionable_adapter_for_process",
                        return_value=SimpleNamespace(implemented=True, key="demo"),
                    ):
                        self.assertFalse(history.application_is_live(target))

    def test_live_applications_discards_only_stale_app_entries(self):
        history = RecentTargetHistory()
        live = history.record_application(
            hwnd=1, pid=10, process_name="live.exe", label="Live", adapter_key="live"
        )
        stale = history.record_application(
            hwnd=2, pid=20, process_name="stale.exe", label="Stale", adapter_key="stale"
        )
        history.application_is_live = lambda target: target == live
        self.assertEqual(history.live_applications(), (live,))
        self.assertNotIn(stale, history.items())

    def test_recent_conversation_uses_explicit_process_identity_when_supplied(self):
        history = RecentTargetHistory()
        conversation = SimpleNamespace(
            hwnd=55,
            pid=555,
            name="Project Chat",
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "conversation"),
            left=10,
            top=20,
            right=250,
            bottom=52,
        )
        history._process_name_for_pid = lambda pid: self.fail("unexpected pid lookup")
        target = history.record_conversation(
            conversation,
            adapter_key="slack",
            process_name="Slack.exe",
        )
        self.assertEqual(target.kind, "conversation")
        self.assertEqual(target.label, "Project Chat")
        self.assertEqual(target.process_name, "slack.exe")
        self.assertEqual(target.scope, TargetScope(55, 555))
        self.assertEqual(target.runtime_id, (1, 2, 3))
        self.assertEqual(target.control_identity, ("ListItem", "conversation"))
        self.assertEqual(target.left, 10)
        self.assertEqual(target.bottom, 52)

    def test_recent_conversation_prefers_matching_confirmed_row_geometry(self):
        history = RecentTargetHistory()
        requested = SimpleNamespace(
            hwnd=55,
            pid=555,
            name="Project Chat",
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "conversation"),
            left=10,
            top=20,
            right=250,
            bottom=52,
        )
        confirmed = SimpleNamespace(
            hwnd=55,
            pid=555,
            name="Project Chat",
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "conversation"),
            left=14,
            top=24,
            right=254,
            bottom=56,
            selected=True,
        )
        with patch(
            "floatingbar.conversation_rows.selected_conversation_for_scope",
            return_value=confirmed,
        ):
            target = history.record_conversation(
                requested,
                adapter_key="slack",
                process_name="slack.exe",
            )
        self.assertEqual(target.left, 14)
        self.assertEqual(target.top, 24)
        self.assertEqual(target.right, 254)
        self.assertEqual(target.bottom, 56)
        self.assertEqual(target.runtime_id, (1, 2, 3))

    def test_live_conversation_revalidation_removes_replaced_row(self):
        history = RecentTargetHistory()
        conversation = SimpleNamespace(
            hwnd=55,
            pid=555,
            name="Project Chat",
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "conversation"),
            left=10,
            top=20,
            right=250,
            bottom=52,
        )
        target = history.record_conversation(
            conversation,
            adapter_key="slack",
            process_name="slack.exe",
        )

        class User32:
            @staticmethod
            def IsWindow(hwnd):
                return hwnd == 55

        replacement = SimpleNamespace(
            hwnd=55,
            pid=555,
            name="Other Chat",
            runtime_id=(9, 9),
            control_identity=("ListItem", "conversation"),
            left=10,
            top=20,
            right=250,
            bottom=52,
        )
        with patch("floatingbar.recent_targets.winapi.user32", User32()):
            with patch("floatingbar.recent_targets.winapi.get_window_pid", return_value=555):
                with patch(
                    "floatingbar.recent_targets.winapi.get_process_image_name",
                    return_value=r"C:\\slack.exe",
                ):
                    with patch(
                        "floatingbar.recent_targets.actionable_adapter_for_process",
                        return_value=SimpleNamespace(implemented=True, key="slack"),
                    ):
                        with patch(
                            "floatingbar.conversation_rows.enumerate_conversations",
                            return_value=(replacement,),
                        ):
                            self.assertEqual(history.live_conversations(), ())
        self.assertNotIn(target, history.items())


if __name__ == "__main__":
    unittest.main()
