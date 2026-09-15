import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.background_windows import BackgroundWindow, enumerate_background_windows


class BackgroundWindowCatalogTests(unittest.TestCase):
    def test_catalog_excludes_requested_hwnds_and_minimized_windows(self):
        windows = [100, 200, 300]
        def minimized(hwnd):
            return hwnd == 200

        def title_candidate(hwnd):
            return True

        def pid(hwnd):
            return {100: 10, 200: 20, 300: 30}[hwnd]

        def image(process_id):
            return {
                10: r"C:\Apps\Browser.exe",
                20: r"C:\Apps\Terminal.exe",
                30: r"C:\Apps\Editor.exe",
            }[process_id]

        with patch("floatingbar.background_windows.winapi._enum_windows", return_value=windows), \
             patch("floatingbar.background_windows.winapi._is_candidate_window", side_effect=title_candidate), \
             patch("floatingbar.background_windows.winapi.is_minimized", side_effect=minimized), \
             patch("floatingbar.background_windows.winapi.get_foreground_window", return_value=100), \
             patch("floatingbar.background_windows.winapi.get_window_pid", side_effect=pid), \
             patch("floatingbar.background_windows.winapi.get_process_image_name", side_effect=image), \
             patch("floatingbar.background_windows.winapi.get_window_rect_area", side_effect=lambda hwnd: {100: 900, 200: 800, 300: 1000}[hwnd]):
            result = enumerate_background_windows(exclude_hwnds={300})

        self.assertEqual([item.hwnd for item in result], [100])
        self.assertEqual(result[0].process_name, "browser.exe")
        self.assertTrue(result[0].foreground)

    def test_foreground_window_is_sorted_ahead_of_larger_background_window(self):
        windows = [100, 200]
        with patch("floatingbar.background_windows.winapi._enum_windows", return_value=windows), \
             patch("floatingbar.background_windows.winapi._is_candidate_window", return_value=True), \
             patch("floatingbar.background_windows.winapi.is_minimized", return_value=False), \
             patch("floatingbar.background_windows.winapi.get_foreground_window", return_value=100), \
             patch("floatingbar.background_windows.winapi.get_window_pid", side_effect=lambda hwnd: hwnd + 1000), \
             patch("floatingbar.background_windows.winapi.get_process_image_name", side_effect=lambda pid: r"C:\Apps\App.exe"), \
             patch("floatingbar.background_windows.winapi.get_window_rect_area", side_effect=lambda hwnd: {100: 100, 200: 10000}[hwnd]):
            result = enumerate_background_windows()

        self.assertEqual([item.hwnd for item in result], [100, 200])

    def test_catalog_is_content_free(self):
        self.assertEqual(
            BackgroundWindow(100, 200, "telegram.exe", 500, True).label,
            "telegram.exe",
        )
        self.assertNotIn("title", BackgroundWindow.__dataclass_fields__)
        self.assertNotIn("message", BackgroundWindow.__dataclass_fields__)

    def test_broken_window_inspection_is_skipped(self):
        with patch("floatingbar.background_windows.winapi._enum_windows", return_value=[100, 200]), \
             patch("floatingbar.background_windows.winapi._is_candidate_window", side_effect=[True, RuntimeError("gone")]), \
             patch("floatingbar.background_windows.winapi.is_minimized", return_value=False), \
             patch("floatingbar.background_windows.winapi.get_foreground_window", return_value=0), \
             patch("floatingbar.background_windows.winapi.get_window_pid", return_value=10), \
             patch("floatingbar.background_windows.winapi.get_process_image_name", return_value=r"C:\Apps\App.exe"), \
             patch("floatingbar.background_windows.winapi.get_window_rect_area", return_value=100):
            result = enumerate_background_windows()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].hwnd, 100)


if __name__ == "__main__":
    unittest.main()
