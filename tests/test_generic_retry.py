import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_context_overlay import OrbRelayWindow as BoundContextOverlay
from floatingbar.transaction import SendCompletion, TargetScope


class GenericRetryTests(unittest.TestCase):
    def _window(self):
        window = BoundContextOverlay.__new__(BoundContextOverlay)
        window._background_typer = Mock()
        window._background_typer.scope.return_value = TargetScope(410, 811)
        window._generic_attempt_id = 21
        window._background_process_name = "discord.exe"
        window._background_adapter_key = "discord"
        window._generic_retry_scope = None
        window._generic_retry_process_name = ""
        window._generic_retry_adapter_key = ""
        window._retry_draft = None
        window._sending = False
        window._work_hwnd = 0
        return window

    def test_failed_generic_send_keeps_exact_scope_and_adapter_for_retry(self):
        window = self._window()
        completion = SendCompletion.from_result(21, error="background typing target is unavailable")

        def fail_and_offer_retry(_instance, _completion):
            window._retry_draft = "hello again"
            window._retry_target_hwnd = 410

        with patch.object(
            BoundContextOverlay._send_finished.__globals__["_BaseOverlay"],
            "_send_finished",
            side_effect=fail_and_offer_retry,
        ):
            window._send_finished(completion)

        self.assertEqual(window._generic_retry_scope, TargetScope(410, 811))
        self.assertEqual(window._generic_retry_process_name, "discord.exe")
        self.assertEqual(window._generic_retry_adapter_key, "discord")
        window._background_typer.release.assert_called_once_with()
        self.assertEqual(window._background_process_name, "")
        self.assertEqual(window._background_adapter_key, "")

    def test_generic_retry_rebinds_original_scope_instead_of_foreground_path(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch.object(
                 BoundContextOverlay._send_finished.__globals__["_BaseOverlay"],
                 "_retry_failed_draft",
                 side_effect=AssertionError("generic retry must not fall back to Telegram/base path"),
             ):
            window._retry_failed_draft()

        window._background_typer.bind.assert_called_once_with(410, 811)
        self.assertEqual(window._background_process_name, "discord.exe")
        self.assertEqual(window._background_adapter_key, "discord")
        self.assertEqual(window._work_hwnd, 410)
        window._show_bar.assert_called_once_with()
        window._set_retry_menu_enabled.assert_called_once_with(True)

    def test_generic_retry_is_cleared_when_new_background_window_is_selected(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._telegram_chat_picker = Mock()
        window._conversation_picker = Mock()
        window._state = "orb"
        window._sending = False
        window._update_status = Mock()
        window._show_bar = Mock()
        window._work_hwnd = 0

        item = Mock(hwnd=512, pid=900, process_name="whatsapp.exe", actionable=True)
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer):
            window._select_background_window(item)

        self.assertIsNone(window._generic_retry_scope)
        self.assertEqual(window._generic_retry_process_name, "")
        self.assertEqual(window._generic_retry_adapter_key, "")
        self.assertEqual(window._background_adapter_key, "whatsapp")
        window._background_typer.release.assert_called_once_with()
        window._background_typer.bind.assert_called_once_with(512, 900)


if __name__ == "__main__":
    unittest.main()
