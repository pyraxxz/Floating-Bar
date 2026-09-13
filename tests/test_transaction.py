import unittest

from floatingbar.evidence import EvidenceState
from floatingbar.transaction import SendAttempt, SendCandidate, SendCompletion, TargetScope


class TransactionTests(unittest.TestCase):
    def test_target_scope_requires_hwnd_and_pid(self):
        self.assertTrue(TargetScope(10, 20).valid)
        self.assertFalse(TargetScope(0, 20).valid)
        self.assertFalse(TargetScope(10, 0).valid)

    def test_send_candidate_preserves_legacy_three_value_tuple_shape(self):
        candidate = SendCandidate("Send", 40, 50, 137.5)
        self.assertEqual(candidate, ("Send", 40, 50))
        self.assertEqual(candidate[1:], (40, 50))
        name, x, y = candidate
        self.assertEqual((name, x, y), ("Send", 40, 50))

    def test_send_candidate_carries_immutable_evidence_metadata(self):
        candidate = SendCandidate("Send", 40, 50, 137.5)
        self.assertEqual(candidate.name, "Send")
        self.assertEqual(candidate.client_x, 40)
        self.assertEqual(candidate.client_y, 50)
        self.assertEqual(candidate.evidence_score, 137.5)
        with self.assertRaises(AttributeError):
            candidate.evidence_score = 20.0
        with self.assertRaises(AttributeError):
            candidate.extra = True
        with self.assertRaises(AttributeError):
            del candidate.evidence_score

    def test_send_attempt_is_immutable_and_valid(self):
        attempt = SendAttempt(
            attempt_id=7,
            text="hello",
            target=TargetScope(10, 20),
            restore_hwnd=99,
        )
        self.assertTrue(attempt.valid)
        with self.assertRaises(Exception):
            attempt.attempt_id = 8

    def test_whitespace_only_send_attempt_is_invalid(self):
        self.assertFalse(
            SendAttempt(7, " \t ", TargetScope(10, 20)).valid
        )

    def test_send_attempt_invalid_when_identity_or_target_is_missing(self):
        self.assertFalse(
            SendAttempt(0, "hello", TargetScope(10, 20)).valid
        )
        self.assertFalse(
            SendAttempt(7, "hello", TargetScope(0, 20)).valid
        )
        self.assertFalse(
            SendAttempt(7, "", TargetScope(10, 20)).valid
        )

    def test_completion_can_carry_typed_evidence(self):
        completion = SendCompletion(
            attempt_id=7,
            strategy="posted-enter (VERIFIED)",
            evidence_state=EvidenceState.VERIFIED,
        )
        self.assertFalse(completion.failed)
        self.assertEqual(completion.evidence_state, EvidenceState.VERIFIED)

    def test_completion_failure_state_is_explicit_failure(self):
        completion = SendCompletion(
            attempt_id=7,
            evidence_state=EvidenceState.FAILED,
        )
        self.assertTrue(completion.failed)

    def test_completion_error_is_explicit_failure(self):
        completion = SendCompletion(
            attempt_id=7,
            error="target changed",
        )
        self.assertTrue(completion.failed)


if __name__ == "__main__":
    unittest.main()
