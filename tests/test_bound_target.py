import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_target import BoundTelegramTarget
from floatingbar.target import TelegramNotFound, TelegramTarget
from floatingbar.target_contract import BackgroundTarget
from floatingbar.telegram_chats import TelegramChatItem
from floatingbar.transaction import TargetScope


class BoundTargetTests(unittest.TestCase):
    def _inner(self):
        inner = Mock()
        inner.select_for_send.return_value = 100
        inner.scope.return_value = TargetScope(100, 7)
        inner.is_available.return_value = True
        return inner

    def test_unbound_preferred_selection_creates_exact_binding(self):
        inner = self._inner()
        target = BoundTelegramTarget(inner)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=7
        ):
            selected = target.select_for_send(preferred_hwnd=100)
            self.assertEqual(selected, 100)
            self.assertEqual(target.bound_scope, TargetScope(100, 7))
            self.assertTrue(target.is_available())
            self.assertEqual(target.scope(), TargetScope(100, 7))

    def test_preferred_selection_rejects_silent_retarget(self):
        inner = self._inner()
        inner.select_for_send.return_value = 200
        inner.scope.return_value = TargetScope(200, 8)
        target = BoundTelegramTarget(inner)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=8
        ):
            selected = target.select_for_send(preferred_hwnd=100)

        self.assertEqual(selected, 0)
        self.assertIsNone(target.bound_scope)

    def test_bound_target_returns_unavailable_when_original_window_dies(self):
        inner = self._inner()
        target = BoundTelegramTarget(inner)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=7
        ):
            self.assertEqual(target.select_for_send(preferred_hwnd=100), 100)

        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=False):
            self.assertEqual(target.hwnd, 0)
            self.assertFalse(target.is_available())
            self.assertEqual(target.scope(), TargetScope(0, 0))
            with self.assertRaises(TelegramNotFound):
                target.compose_box()

    def test_bound_target_never_calls_inner_with_a_different_preferred_window(self):
        inner = self._inner()
        target = BoundTelegramTarget(inner)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=7
        ):
            target.select_for_send(preferred_hwnd=100)
            inner.select_for_send.reset_mock()
            selected = target.select_for_send(preferred_hwnd=200)

        self.assertEqual(selected, 0)
        inner.select_for_send.assert_not_called()

    def test_bound_telegram_target_avoids_discovery_when_cached_scope_is_exact(self):
        inner = TelegramTarget()
        inner._hwnd = 100
        inner._pid = 7
        inner.compose_box = Mock(return_value=object())
        target = BoundTelegramTarget(inner)

        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=7
        ), patch.object(inner, "select_for_send", wraps=inner.select_for_send) as select:
            target._bound_scope = TargetScope(100, 7)
            result = target.compose_box()

        self.assertIsNotNone(result)
        select.assert_not_called()

    def test_bound_target_resynchronizes_only_after_cached_scope_drift(self):
        inner = TelegramTarget()
        inner._hwnd = 200
        inner._pid = 8
        inner.compose_box = Mock(return_value=object())
        target = BoundTelegramTarget(inner)
        target._bound_scope = TargetScope(100, 7)

        def resync(preferred_hwnd=0):
            self.assertEqual(preferred_hwnd, 100)
            inner._hwnd = 100
            inner._pid = 7
            return 100

        inner.select_for_send = Mock(side_effect=resync)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", side_effect=[7, 7, 7]
        ):
            result = target.compose_box()

        self.assertIsNotNone(result)
        inner.select_for_send.assert_called_once_with(preferred_hwnd=100)

    def test_bound_target_fails_closed_when_resynchronization_lands_elsewhere(self):
        inner = TelegramTarget()
        inner._hwnd = 200
        inner._pid = 8
        inner.select_for_send = Mock(return_value=200)
        target = BoundTelegramTarget(inner)
        target._bound_scope = TargetScope(100, 7)

        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", return_value=7
        ):
            with self.assertRaises(TelegramNotFound):
                target.compose_box()

        inner.select_for_send.assert_called_once_with(preferred_hwnd=100)

    def test_chat_identity_can_be_bound_and_validated_without_message_content(self):
        target = BoundTelegramTarget(self._inner())
        chat = TelegramChatItem(100, 7, "Alice", 0, 0, 100, 40, True, (1, 2))
        with patch("floatingbar.bound_target.chat_identity_matches", return_value=True) as matches:
            target.bind_chat_identity(chat)
            self.assertTrue(target.chat_identity_matches())
        matches.assert_called_once_with(chat)

    def test_bind_prefers_confirmed_chat_row_for_same_scope(self):
        target = BoundTelegramTarget(self._inner())
        stale = TelegramChatItem(100, 7, "Alice", 0, 0, 100, 40, True, (1, 2))
        confirmed = TelegramChatItem(100, 7, "Alice", 10, 20, 110, 60, True, (1, 2))
        with patch(
            "floatingbar.bound_target.confirmed_telegram_chat_for_scope",
            return_value=confirmed,
        ):
            target.bind_chat_identity(stale)
        self.assertIs(target._chat_identity, confirmed)

    def test_chat_identity_does_not_match_after_manual_switch(self):
        target = BoundTelegramTarget(self._inner())
        chat = TelegramChatItem(100, 7, "Alice", 0, 0, 100, 40, True, (1, 2))
        with patch("floatingbar.bound_target.chat_identity_matches", return_value=False):
            target.bind_chat_identity(chat)
            self.assertFalse(target.chat_identity_matches())

    def test_release_clears_chat_identity_lease(self):
        target = BoundTelegramTarget(self._inner())
        chat = TelegramChatItem(100, 7, "Alice", 0, 0, 100, 40, True, (1, 2))
        target.bind_chat_identity(chat)
        target.release()
        self.assertTrue(target.chat_identity_matches())

    def test_release_clears_confirmed_chat_cache_for_bound_scope(self):
        target = BoundTelegramTarget(self._inner())
        target._bound_scope = TargetScope(100, 7)
        with patch("floatingbar.bound_target.clear_confirmed_telegram_chat_for_scope") as clear:
            target.release()
        clear.assert_called_once_with(100, 7)

    def test_release_allows_a_fresh_target_selection(self):
        inner = self._inner()
        target = BoundTelegramTarget(inner)
        with patch("floatingbar.bound_target.winapi.user32.IsWindow", return_value=True), patch(
            "floatingbar.bound_target.winapi.get_window_pid", side_effect=[7, 8]
        ):
            target.select_for_send(preferred_hwnd=100)
            target.release()
            inner.select_for_send.return_value = 200
            inner.scope.return_value = TargetScope(200, 8)
            selected = target.select_for_send(preferred_hwnd=200)

        self.assertEqual(selected, 200)
        self.assertEqual(target.bound_scope, TargetScope(200, 8))

    def test_wrapper_conforms_to_background_target_protocol(self):
        target = BoundTelegramTarget(self._inner())
        self.assertIsInstance(target, BackgroundTarget)


if __name__ == "__main__":
    unittest.main()
