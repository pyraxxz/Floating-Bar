import unittest
from unittest.mock import patch

from floatingbar.generic_target import BackgroundTypingTarget


class GenericSubmitUncertaintyTests(unittest.TestCase):
    def test_submit_exception_after_text_injection_is_verification_unavailable(self):
        target = BackgroundTypingTarget(100, 200)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.submit_background_target", side_effect=RuntimeError("submit race")) as submit:
            result = target.send("hello")

        self.assertEqual(result, "posted-enter (verification-unavailable)")
        post_text.assert_called_once_with(300, "hello")
        submit.assert_called_once()
        self.assertIsNotNone(target.last_post_send_check)
        self.assertTrue(target.last_post_send_check.healthy)


if __name__ == "__main__":
    unittest.main()
