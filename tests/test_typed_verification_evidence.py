import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget
from floatingbar.evidence import EvidenceState, EvidenceStrategy
from floatingbar.terminal_target import TerminalTypingTarget


class TypedVerificationEvidenceTests(unittest.TestCase):
    def test_chat_verified_result_carries_typed_contract_evidence(self):
        target = ChatComposerTarget(100, 200)
        target.bind(100, 200, spec=adapter_for_process("whatsapp.exe"))
        candidate = SimpleNamespace(
            hwnd=301,
            pid=200,
            control_type="Edit",
            class_name="Edit",
            is_likely_composer_shape=True,
        )
        target._pin_candidate(candidate)
        with patch.object(target, "input_candidates", return_value=(candidate,)), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_wait_for_length", return_value=True):
            result = target.finish_submission_verification(301, 0, "posted-enter (unverified)")

        self.assertIsInstance(result, EvidenceStrategy)
        self.assertEqual(result, "posted-enter (VERIFIED)")
        self.assertEqual(result.submission_evidence.state, EvidenceState.VERIFIED)
        self.assertIn("contract=whatsapp-compose-clear", result.submission_evidence.detail)

    def test_terminal_unverified_result_carries_submitted_typed_evidence(self):
        target = TerminalTypingTarget(100, 200)
        target.bind(100, 200, spec=adapter_for_process("wt.exe"))
        candidate = SimpleNamespace(
            hwnd=301,
            pid=200,
            control_type="Edit",
            class_name="Edit",
            is_likely_composer_shape=True,
        )
        target._pin_candidate(candidate)
        with patch.object(target, "input_candidates", return_value=(candidate,)), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_wait_for_length", return_value=False):
            result = target.finish_submission_verification(301, 2, "posted-enter (unverified)")

        self.assertIsInstance(result, EvidenceStrategy)
        self.assertEqual(result, "posted-enter (unverified)")
        self.assertEqual(result.submission_evidence.state, EvidenceState.SUBMITTED)
        self.assertIn("contract=terminal-input-clear", result.submission_evidence.detail)

    def test_unverified_or_generic_adapter_still_returns_legacy_strategy(self):
        target = ChatComposerTarget(100, 200)
        target.bind(
            100,
            200,
            spec=SimpleNamespace(
                key="generic:test",
                target_mode="focused-child",
                submit_mode="enter",
                verification_mode="unverified",
            ),
        )
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (unverified)",
        )


if __name__ == "__main__":
    unittest.main()
