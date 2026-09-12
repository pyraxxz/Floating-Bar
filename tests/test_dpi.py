import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar import dpi


class DpiTests(unittest.TestCase):
    def test_non_windows_is_noop(self):
        with patch.object(dpi.sys, "platform", "linux"):
            self.assertFalse(dpi.enable_per_monitor_awareness())

    def test_modern_api_success(self):
        setter = Mock(return_value=True)
        user32 = SimpleNamespace(SetProcessDpiAwarenessContext=setter)
        with patch.object(dpi.sys, "platform", "win32"), \
             patch("floatingbar.dpi.ctypes.WinDLL", return_value=user32):
            self.assertTrue(dpi.enable_per_monitor_awareness())
        setter.assert_called_once()

    def test_legacy_fallback_success(self):
        modern = SimpleNamespace(SetProcessDpiAwarenessContext=Mock(return_value=False))
        legacy_setter = Mock(return_value=0)
        shcore = SimpleNamespace(SetProcessDpiAwareness=legacy_setter)
        with patch.object(dpi.sys, "platform", "win32"), \
             patch("floatingbar.dpi.ctypes.WinDLL", side_effect=[modern, shcore]):
            self.assertTrue(dpi.enable_per_monitor_awareness())
        legacy_setter.assert_called_once_with(2)

    def test_legacy_access_denied_means_already_aware(self):
        modern = SimpleNamespace(SetProcessDpiAwarenessContext=Mock(return_value=False))
        legacy_setter = Mock(return_value=0x80070005)
        shcore = SimpleNamespace(SetProcessDpiAwareness=legacy_setter)
        with patch.object(dpi.sys, "platform", "win32"), \
             patch("floatingbar.dpi.ctypes.WinDLL", side_effect=[modern, shcore]):
            self.assertTrue(dpi.enable_per_monitor_awareness())


if __name__ == "__main__":
    unittest.main()
