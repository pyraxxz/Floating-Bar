import unittest

from floatingbar.evidence import EvidenceState
from floatingbar.transaction import SendAttempt, SendCompletion, TargetScope


class TransactionTests(unittest.TestCase):
    def test_target_scope_requires_hwnd_and_pid(self):
        self.assertTrue(TargetScope(10, 20).valid)
        self.assertFalse(TargetScope(0, 20).valid)
        self.assertFalse(TargetScope(10, 0).valid)

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
            strategy="posted-enter",
            evidence_state=EvidenceState.CONFIRMED,
        )
        self.assertFalse(completion.failed)
        self.assertEqual(completion.evidence_state, EvidenceState.CONFIRMED)

    def test_completion_error_is_explicit_failure(self):
        completion = SendCompletion(
            attempt_id=7,
            error="target changed",
        )
        self.assertTrue(completion.failed)


if __name__ == "__main__":
    unittest.main()
