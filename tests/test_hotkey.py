import sys
import unittest
from unittest.mock import Mock, patch


if sys.platform == "win32":
    from floatingbar.hotkey import (
        GlobalHotkey,
        HotkeySpec,
        MOD_ALT,
        MOD_CONTROL,
        WM_HOTKEY,
        _HOTKEY_ID,
    )
else:
    GlobalHotkey = None
    HotkeySpec = None
    MOD_ALT = MOD_CONTROL = 0
    WM_HOTKEY = _HOTKEY_ID = 0


@unittest.skipUnless(sys.platform == "win32", "global hotkey requires Windows")
class GlobalHotkeyTests(unittest.TestCase):
    def test_invalid_virtual_key_is_rejected(self):
        with self.assertRaises(ValueError):
            GlobalHotkey(HotkeySpec(MOD_CONTROL | MOD_ALT, 0x100), Mock(), Mock())

    def test_non_callable_trigger_is_rejected(self):
        with self.assertRaises(TypeError):
            GlobalHotkey(HotkeySpec(MOD_CONTROL | MOD_ALT, 0x20), None, Mock())

    def test_successful_registration_marshals_hotkey_to_tk_thread(self):
        callback = Mock()
        root = Mock()
        hotkey = GlobalHotkey(
            HotkeySpec(MOD_CONTROL | MOD_ALT, 0x20),
            callback,
            root,
        )
        calls = []

        def register(*args):
            calls.append("register")
            self.assertEqual(args[0], None)
            self.assertEqual(args[1], _HOTKEY_ID)
            self.assertEqual(args[2], MOD_CONTROL | MOD_ALT | 0x4000)
            self.assertEqual(args[3], 0x20)
            return True

        def get_message(msg_ptr, *_args):
            calls.append("message")
            if calls.count("message") == 1:
                msg = msg_ptr._obj
                msg.message = WM_HOTKEY
                msg.wParam = _HOTKEY_ID
                return 1
            return 0

        with patch.object(hotkey, "_ensure_message_queue", side_effect=lambda: calls.append("queue")), \
             patch.object(hotkey, "_thread_id", 42), \
             patch("floatingbar.hotkey.kernel32.GetCurrentThreadId", return_value=42), \
             patch("floatingbar.hotkey.user32.RegisterHotKey", side_effect=register), \
             patch("floatingbar.hotkey.user32.GetMessageW", side_effect=get_message), \
             patch("floatingbar.hotkey.user32.UnregisterHotKey", side_effect=lambda *args: calls.append("unregister")):
            hotkey._run()

        self.assertEqual(calls[0:3], ["queue", "register", "message"])
        root.after.assert_called_once_with(0, callback)
        self.assertIn("unregister", calls)

    def test_registration_failure_does_not_enter_message_loop(self):
        hotkey = GlobalHotkey(
            HotkeySpec(MOD_CONTROL | MOD_ALT, 0x20),
            Mock(),
            Mock(),
        )
        with patch("floatingbar.hotkey.user32.RegisterHotKey", return_value=False) as register, \
             patch("floatingbar.hotkey.user32.GetMessageW") as get_message, \
             patch.object(hotkey, "_ensure_message_queue"), \
             patch("floatingbar.hotkey.kernel32.GetCurrentThreadId", return_value=42):
            hotkey._run()

        self.assertFalse(hotkey.is_registered)
        register.assert_called_once()
        get_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
