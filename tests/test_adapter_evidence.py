import unittest
from types import SimpleNamespace

from floatingbar.adapter_evidence import evidence_for_adapter
from floatingbar.app_adapters import adapter_for_process
from floatingbar.evidence import EvidenceState, SubmissionEvidence


class AdapterEvidenceTests(unittest.TestCase):
    def test_unverified_adapter_cannot_upgrade_to_verified(self):
        spec = adapter_for_process("my-editor.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)
        self.assertTrue(evidence.uncertain)

    def test_terminal_input_clear_contract_allows_verified_evidence(self):
        spec = adapter_for_process("wt.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.VERIFIED)
        self.assertTrue(evidence.confirmed)
        self.assertEqual(evidence.proof_kind, "input-acceptance")

    def test_each_chat_contract_allows_verified_evidence(self):
        for process_name in (
            "telegram.exe",
            "whatsapp.exe",
            "discord.exe",
            "slack.exe",
            "teams.exe",
        ):
            with self.subTest(process_name=process_name):
                spec = adapter_for_process(process_name)
                evidence = evidence_for_adapter(spec, strategy="posted-enter (VERIFIED)")
                self.assertEqual(evidence.state, EvidenceState.VERIFIED)
                self.assertTrue(evidence.confirmed)

    def test_typed_evidence_wins_over_conflicting_strategy_text(self):
        spec = adapter_for_process("telegram.exe")
        typed = SubmissionEvidence(
            state=EvidenceState.SUBMITTED,
            strategy="posted-click",
            detail="typed producer did not verify the submission",
        )
        evidence = evidence_for_adapter(
            spec,
            strategy="posted-click (VERIFIED)",
            submission_evidence=typed,
        )
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)
        self.assertEqual(evidence.detail, typed.detail)

    def test_typed_verified_proof_scope_must_match_adapter_contract(self):
        spec = adapter_for_process("wt.exe")
        typed = SubmissionEvidence(
            state=EvidenceState.VERIFIED,
            strategy="posted-enter",
            proof_kind="semantic-execution",
        )
        evidence = evidence_for_adapter(spec, submission_evidence=typed)
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)
        self.assertIsNone(evidence.proof_kind)

    def test_typed_terminal_verification_is_preserved(self):
        spec = adapter_for_process("wt.exe")
        typed = SubmissionEvidence(
            state=EvidenceState.VERIFIED,
            strategy="posted-enter",
        )
        evidence = evidence_for_adapter(spec, submission_evidence=typed)
        self.assertEqual(evidence.state, EvidenceState.VERIFIED)
        self.assertTrue(evidence.confirmed)

    def test_failed_send_remains_failed_for_any_adapter(self):
        spec = adapter_for_process("wt.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter", error="target disappeared")
        self.assertEqual(evidence.state, EvidenceState.FAILED)
        self.assertTrue(evidence.retryable)
        self.assertEqual(evidence.detail, "target disappeared")

    def test_blocked_result_stays_blocked_under_adapter_policy(self):
        spec = adapter_for_process("wt.exe")
        evidence = evidence_for_adapter(spec, strategy="preflight (blocked)")
        self.assertEqual(evidence.state, EvidenceState.BLOCKED)
        self.assertTrue(evidence.blocked)
        self.assertFalse(evidence.retryable)

    def test_unknown_adapter_contract_fails_closed(self):
        evidence = evidence_for_adapter(None, strategy="posted-enter (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)

    def test_unknown_verification_mode_cannot_upgrade_to_verified(self):
        spec = SimpleNamespace(key="future-adapter", verification_mode="not-yet-supported")
        evidence = evidence_for_adapter(spec, strategy="posted-click (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)
        self.assertFalse(evidence.retryable)

    def test_unknown_verification_mode_still_preserves_real_failure(self):
        spec = SimpleNamespace(key="future-adapter", verification_mode="not-yet-supported")
        evidence = evidence_for_adapter(spec, strategy="posted-click", error="send failed")
        self.assertEqual(evidence.state, EvidenceState.FAILED)
        self.assertTrue(evidence.retryable)
        self.assertEqual(evidence.detail, "send failed")


if __name__ == "__main__":
    unittest.main()
