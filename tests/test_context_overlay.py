import queue
import unittest
from unittest.mock import Mock, patch

from floatingbar.bound_context_overlay import OrbRelayWindow as BoundContextOverlay
from floatingbar.context_overlay import OrbRelayWindow
from floatingbar.transaction import SendAttempt, SendCompletion, SendRequest, TargetScope
from floatingbar.transaction_coordinator import PreparedTransaction, TransactionRejected
from floatingbar.transaction_state import TransactionLifecycle, TransactionState


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
        window._active_lifecycle = None
        window._active_attempt_id = 0
        window._work_hwnd = 0
        window._retry_draft = None
        window._retry_target_hwnd = 0
        window._sending = False
        window._state = "orb"
        return window

    def _prepared(self, attempt_id=7, restore_hwnd=111, context=None, text="hello"):
        context = context or Mock()
        context.hwnd = 700
        attempt = SendAttempt(
            attempt_id=attempt_id,
            text=text,
            target=TargetScope(700, 900),
            restore_hwnd=restore_hwnd,
            context=context,
        )
        return PreparedTransaction(
            attempt=attempt,
            preflight=Mock(),
        )

    def test_bound_context_overlay_adds_picker_without_replacing_parent_completion(self):
        self.assertIsNot(BoundContextOverlay.__init__, OrbRelayWindow.__init__)
        self.assertIsNot(BoundContextOverlay._send_finished, OrbRelayWindow._send_finished)
        self.assertIn("_background_picker", BoundContextOverlay.__init__.__code__.co_names)
        self.assertIn("_generic_attempt_id", BoundContextOverlay._send_finished.__code__.co_names)

    def test_uncertain_feedback_is_target_neutral_in_base_overlay(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        self.assertEqual(
            window._uncertain_feedback_message(),
            "The send was not confirmed. Verify the target before retrying.",
        )

    def test_uncertain_feedback_names_selected_adapter_without_ui_content(self):
        window = BoundContextOverlay.__new__(BoundContextOverlay)
        window._background_process_name = "wt.exe"
        adapter = Mock(label="Windows Terminal")
        with patch(
            "floatingbar.bound_context_overlay.actionable_adapter_for_process",
            return_value=adapter,
        ):
            self.assertEqual(
                window._uncertain_feedback_message(),
                "Windows Terminal did not confirm the send. Verify the target before retrying.",
            )

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

    def test_send_worker_uses_request_first_coordinator_and_preserves_restore_hwnd(self):
        window = self._window()
        prepared = self._prepared(restore_hwnd=111)
        window.coordinator.prepare_request.return_value = prepared

        request = SendRequest(
            attempt_id=7,
            text="hello",
            restore_hwnd=111,
        )
        with patch.object(window, "_is_telegram_window", return_value=False), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker_request(request)

        window.coordinator.prepare_request.assert_called_once_with(
            request,
            preferred_hwnd=0,
        )
        self.assertIs(window._active_transaction, prepared.attempt)
        self.assertEqual(window._active_transaction.target, TargetScope(700, 900))
        self.assertEqual(window._active_transaction.restore_hwnd, 111)
        self.assertEqual(window._work_hwnd, 700)
        self.assertIs(window._attempt_context, prepared.attempt.context)
        self.assertIsNotNone(window._active_lifecycle)
        self.assertEqual(window._active_lifecycle.state, TransactionState.SENDING)
        window.injector.set_window_context.assert_called_once_with(prepared.attempt.context)
        execute_attempt.assert_called_once_with("hello", 111, 7)

    def test_send_worker_uses_immutable_request_payload(self):
        window = self._window()
        prepared = self._prepared(attempt_id=14, restore_hwnd=333, text="prepared")
        window.coordinator.prepare_request.return_value = prepared

        request = SendRequest(
            attempt_id=14,
            text="payload",
            restore_hwnd=333,
        )
        with patch.object(window, "_is_telegram_window", return_value=False), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker_request(request)

        window.coordinator.prepare_request.assert_called_once_with(
            request,
            preferred_hwnd=0,
        )
        execute_attempt.assert_called_once_with("prepared", 333, 14)

    def test_send_worker_request_rejects_invalid_request(self):
        window = self._window()
        request = SendRequest(
            attempt_id=0,
            text="payload",
            restore_hwnd=333,
        )

        window._send_worker_request(request)

        window.coordinator.prepare_request.assert_not_called()
        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 0)
        self.assertIn("invalid", completion.error.lower())

    def test_send_worker_passes_telegram_foreground_as_exact_preference(self):
        window = self._window()
        prepared = self._prepared(attempt_id=8, restore_hwnd=700)
        window.coordinator.prepare_request.return_value = prepared

        with patch.object(window, "_is_telegram_window", return_value=True), patch.object(
            window, "_execute_prepared_attempt"
        ) as execute_attempt:
            window._send_worker("hello", 700, 8)

        request = SendRequest(8, "hello", 700)
        window.coordinator.prepare_request.assert_called_once_with(
            request,
            preferred_hwnd=700,
        )
        execute_attempt.assert_called_once_with("hello", 700, 8)

    def test_transaction_rejection_is_returned_as_blocked_typed_completion(self):
        window = self._window()
        window.coordinator.prepare_request.side_effect = TransactionRejected("blocked")

        window._send_worker("hello", 111, 9)

        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 9)
        self.assertEqual(completion.strategy, "preflight (blocked)")
        self.assertIsNone(completion.error)
        self.assertEqual(completion.evidence_state.name, "BLOCKED")
        self.assertIsNotNone(window._active_lifecycle)
        self.assertEqual(window._active_lifecycle.state, TransactionState.BLOCKED)

    def test_unexpected_coordinator_failure_is_returned_as_typed_safe_failure(self):
        window = self._window()
        window.coordinator.prepare_request.side_effect = RuntimeError("unexpected")

        window._send_worker("hello", 111, 10)

        completion = window._result_q.get_nowait()
        self.assertIsInstance(completion, SendCompletion)
        self.assertEqual(completion.attempt_id, 10)
        self.assertIsNone(completion.strategy)
        self.assertEqual(
            completion.error,
            "Telegram send preflight failed safely.",
        )
        self.assertIsNotNone(window._active_lifecycle)
        self.assertEqual(window._active_lifecycle.state, TransactionState.REJECTED)

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

    def test_completion_transitions_active_lifecycle_from_evidence(self):
        for strategy, expected_state in (
            ("posted-enter (VERIFIED)", TransactionState.VERIFIED),
            ("posted-enter (unverified)", TransactionState.UNCERTAIN),
            ("posted-enter", TransactionState.UNCERTAIN),
        ):
            with self.subTest(strategy=strategy):
                window = self._window()
                window._active_attempt_id = 12
                window._active_transaction = self._prepared(attempt_id=12).attempt
                lifecycle = TransactionLifecycle(12)
                lifecycle.begin_prepare()
                lifecycle.mark_ready()
                lifecycle.begin_send()
                window._active_lifecycle = lifecycle

                with patch(
                    "floatingbar.recovery_overlay.OrbRelayWindow._send_finished"
                ) as base_finished:
                    completion = SendCompletion.from_result(12, strategy=strategy)
                    window._send_finished(completion)

                base_finished.assert_called_once_with(completion)
                self.assertEqual(lifecycle.state, expected_state)
                window.target.release.assert_called_once_with()

    def test_failed_completion_transitions_active_lifecycle_to_failed(self):
        window = self._window()
        window._active_attempt_id = 13
        window._active_transaction = self._prepared(attempt_id=13).attempt
        lifecycle = TransactionLifecycle(13)
        lifecycle.begin_prepare()
        lifecycle.mark_ready()
        lifecycle.begin_send()
        window._active_lifecycle = lifecycle

        with patch(
            "floatingbar.recovery_overlay.OrbRelayWindow._send_finished"
        ) as base_finished:
            completion = SendCompletion.from_result(13, error="injection failed")
            window._send_finished(completion)

        base_finished.assert_called_once_with(completion)
        self.assertEqual(lifecycle.state, TransactionState.FAILED)
        window.target.release.assert_called_once_with()

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


    def test_pinned_conversation_resolution_uses_complete_catalog(self):
        window = BoundContextOverlay.__new__(BoundContextOverlay)
        window._background_process_name = "slack.exe"
        window._background_adapter_key = "slack"
        window._work_hwnd = 55
        window._pinned_targets = Mock()
        window._pinned_targets.items.return_value = ()

        with patch(
            "floatingbar.bound_context_overlay.enumerate_conversations",
            return_value=(),
        ) as enumerate_rows:
            self.assertEqual(window._pinned_conversation_items(), ())

        enumerate_rows.assert_called_once_with(55, limit=None)


if __name__ == "__main__":
    unittest.main()
