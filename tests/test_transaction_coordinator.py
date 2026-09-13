import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.transaction import SendAttempt, TargetScope
from floatingbar.transaction_coordinator import (
    PreparedTransaction,
    SendTransactionCoordinator,
    TransactionRejected,
)


class TransactionCoordinatorTests(unittest.TestCase):
    def _target(self):
        target = Mock()
        target.select_for_send.return_value = 700
        target.scope.return_value = TargetScope(700, 900)
        return target

    def _preflight(self, context=None, ready=True):
        return SimpleNamespace(
            ready=ready,
            status="ready" if ready else "blocked",
            submission_path="send-button",
            context_guard_available=context is not None,
            hwnd=700,
            pid=900,
            context=context,
            reasons=() if ready else ("blocked",),
        )

    def test_prepare_builds_immutable_attempt_from_preflight(self):
        target = self._target()
        context = Mock()
        context.hwnd = 700
        context.matches.return_value = True
        preflight = self._preflight(context=context)
        coordinator = SendTransactionCoordinator(target)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            prepared = coordinator.prepare(
                text="hello",
                attempt_id=12,
                preferred_hwnd=700,
                restore_hwnd=321,
            )

        self.assertIsInstance(prepared, PreparedTransaction)
        self.assertIsInstance(prepared.attempt, SendAttempt)
        self.assertEqual(prepared.attempt.target, TargetScope(700, 900))
        self.assertEqual(prepared.attempt.restore_hwnd, 321)
        self.assertIs(prepared.attempt.context, context)
        target.select_for_send.assert_called_once_with(preferred_hwnd=700)
        context.matches.assert_called_once_with()

    def test_prepare_rejects_blocked_preflight(self):
        target = self._target()
        coordinator = SendTransactionCoordinator(target)
        preflight = self._preflight(ready=False)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            with self.assertRaises(TransactionRejected) as raised:
                coordinator.prepare("hello", 12)

        self.assertIs(raised.exception.preflight, preflight)
        self.assertEqual(str(raised.exception), "blocked")
        target.select_for_send.assert_not_called()

    def test_prepare_rejects_silent_retarget_after_preflight(self):
        target = self._target()
        target.select_for_send.side_effect = [700, 701]
        context = Mock()
        context.hwnd = 700
        context.matches.return_value = True
        preflight = self._preflight(context=context)
        coordinator = SendTransactionCoordinator(target)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            with self.assertRaises(TransactionRejected):
                coordinator.prepare("hello", 12, preferred_hwnd=700)

        self.assertEqual(target.select_for_send.call_count, 2)

    def test_prepare_rejects_context_change_before_worker(self):
        target = self._target()
        context = Mock()
        context.hwnd = 700
        context.matches.return_value = False
        preflight = self._preflight(context=context)
        coordinator = SendTransactionCoordinator(target)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            with self.assertRaises(TransactionRejected) as raised:
                coordinator.prepare("hello", 12, preferred_hwnd=700)

        self.assertIn("context", str(raised.exception).lower())
        target.scope.assert_not_called()

    def test_prepare_rejects_bound_scope_mismatch(self):
        target = self._target()
        target.scope.return_value = TargetScope(700, 901)
        context = Mock()
        context.hwnd = 700
        context.matches.return_value = True
        preflight = self._preflight(context=context)
        coordinator = SendTransactionCoordinator(target)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            with self.assertRaises(TransactionRejected):
                coordinator.prepare("hello", 12, preferred_hwnd=700)

    def test_prepare_accepts_degraded_context_snapshot(self):
        target = self._target()
        context = Mock()
        context.hwnd = 700
        context.matches.return_value = True
        preflight = self._preflight(context=context)
        coordinator = SendTransactionCoordinator(target)

        with patch(
            "floatingbar.transaction_coordinator.run_preflight",
            return_value=preflight,
        ):
            prepared = coordinator.prepare("hello", 12, preferred_hwnd=700)

        self.assertEqual(prepared.attempt.target, TargetScope(700, 900))


if __name__ == "__main__":
    unittest.main()
