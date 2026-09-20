import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_context_overlay import OrbRelayWindow
from floatingbar.transaction import TargetScope


class SelectionRaceTests(unittest.TestCase):
    def _window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._sending = False
        window._pending_conversation = None
        window._pending_chat = None
        window._selection_generation = 0
        window._state = "orb"
        window._work_hwnd = 123
        window._background_process_name = "discord.exe"
        window._background_adapter_key = "discord"
        window._background_window_class = ""
        window._background_typer = Mock()
        window._background_typer.bind.return_value = TargetScope(123, 200)
        window._background_typer.probe.return_value = Mock(available=True, candidate_count=1)
        window._update_status = Mock()
        window._show_bar = Mock()
        window._show_feedback = Mock()
        window.target = Mock()
        return window


    def test_pinned_picker_item_preserves_process_instance_identity(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        from floatingbar.pinned_targets import PinnedTarget
        window._pinned_targets = Mock()
        window._pinned_targets.items.return_value = (
            PinnedTarget(
                kind="application",
                adapter_key="discord",
                process_name="discord.exe",
                label="Discord",
                window_class="DiscordMainWindow",
            ),
        )
        live = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            window_class="DiscordMainWindow",
            process_start=456,
            foreground=False,
        )
        with patch("floatingbar.bound_context_overlay.to_picker_items", return_value=(
            Mock(
                hwnd=123,
                pid=200,
                process_name="discord.exe",
                window_class="DiscordMainWindow",
                process_start=456,
                foreground=False,
            ),
        )),              patch(
                 "floatingbar.bound_context_overlay.actionable_adapter_for_process",
                 return_value=Mock(key="discord", label="Discord", implemented=True, supports_background_type=True),
             ):
            items = window._pinned_picker_items((live,))

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].process_start, 456)

    def test_invalid_new_selection_clears_active_app_identity(self):
        window = self._window()
        window._background_process_name = "discord.exe"
        window._background_adapter_key = "discord"
        window._work_hwnd = 123
        item = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            actionable=True,
            window_class="DifferentWindow",
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DiscordMainWindow"):
            window._select_background_window(item)
        self.assertEqual(window._background_process_name, "")
        self.assertEqual(window._background_adapter_key, "")
        self.assertEqual(window._work_hwnd, 0)

    def test_invalid_new_background_selection_clears_previous_retry_context(self):
        window = self._window()
        window._generic_retry_scope = TargetScope(410, 811)
        window._generic_retry_process_name = "discord.exe"
        window._generic_retry_adapter_key = "discord"
        window._generic_retry_window_class = "DiscordMainWindow"
        item = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            actionable=True,
            window_class="DifferentWindow",
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DiscordMainWindow"):
            window._select_background_window(item)
        self.assertIsNone(window._generic_retry_scope)
        self.assertEqual(window._generic_retry_process_name, "")
        self.assertEqual(window._generic_retry_adapter_key, "")
        self.assertEqual(window._generic_retry_window_class, "")
        window._background_typer.bind.assert_not_called()

    def test_background_selection_rejects_recycled_same_process_window(self):
        window = self._window()
        item = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            actionable=True,
            window_class="DiscordMainWindow",
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DifferentWindow"):
            window._select_background_window(item)
        window._background_typer.bind.assert_not_called()
        window._show_feedback.assert_called_once()


    def test_background_selection_rejects_same_pid_after_process_restart(self):
        window = self._window()
        item = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            actionable=True,
            window_class="DiscordMainWindow",
            process_start=123,
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.bound_context_overlay.winapi.get_process_creation_time", return_value=456):
            window._select_background_window(item)
        window._background_typer.bind.assert_not_called()
        window._show_feedback.assert_called_once_with(
            "That background app restarted before it could be selected."
        )

    def test_background_selection_rejects_replaced_process_before_binding(self):
        window = self._window()
        item = Mock(
            hwnd=123,
            pid=200,
            process_name="discord.exe",
            actionable=True,
            window_class="DiscordMainWindow",
        )
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer), \
             patch("floatingbar.bound_context_overlay.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_pid", return_value=999), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DiscordMainWindow"):
            window._select_background_window(item)
        window._background_typer.bind.assert_not_called()
        window._show_feedback.assert_called_once()

    def test_conversation_finish_rejects_recycled_top_level_class(self):
        window = self._window()
        window._background_process_name = "discord.exe"
        window._background_window_class = "DiscordMainWindow"
        window._pending_conversation = Mock(hwnd=123, pid=200, name="Chat")
        window._background_typer.release = Mock()
        with patch("floatingbar.bound_context_overlay.actionable_adapter_for_process", return_value=Mock(key="discord")), \
             patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DifferentWindow"):
            window._finish_conversation_selection(window._selection_generation_value())
        window._background_typer.bind.assert_not_called()
        window._background_typer.release.assert_called_once()

    def test_telegram_finish_rejects_recycled_top_level_class(self):
        window = self._window()
        window._background_process_name = "telegram.exe"
        window._background_window_class = "TelegramMainWindow"
        window._pending_chat = Mock(hwnd=123, pid=200, name="Chat")
        window.target.release = Mock()
        with patch("floatingbar.bound_context_overlay.winapi.get_window_class_name", return_value="DifferentWindow"):
            window._finish_telegram_chat_selection(window._selection_generation_value())
        window.target.select_for_send.assert_not_called()
        window.target.release.assert_not_called()

    def test_conversation_selection_handoff_uses_confirmed_row(self):
        window = self._window()
        original = Mock(hwnd=123, pid=200, name="Original", process_start=10)
        confirmed = Mock(hwnd=123, pid=200, name="Confirmed", process_start=10)
        window.after = lambda _delay, callback: None

        with patch(
            "floatingbar.bound_context_overlay.select_conversation",
            return_value=confirmed,
        ):
            window._select_conversation(original)

        self.assertIs(window._pending_conversation, confirmed)

    def test_telegram_selection_handoff_uses_confirmed_row(self):
        window = self._window()
        original = Mock(hwnd=123, pid=200, name="Original", process_start=10)
        confirmed = Mock(hwnd=123, pid=200, name="Confirmed", process_start=10)
        window.after = lambda _delay, callback: None

        with patch(
            "floatingbar.bound_context_overlay.select_telegram_chat",
            return_value=confirmed,
        ):
            window._select_telegram_chat(original)

        self.assertIs(window._pending_chat, confirmed)

    def test_failed_conversation_finish_releases_target_lease(self):
        window = self._window()
        window._background_process_name = "discord.exe"
        window._work_hwnd = 123
        window._pending_conversation = Mock(hwnd=123, pid=200, name="Broken")
        window._background_typer.bind.side_effect = RuntimeError("probe failure")
        window._background_typer.release = Mock()
        with patch("floatingbar.bound_context_overlay.actionable_adapter_for_process", return_value=Mock(key="discord")):
            window._finish_conversation_selection(window._selection_generation_value())
        window._background_typer.release.assert_called_once()
        window._show_feedback.assert_called_once_with(
            "The selected conversation could not expose a safe background typing control."
        )

    def test_failed_telegram_finish_releases_target_lease(self):
        window = self._window()
        window._pending_chat = Mock(hwnd=123, pid=200, name="Broken")
        window.target.release = Mock()
        window.target.select_for_send.side_effect = RuntimeError("scope changed")
        window._finish_telegram_chat_selection(window._selection_generation_value())
        window.target.release.assert_called_once()

    def test_stale_generic_selection_callback_cannot_bind_newer_conversation(self):
        window = self._window()
        older = Mock(hwnd=123, pid=200, name="Older", process_start=None)
        newer = Mock(hwnd=123, pid=200, name="Newer", process_start=None)
        callbacks = []
        window.after = lambda _delay, callback: callbacks.append(callback)

        with patch("floatingbar.bound_context_overlay.select_conversation"):
            window._select_conversation(older)
            first = callbacks.pop()
            window._select_conversation(newer)
            second = callbacks.pop()

        first()
        window._background_typer.bind.assert_not_called()
        self.assertIs(window._pending_conversation, newer)

        second()
        window._background_typer.bind.assert_called_once_with(123, 200)

    def test_stale_telegram_selection_callback_cannot_rebind_newer_chat(self):
        window = self._window()
        older = Mock(hwnd=123, pid=200, name="Older", process_start=111)
        newer = Mock(hwnd=123, pid=200, name="Newer", process_start=222)
        callbacks = []
        window.after = lambda _delay, callback: callbacks.append(callback)
        with patch("floatingbar.bound_context_overlay.select_telegram_chat"), \
             patch("floatingbar.bound_context_overlay.capture", return_value=Mock()):
            window._select_telegram_chat(older)
            first = callbacks.pop()
            window._select_telegram_chat(newer)
            second = callbacks.pop()

        first()
        window.target.select_for_send.assert_not_called()
        self.assertIs(window._pending_chat, newer)
        second()
        window.target.select_for_send.assert_called_once_with(
            preferred_hwnd=123,
            expected_process_start=222,
        )

    def test_switching_background_window_invalidates_pending_selection(self):
        window = self._window()
        window._background_process_name = ""
        window._background_adapter_key = ""
        window._generic_attempt_id = 0
        window._background_typer.release = Mock()
        window._telegram_chat_picker = Mock()
        window._conversation_picker = Mock()
        window._generic_retry_scope = None
        window._generic_retry_process_name = ""
        window._generic_retry_adapter_key = ""

        older = Mock(hwnd=123, pid=200, name="Older")
        callbacks = []
        window.after = lambda _delay, callback: callbacks.append(callback)
        with patch("floatingbar.bound_context_overlay.select_conversation"):
            window._select_conversation(older)

        stale = callbacks.pop()
        item = Mock(hwnd=456, pid=300, process_name="discord.exe", actionable=True)
        with patch("floatingbar.bound_context_overlay.target_for_adapter", return_value=window._background_typer):
            window._select_background_window(item)

        stale()
        window._background_typer.bind.assert_not_called()


if __name__ == "__main__":
    unittest.main()
