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

    @mock.patch.object(winapi, "unlock_foreground")
    @mock.patch.object(winapi, "lock_foreground", return_value=True)
    @mock.patch.object(winapi, "post_click")
    @mock.patch.object(winapi, "post_enter")
    @mock.patch.object(winapi, "get_foreground_window", return_value=9999)
    @mock.patch("floatingbar.injector.time.sleep")
    def test_send_uses_protected_background_click_not_uia(
        self, sleep, foreground, post_enter, post_click,
        lock_foreground, unlock_foreground
    ):
        from types import SimpleNamespace

        class Box:
            def __init__(self):
                self.iface_value = SimpleNamespace(CurrentValue="hello")

        class Target(_DummyTarget):
            def __init__(self):
                super().__init__()
                self.box = Box()

            def send_button_control(self, near_box=None):
                return ("Send", "Send", 10, 10)

        target = Target()
        injector = TelegramInjector(target)
        injector.target = target

        def click(_hwnd, _x, _y):
            target.box.iface_value.CurrentValue = ""

        post_click.side_effect = click
        result = injector._submit_invisible(
            target.box, target.hwnd, primary_ctrl=False, landing="compose"
        )

        self.assertEqual(result, "posted-click-protected (VERIFIED)")
        lock_foreground.assert_called_once_with()
        unlock_foreground.assert_called_once_with()
        post_click.assert_called_once_with(1234, 10, 10)


if __name__ == "__main__":
    unittest.main()
