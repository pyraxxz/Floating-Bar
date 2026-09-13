import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_target import BoundTelegramTarget
from floatingbar.target import TelegramNotFound
from floatingbar.target_contract import BackgroundTarget
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
