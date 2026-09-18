import unittest
from unittest.mock import patch

from floatingbar import winapi


class WinApiPostGuardTests(unittest.TestCase):
    def test_post_rejects_recycled_hwnd_from_different_process(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=999), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                winapi._post(301, winapi.WM_CHAR, 65, 0, "test", expected_pid=200)
        post_message.assert_not_called()

    def test_post_allows_expected_process_and_sends(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=200), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            winapi._post(301, winapi.WM_CHAR, 65, 0, "test", expected_pid=200)
        post_message.assert_called_once_with(301, winapi.WM_CHAR, 65, 0)


if __name__ == "__main__":
    unittest.main()
