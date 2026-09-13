import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_context_overlay import OrbRelayWindow as BoundContextOverlay
from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.transaction import SendAttempt, SendCompletion, TargetScope
from floatingbar.transaction_coordinator import PreparedTransaction, TransactionRejected


class ContextOverlayTests(unittest.TestCase):
    def _window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window.target = Mock()
        window.coordinator = Mock()
        window.injector = Mock()
        window._result_q = queue.Queue()
        window._attempt_context = None
        window._retry_context = None
        window._active_transaction = None
        window._active_attempt_id = 0
        window._work_hwnd = 0
        window._retry_draft = None
        window._retry_target_hwnd = 0
        window._sending = False
        window._state = "orb"
        return window

    def _prepared(self, attempt_id=7, restore_hwnd=111, context=None):
        context = context or Mock()
        context.hwnd = 700
        attempt = SendAttempt(
            attempt_id=attempt_id,
            text="hello",
            target=TargetScope(700, 900),
            restore_hwnd=restore_hwnd,
            context=context,
        )
        return PreparedTransaction(
            attempt=attempt,
            preflight=Mock(),
        )

    def test_bound_context_overlay_is_compatibility_only(self):
        self.assertIs(BoundContextOverlay.__init__, OrbRelayWindow.__init__)
        self.assertIs(BoundContextOverlay._send_finished, OrbRelayWindow._send_finished)

    def test_expand_preserves_failed_draft_target_context(self):
        window = self._window()
        retry_context = Mock()
        retry_context.hwnd = 321
        window._retry_draft = "retry me"
        window._retry_context = retry_context
        window._retry_target_hwnd = 321

        with patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._expand",
            side_effect=lambda: setattr(window, "_state", "bar"),
        ), patch.object(window, "_is_telegram_window") as is_telegram:
            window._expand()

        self.assertEqual(window._work_hwnd, 321)
        self.assertIs(window._attempt_context, retry_context)
        window.injector.set_window_context.assert_called_once_with(retry_context)
        is_telegram.assert_not_called()

    def test_send_worker_uses_coordinator_and_preserves_restore_hwnd(self):
        window = self._window()
        prepared = self._prepared(restore_hwnd=111)
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=False), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker("hello", 111, 7)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=7,
            preferred_hwnd=0,
            restore_hwnd=111,
        )
        self.assertIs(window._active_transaction, prepared.attempt)
        self.assertEqual(window._active_transaction.target, TargetScope(700, 900))
        self.assertEqual(window._active_transaction.restore_hwnd, 111)
        self.assertEqual(window._work_hwnd, 700)
        self.assertIs(window._attempt_context, prepared.attempt.context)
        window.injector.set_window_context.assert_called_once_with(prepared.attempt.context)
        execute_attempt.assert_called_once_with("hello", 111, 7)

    def test_send_worker_passes_telegram_foreground_as_exact_preference(self):
        window = self._window()
        prepared = self._prepared(attempt_id=8, restore_hwnd=700)
        window.coordinator.prepare.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=True), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker("hello", 700, 8)

        window.coordinator.prepare.assert_called_once_with(
            text="hello",
            attempt_id=8,
            preferred_hwnd=700,
            restore_hwnd=700,
        )
        execute_attempt.assert_called_once_with("hello", 700, 8)

    def test_transaction_rejection_is_returned_as_typed_safe_failure(self):
        window = self._window()
        window.coordinator.prepare.side_effect = TransactionRejected("blocked")

        window._send_worker("hello", 111, 9)

        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 9)
        self.assertIsNone(completion.strategy)
        self.assertEqual(completion.error, "blocked")

    def test_unexpected_coordinator_failure_is_returned_as_typed_safe_failure(self):
        window = self._window()
        window.coordinator.prepare.side_effect = RuntimeError("unexpected")

        window._send_worker("hello", 111, 10)

        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 10)
        self.assertIsNone(completion.strategy)
        self.assertIn("unexpected", completion.error)

    def test_queue_completion_maps_evidence_state(self):
        window = self._window()

        window._queue_completion(11, "posted-enter (VERIFIED)", None)

        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.evidence_state.name, "VERIFIED")

    def test_typed_poll_delivers_completion_to_finished_handler(self):
        window = self._window()
        completion = SendCompletion.from_result(
            12,
            strategy="posted-enter (VERIFIED)",
        )
        window._result_q.put(completion)
        window._send_finished = Mock()
        window.after = Mock()

        window._poll_results()

        window._send_finished.assert_called_once_with(completion)
        window.after.assert_called_once_with(80, window._poll_results)

    def test_poll_rejects_untyped_completion(self):
        window = self._window()
        window._result_q.put((13, "posted-enter (VERIFIED)", None))
        window._send_finished = Mock()
        window.after = Mock()

        window._poll_results()

        window._send_finished.assert_not_called()
        window.after.assert_called_once_with(80, window._poll_results)

    def test_active_target_lease_releases_when_completion_raises(self):
        window = self._window()
        window._active_attempt_id = 12
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 12
        window._active_transaction.context = Mock()

        with patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_finished",
            side_effect=RuntimeError("completion bug"),
        ):
            with self.assertRaises(RuntimeError):
                window._send_finished(
                    SendCompletion(
                        attempt_id=12,
                        error="error",
                    )
                )

        window.target.release.assert_called_once_with()

    def test_stale_completion_never_releases_newer_attempt_lease(self):
        window = self._window()
        window._active_attempt_id = 20
        window._active_transaction = Mock()
        window._active_transaction.attempt_id = 20
        window._active_transaction.context = Mock()

        with patch("floatingbar.recovery_overlay.OrbRelayWindow._send_finished") as base_finished:
            completion = SendCompletion(
                attempt_id=19,
                error="old result",
            )
            window._send_finished(completion)

        base_finished.assert_called_once_with(completion)
        window.target.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
