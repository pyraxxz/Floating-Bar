import unittest
from unittest.mock import patch

from floatingbar import winapi


class WinApiPostGuardTests(unittest.TestCase):
    def test_get_window_pid_retries_transient_zero_result(self):
        values = iter((0, 0, 200))

        def read_pid(_hwnd, pid_ptr):
            pid_ptr._obj.value = next(values)
            return 1

        with patch.object(winapi.user32, "GetWindowThreadProcessId", side_effect=read_pid), \
             patch.object(winapi.time, "sleep") as sleep:
            self.assertEqual(winapi.get_window_pid(301), 200)

        self.assertEqual(sleep.call_count, 2)

    def test_post_rejects_recycled_hwnd_from_different_process(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=999), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            with self.assertRaisesRegex(RuntimeError, "process changed"):
                winapi._post(301, winapi.WM_CHAR, 65, 0, "test", expected_pid=200)
        post_message.assert_not_called()


    def test_post_rejects_same_pid_when_process_instance_changes(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=200), \
             patch.object(winapi, "get_process_creation_time", return_value=456), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            with self.assertRaisesRegex(RuntimeError, "process instance changed"):
                winapi._post(
                    301,
                    winapi.WM_CHAR,
                    65,
                    0,
                    "test",
                    expected_pid=200,
                    expected_process_start=123,
                )
        post_message.assert_not_called()

    def test_post_rejects_unreadable_process_instance(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=200), \
             patch.object(winapi, "get_process_creation_time", return_value=None), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            with self.assertRaisesRegex(RuntimeError, "identity unavailable"):
                winapi._post(
                    301,
                    winapi.WM_CHAR,
                    65,
                    0,
                    "test",
                    expected_pid=200,
                    expected_process_start=123,
                )
        post_message.assert_not_called()

    def test_post_allows_matching_process_instance(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=200), \
             patch.object(winapi, "get_process_creation_time", return_value=123), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            winapi._post(
                301,
                winapi.WM_CHAR,
                65,
                0,
                "test",
                expected_pid=200,
                expected_process_start=123,
            )
        post_message.assert_called_once_with(301, winapi.WM_CHAR, 65, 0)

    def test_post_allows_expected_process_and_sends(self):
        with patch.object(winapi.user32, "IsWindow", return_value=True), \
             patch.object(winapi, "get_window_pid", return_value=200), \
             patch.object(winapi.user32, "PostMessageW", return_value=True) as post_message:
            winapi._post(301, winapi.WM_CHAR, 65, 0, "test", expected_pid=200)
        post_message.assert_called_once_with(301, winapi.WM_CHAR, 65, 0)


if __name__ == "__main__":
    unittest.main()
