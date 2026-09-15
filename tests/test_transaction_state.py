import unittest

from floatingbar.evidence import EvidenceState
from floatingbar.transaction_state import (
    InvalidTransactionTransition,
    TransactionLifecycle,
    TransactionState,
    allowed_transitions,
)


class TransactionStateTests(unittest.TestCase):
    def test_new_lifecycle_is_idle(self):
        lifecycle = TransactionLifecycle(7)
        self.assertEqual(lifecycle.attempt_id, 7)
        self.assertEqual(lifecycle.state, TransactionState.IDLE)
        self.assertFalse(lifecycle.terminal)

    def test_happy_path_is_linear(self):
        lifecycle = TransactionLifecycle(7)
        self.assertEqual(lifecycle.begin_prepare(), TransactionState.PREPARING)
        self.assertEqual(lifecycle.mark_ready(), TransactionState.READY)
        self.assertEqual(lifecycle.begin_send(), TransactionState.SENDING)
        self.assertEqual(lifecycle.complete_verified(), TransactionState.VERIFIED)
        self.assertTrue(lifecycle.terminal)

    def test_failed_path_is_terminal(self):
        lifecycle = TransactionLifecycle(8)
        lifecycle.begin_prepare()
        lifecycle.mark_ready()
        lifecycle.begin_send()
        self.assertEqual(lifecycle.complete_failed(), TransactionState.FAILED)
        self.assertTrue(lifecycle.terminal)

    def test_uncertain_path_is_terminal(self):
        lifecycle = TransactionLifecycle(9)
        lifecycle.begin_prepare()
        lifecycle.mark_ready()
        lifecycle.begin_send()
        self.assertEqual(lifecycle.complete_uncertain(), TransactionState.UNCERTAIN)
        self.assertTrue(lifecycle.terminal)

    def test_rejected_preflight_is_terminal(self):
        lifecycle = TransactionLifecycle(10)
        lifecycle.begin_prepare()
        self.assertEqual(lifecycle.reject(), TransactionState.REJECTED)
        self.assertTrue(lifecycle.terminal)

    def test_invalid_transition_cannot_skip_safety_phases(self):
        lifecycle = TransactionLifecycle(11)
        with self.assertRaises(InvalidTransactionTransition):
            lifecycle.begin_send()
        lifecycle.begin_prepare()
        with self.assertRaises(InvalidTransactionTransition):
            lifecycle.complete_verified()

    def test_terminal_state_cannot_be_reused(self):
        lifecycle = TransactionLifecycle(12)
        lifecycle.begin_prepare()
        lifecycle.mark_ready()
        lifecycle.begin_send()
        lifecycle.complete_verified()
        with self.assertRaises(InvalidTransactionTransition):
            lifecycle.begin_prepare()

    def test_allowed_transitions_are_immutable(self):
        self.assertEqual(
            allowed_transitions(TransactionState.PREPARING),
            frozenset({TransactionState.READY, TransactionState.REJECTED}),
        )
        with self.assertRaises(AttributeError):
            allowed_transitions(TransactionState.PREPARING).add(TransactionState.SENDING)

    def test_attempt_id_must_be_positive_integer(self):
        for value in (0, -1, True, False, "7"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    TransactionLifecycle(value)

    def test_evidence_mapping_covers_verified_uncertain_and_failed(self):
        cases = (
            (EvidenceState.VERIFIED, TransactionState.VERIFIED),
            (EvidenceState.SUBMITTED, TransactionState.UNCERTAIN),
            (EvidenceState.UNAVAILABLE, TransactionState.UNCERTAIN),
            (EvidenceState.UNKNOWN, TransactionState.UNCERTAIN),
            (EvidenceState.FAILED, TransactionState.FAILED),
        )
        for evidence_state, expected_state in cases:
            with self.subTest(evidence_state=evidence_state):
                lifecycle = TransactionLifecycle(100 + len(evidence_state.value))
                lifecycle.begin_prepare()
                lifecycle.mark_ready()
                lifecycle.begin_send()
                self.assertEqual(
                    lifecycle.complete_from_evidence(evidence_state),
                    expected_state,
                )
                self.assertTrue(lifecycle.terminal)

    def test_evidence_mapping_rejects_wrong_type(self):
        lifecycle = TransactionLifecycle(20)
        lifecycle.begin_prepare()
        lifecycle.mark_ready()
        lifecycle.begin_send()
        with self.assertRaises(TypeError):
            lifecycle.complete_from_evidence("verified")


if __name__ == "__main__":
    unittest.main()
