import unittest
from unittest.mock import Mock, patch

from floatingbar.hardening import HardenedTelegramInjector
from floatingbar.injector import InjectionFailed


class ScopeGuardTests(unittest.TestCase):
    def test_scope_change_aborts_send(self):
        target = Mock()
        target.scope_matches.return_value = False
        injector = HardenedTelegramInjector(target)

        with patch("floatingbar.hardening.winapi.get_window_pid", return_value=55):
            with self.assertRaises(InjectionFailed):
                injector._assert_target_scope(123, "before Send click")

        target.scope_matches.assert_called_once_with(123, 55)

    def test_stable_scope_allows_send(self):
        target = Mock()
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)

        with patch("floatingbar.hardening.winapi.get_window_pid", return_value=55):
            injector._assert_target_scope(123, "before Send click")

        target.scope_matches.assert_called_once_with(123, 55)

    def test_scope_can_change_between_checks_and_blocks_submission(self):
        target = Mock()
        target.scope_matches.side_effect = [True, False]
        target.send_button_click.return_value = None
        injector = HardenedTelegramInjector(target)
        posted_enter = Mock()

        with patch("floatingbar.hardening.winapi.get_window_pid", return_value=55), \
             patch("floatingbar.hardening.winapi.post_enter", posted_enter), \
             patch("floatingbar.hardening.time.sleep"):
            with self.assertRaises(InjectionFailed):
                injector._submit_invisible(Mock(), 123, False, "unknown")

        posted_enter.assert_not_called()
        self.assertEqual(target.scope_matches.call_count, 2)


if __name__ == "__main__":
    unittest.main()
