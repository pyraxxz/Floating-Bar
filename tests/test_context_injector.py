import unittest
from unittest.mock import Mock, patch

from floatingbar.context import WindowContext
from floatingbar.context_injector import ContextGuardedRecoveryInjector
from floatingbar.injector import InjectionFailed
from floatingbar.recovery import ScopeGuardedRecoveryInjector


class ContextInjectorTests(unittest.TestCase):
    def test_changed_context_aborts_before_landing(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        context = Mock(spec=WindowContext)
        context.matches.return_value = False
        injector.set_window_context(context)

        with self.assertRaises(InjectionFailed):
            injector._assert_window_context("test landing")

        context.matches.assert_called_once_with()

    def test_matching_context_allows_landing_guard(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        context = Mock(spec=WindowContext)
        context.matches.return_value = True
        injector.set_window_context(context)
        injector._assert_window_context("test landing")
        context.matches.assert_called_once_with()

    def test_send_revalidates_target_before_entering_injector(self):
        target = Mock()
        target.hwnd = 700
        target.scope_matches.return_value = False
        injector = ContextGuardedRecoveryInjector(target)

        with patch.object(ScopeGuardedRecoveryInjector, "send") as parent_send:
            with self.assertRaises(InjectionFailed):
                injector.send("hello")

        parent_send.assert_not_called()
        target.scope_matches.assert_called_once_with(700, 0)

    def test_send_revalidates_context_before_entering_injector(self):
        target = Mock()
        target.hwnd = 700
        target.scope_matches.return_value = True
        injector = ContextGuardedRecoveryInjector(target)
        context = Mock(spec=WindowContext)
        context.matches.return_value = False
        injector.set_window_context(context)

        with patch.object(ScopeGuardedRecoveryInjector, "send") as parent_send:
            with self.assertRaises(InjectionFailed):
                injector.send("hello")

        parent_send.assert_not_called()
        context.matches.assert_called_once_with()

    def test_send_delegates_after_final_transaction_guards(self):
        target = Mock()
        target.hwnd = 700
        target.scope_matches.return_value = True
        injector = ContextGuardedRecoveryInjector(target)
        context = Mock(spec=WindowContext)
        context.matches.return_value = True
        injector.set_window_context(context)

        with patch.object(
            ScopeGuardedRecoveryInjector,
            "send",
            return_value="A2",
        ) as parent_send:
            result = injector.send("hello", restore_hwnd=321)

        self.assertEqual(result, "A2")
        parent_send.assert_called_once_with("hello", restore_hwnd=321)
        target.scope_matches.assert_called_once_with(700, 0)
        context.matches.assert_called_once_with()

    def test_send_rejects_unavailable_target(self):
        target = Mock()
        target.hwnd = 0
        injector = ContextGuardedRecoveryInjector(target)

        with patch.object(ScopeGuardedRecoveryInjector, "send") as parent_send:
            with self.assertRaises(InjectionFailed):
                injector.send("hello")

        parent_send.assert_not_called()

    def test_malformed_context_is_rejected_and_cleared(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        injector.set_window_context(object())
        self.assertIsNone(injector.window_context)

    def test_corrupted_context_fails_closed(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        injector.window_context = object()

        with self.assertRaises(InjectionFailed) as raised:
            injector._assert_window_context("before send click")

        self.assertIn("context", str(raised.exception).lower())

    def test_context_guard_is_included_in_per_action_scope_check(self):
        target = Mock()
        target.scope_matches.return_value = True
        injector = ContextGuardedRecoveryInjector(target)
        context = Mock(spec=WindowContext)
        context.matches.return_value = False
        injector.set_window_context(context)

        with self.assertRaises(InjectionFailed):
            injector._assert_target_scope(100, "before send click")

        target.scope_matches.assert_called_once_with(100, 0)
        context.matches.assert_called_once_with()

    def test_no_context_preserves_existing_behavior(self):
        target = Mock()
        target.hwnd = 700
        target.scope_matches.return_value = True
        injector = ContextGuardedRecoveryInjector(target)

        with patch.object(
            ScopeGuardedRecoveryInjector,
            "send",
            return_value="A2",
        ) as parent_send:
            result = injector.send("hello")

        self.assertEqual(result, "A2")
        parent_send.assert_called_once_with("hello", restore_hwnd=0)


if __name__ == "__main__":
    unittest.main()
