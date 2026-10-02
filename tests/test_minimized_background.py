import unittest
from unittest import mock

from floatingbar.injector import TelegramInjector
from floatingbar import winapi


class _DummyTarget:
    def __init__(self):
        self.hwnd = 1234
        self.box = object()

    def compose_box(self):
        return self.box


class MinimizedBackgroundTests(unittest.TestCase):
    def _injector(self):
        target = _DummyTarget()
        injector = TelegramInjector(target)
        injector._land_text = mock.Mock(return_value="A-inner")
        injector._audit_and_retarget = mock.Mock(
            return_value=("compose", target.box)
        )
        injector._submit_invisible = mock.Mock(return_value="posted-enter (VERIFIED)")
        return injector

    @mock.patch("floatingbar.injector.time.sleep")
    @mock.patch.object(winapi, "minimize_without_activation", return_value=True)
    @mock.patch.object(winapi, "restore_without_activation", return_value=True)
    @mock.patch.object(winapi, "get_foreground_window", return_value=9999)
    @mock.patch.object(winapi, "is_minimized", side_effect=[True, False])
    def test_minimized_telegram_is_restored_and_reminimized(
        self, is_minimized, foreground, restore, minimize, sleep
    ):
        injector = self._injector()
        result = injector.send("hello", restore_hwnd=9999)

        self.assertEqual(result, "posted-enter (VERIFIED)")
        restore.assert_called_once_with(1234, mock.ANY)
        minimize.assert_called_once_with(1234)
        is_minimized.assert_has_calls([mock.call(1234), mock.call(1234)])

    @mock.patch.object(winapi, "minimize_without_activation")
    @mock.patch.object(winapi, "restore_without_activation")
    @mock.patch.object(winapi, "get_foreground_window", return_value=9999)
    @mock.patch.object(winapi, "is_minimized", return_value=False)
    def test_normal_background_telegram_is_not_reshuffled(
        self, is_minimized, foreground, restore, minimize
    ):
        injector = self._injector()
        result = injector.send("hello", restore_hwnd=9999)

        self.assertEqual(result, "posted-enter (VERIFIED)")
        restore.assert_not_called()
        minimize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
