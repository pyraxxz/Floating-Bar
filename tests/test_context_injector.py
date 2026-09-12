import unittest
from unittest.mock import Mock

from floatingbar.context_injector import ContextGuardedRecoveryInjector
from floatingbar.injector import InjectionFailed


class ContextInjectorTests(unittest.TestCase):
    def test_changed_context_aborts_before_landing(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        context = Mock()
        context.matches.return_value = False
        injector.set_window_context(context)

        with self.assertRaises(InjectionFailed):
            injector._assert_window_context("test landing")

    def test_matching_context_allows_landing_guard(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        context = Mock()
        context.matches.return_value = True
        injector.set_window_context(context)

        injector._assert_window_context("test landing")
        context.matches.assert_called_once_with()

    def test_no_context_preserves_existing_behavior(self):
        injector = ContextGuardedRecoveryInjector(Mock())
        injector._assert_window_context("test")


if __name__ == "__main__":
    unittest.main()
