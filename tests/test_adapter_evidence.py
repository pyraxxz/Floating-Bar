import unittest
from types import SimpleNamespace

from floatingbar.adapter_evidence import evidence_for_adapter
from floatingbar.app_adapters import adapter_for_process
from floatingbar.evidence import EvidenceState


class AdapterEvidenceTests(unittest.TestCase):
    def test_unverified_adapter_cannot_upgrade_to_verified(self):
        spec = adapter_for_process("my-editor.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.SUBMITTED)
        self.assertFalse(evidence.confirmed)
        self.assertTrue(evidence.uncertain)

    def test_terminal_input_clear_contract_allows_verified_evidence(self):
        spec = adapter_for_process("terminal.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.VERIFIED)
        self.assertTrue(evidence.confirmed)

    def test_telegram_compose_clear_allows_verified_evidence(self):
        spec = adapter_for_process("telegram.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-click (VERIFIED)")
        self.assertEqual(evidence.state, EvidenceState.VERIFIED)
        self.assertTrue(evidence.confirmed)

    def test_failed_send_remains_failed_for_any_adapter(self):
        spec = adapter_for_process("terminal.exe")
        evidence = evidence_for_adapter(spec, strategy="posted-enter", error="target disappeared")
        self.assertEqual(evidence.state, EvidenceState.FAILED)
        self.assertTrue(evidence.retryable)
        self.assertEqual(evidence.detail, "target disappeared")

    def test_blocked_result_stays_blocked_under_adapter_policy(self):
        spec = adapter_for_process("terminal.exe")
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
