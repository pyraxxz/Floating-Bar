import unittest
from unittest.mock import Mock, patch

from floatingbar.injector import InjectionFailed
from floatingbar.recovery import ScopeGuardedRecoveryInjector


class RecoveryScopeTests(unittest.TestCase):
    def test_focus_steal_stops_before_foreground_when_scope_changes(self):
        target = Mock()
        target.scope_matches.side_effect = [True, False]
        injector = ScopeGuardedRecoveryInjector(target)
        box = Mock()
        set_foreground = Mock(return_value=True)

        with patch(
            "floatingbar.recovery.winapi.get_foreground_window",
            return_value=999,
        ), patch(
            "floatingbar.recovery.winapi.get_window_pid",
            return_value=11,
        ), patch(
            "floatingbar.recovery.winapi.set_foreground_window",
            set_foreground,
        ), patch("floatingbar.recovery.winapi.ensure_restored") as restored, patch(
            "floatingbar.recovery.time.sleep"
        ):
            with self.assertRaises(InjectionFailed):
                injector._submit_focus_steal(box, 123, False, 999)

        restored.assert_called_once_with(123)
        self.assertFalse(any(call.args == (123,) for call in set_foreground.call_args_list))
        box.set_focus.assert_not_called()
        box.type_keys.assert_not_called()

    def test_focus_steal_stable_scope_can_submit(self):
        target = Mock()
        target.scope_matches.return_value = True
        injector = ScopeGuardedRecoveryInjector(target)
        box = Mock()
        injector._value_length = Mock(return_value=0)

        with patch(
            "floatingbar.recovery.winapi.get_foreground_window",
            return_value=999,
        ), patch(
            "floatingbar.recovery.winapi.get_window_pid",
            return_value=11,
        ), patch(
            "floatingbar.recovery.winapi.set_foreground_window",
            return_value=True,
        ), patch("floatingbar.recovery.winapi.ensure_restored"), patch(
            "floatingbar.recovery.time.sleep"
        ):
            self.assertTrue(injector._submit_focus_steal(box, 123, False, 999))

        box.set_focus.assert_called_once_with()
        box.type_keys.assert_called_once_with("{ENTER}", pause=0.02)

    def test_clipboard_recovery_stops_before_focus_when_scope_changes(self):
        target = Mock()
        target.hwnd = 123
        target.scope_matches.side_effect = [True, False]
        injector = ScopeGuardedRecoveryInjector(target)
        box = Mock()
        guard = Mock()
        guard.__enter__ = Mock(return_value=guard)
        guard.__exit__ = Mock(return_value=False)

        with patch(
            "floatingbar.recovery.clipboard_guard.preserved_clipboard",
            return_value=guard,
        ), patch(
            "floatingbar.recovery.winapi.get_foreground_window",
            return_value=999,
        ), patch(
            "floatingbar.recovery.winapi.get_window_pid",
            return_value=11,
        ), patch(
            "floatingbar.recovery.winapi.ensure_restored"
        ) as restored, patch(
            "floatingbar.recovery.winapi.set_foreground_window",
            return_value=True,
        ) as set_foreground, patch("floatingbar.recovery.time.sleep"):
            with self.assertRaises(InjectionFailed):
                injector._strategy_b(box, "hello", False, 999)

        restored.assert_called_once_with(123)
        box.set_focus.assert_not_called()
        box.type_keys.assert_not_called()
        self.assertFalse(any(call.args == (123,) for call in set_foreground.call_args_list))

    def test_clipboard_recovery_uses_original_scope_after_target_replacement(self):
        target = Mock()
        target.hwnd = 999
        target.scope_matches.side_effect = [True, False]
        injector = ScopeGuardedRecoveryInjector(target)
        injector._recovery_scope = (123, 11)
        box = Mock()
        guard = Mock()
        guard.__enter__ = Mock(return_value=guard)
        guard.__exit__ = Mock(return_value=False)

        with patch(
            "floatingbar.recovery.clipboard_guard.preserved_clipboard",
            return_value=guard,
        ), patch(
            "floatingbar.recovery.winapi.get_foreground_window",
            return_value=999,
        ), patch(
            "floatingbar.recovery.winapi.get_window_pid",
            return_value=11,
        ), patch(
            "floatingbar.recovery.winapi.ensure_restored"
        ) as restored, patch(
            "floatingbar.recovery.winapi.set_foreground_window",
            return_value=True,
        ) as set_foreground, patch("floatingbar.recovery.time.sleep"):
            with self.assertRaises(InjectionFailed):
                injector._strategy_b(box, "hello", False, 999)

        restored.assert_called_once_with(123)
        self.assertFalse(any(call.args == (123,) for call in set_foreground.call_args_list))
        box.set_focus.assert_not_called()
        box.type_keys.assert_not_called()


if __name__ == "__main__":
    unittest.main()
