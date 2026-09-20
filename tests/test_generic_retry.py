import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.bound_context_overlay import OrbRelayWindow as BoundContextOverlay
from floatingbar.transaction import SendCompletion, SendRequest, TargetScope


class GenericRetryTests(unittest.TestCase):
    def _window(self):
        window = BoundContextOverlay.__new__(BoundContextOverlay)
        window._background_typer = Mock()
        window._background_typer.scope.return_value = TargetScope(410, 811)
        window._background_typer.bind.return_value = TargetScope(410, 811)
        window._background_typer.scope_matches.return_value = True
        window._background_typer.bound_process_start = 123
        window._background_typer.probe.return_value = SimpleNamespace(
            available=True,
            candidate_count=1,
            reason="ready",
        )
        window._generic_attempt_id = 21
        window._background_process_name = "discord.exe"
        window._background_adapter_key = "discord"
        window._generic_retry_scope = None
        window._generic_retry_process_name = ""
        window._generic_retry_adapter_key = ""
        window._generic_retry_window_class = ""
        window._generic_retry_process_start = None
        window._retry_draft = None
        window._sending = False
        window._work_hwnd = 0
        return window

    def test_generic_send_exception_uses_content_free_user_error(self):
        window = self._window()
        window._result_q = queue.Queue()
        window._generic_attempt_id = 21
        request = SendRequest(
            attempt_id=21,
            text="hello",
            restore_hwnd=410,
        )
        window._background_typer.pin_best_input.side_effect = RuntimeError(
            "UIA control contained secret message content"
        )
        with patch(
            "floatingbar.bound_context_overlay.actionable_adapter_for_process",
            return_value=Mock(key="discord", implemented=True, supports_background_type=True),
        ):
            window._send_worker_request(request)

        completion = window._result_q.get_nowait()
        self.assertEqual(completion.error, "Background send failed safely.")
        self.assertNotIn("secret message content", completion.error)
        window._background_typer.clear_pinned_input.assert_called_once_with()

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
        ), patch(
            "floatingbar.bound_context_overlay.winapi.get_window_class_name",
            return_value="DemoWindow",
        ):
            window._send_finished(completion)

        self.assertEqual(window._generic_retry_scope, TargetScope(410, 811))
        self.assertEqual(window._generic_retry_process_name, "discord.exe")
        self.assertEqual(window._generic_retry_adapter_key, "discord")
        self.assertEqual(window._generic_retry_window_class, "DemoWindow")
        self.assertEqual(window._generic_retry_process_start, 123)
        window._background_typer.release.assert_called_once_with()
        self.assertEqual(window._background_process_name, "")
        self.assertEqual(window._background_adapter_key, "")
        self.assertEqual(window._background_window_class, "")
        self.assertEqual(window._work_hwnd, 0)


    def test_generic_retry_rejects_same_pid_after_process_restart(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_process_start = 123
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer),              patch("floatingbar.bound_context_overlay.winapi.get_process_creation_time", return_value=456):
            window._retry_failed_draft()

        window._show_feedback.assert_called_once()
        window._background_typer.bind.assert_not_called()
        window._show_bar.assert_not_called()

    def test_generic_retry_rejects_unreadable_saved_process_instance(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_process_start = 123
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer),              patch("floatingbar.bound_context_overlay.winapi.get_process_creation_time", return_value=None):
            window._retry_failed_draft()

        window._show_feedback.assert_called_once()
        window._background_typer.bind.assert_not_called()


    def test_generic_retry_uses_saved_process_instance_when_rebinding(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_process_start = 123
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer),              patch("floatingbar.bound_context_overlay.winapi.get_process_creation_time", return_value=123):
            window._retry_failed_draft()

        window._background_typer.bind.assert_called_once_with(
            410,
            811,
            expected_process_start=123,
        )
        self.assertEqual(window._background_process_name, "discord.exe")

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

    def test_generic_retry_is_blocked_when_scope_changed(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        window._background_typer.bind.return_value = TargetScope(999, 811)
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer):
            window._retry_failed_draft()

        window._show_feedback.assert_called_once()
        window._show_bar.assert_not_called()
        window._background_typer.release.assert_called_once_with()

    def test_generic_retry_blocks_window_class_reuse(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_window_class = "DemoWindow"
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="OtherWindow"):
            window._retry_failed_draft()

        window._show_feedback.assert_called_once()
        window._show_bar.assert_not_called()
        window._background_typer.release.assert_called_once_with()

    def test_generic_retry_requires_same_adapter_identity(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "slack"
        window._retry_draft = "hello again"
        window._hide_feedback = Mock()
        window._show_feedback = Mock()
        window._show_bar = Mock()
        window._set_retry_menu_enabled = Mock()

        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer):
            window._retry_failed_draft()

        window._show_feedback.assert_called_once()
        window._show_bar.assert_not_called()
        window._background_typer.bind.assert_not_called()


    def test_generic_retry_process_instance_is_cleared_when_new_background_window_is_selected(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_process_start = 123
        window._telegram_chat_picker = Mock()
        window._conversation_picker = Mock()
        window._state = "orb"
        window._sending = False
        window._update_status = Mock()
        window._show_bar = Mock()
        window._work_hwnd = 0

        item = Mock(
            hwnd=512,
            pid=900,
            process_name="whatsapp.exe",
            actionable=True,
            window_class="WhatsAppMainWindow",
            process_start=None,
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer),              patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True),              patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=900),              patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="WhatsAppMainWindow"):
            window._select_background_window(item)

        self.assertIsNone(window._generic_retry_process_start)

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

        item = Mock(
            hwnd=512,
            pid=900,
            process_name="whatsapp.exe",
            actionable=True,
            window_class="WhatsAppMainWindow",
            process_start=123,
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=900), \
             patch("floatingbar.bound_context_overlay.winapi.get_process_creation_time", return_value=123), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="WhatsAppMainWindow"):
            window._select_background_window(item)

        self.assertIsNone(window._generic_retry_scope)
        self.assertEqual(window._generic_retry_process_name, "")
        self.assertEqual(window._generic_retry_adapter_key, "")
        self.assertEqual(window._background_adapter_key, "whatsapp")
        window._background_typer.release.assert_called_once_with()
        window._conversation_picker.show.assert_called_once_with()
        window._background_typer.bind.assert_not_called()


if __name__ == "__main__":
    unittest.main()
