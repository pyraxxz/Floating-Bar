import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.terminal_target import TerminalTypingTarget


class TerminalVerificationTests(unittest.TestCase):
    def _target(self):
        target = TerminalTypingTarget(100, 200)
        spec = adapter_for_process("wt.exe")
        target.bind(100, 200, spec=spec)
        candidate = SimpleNamespace(
            hwnd=301,
            pid=200,
            control_type="Edit",
            class_name="Edit",
            is_likely_composer_shape=True,
        )
        target._verification_candidate = candidate
        target._pin_candidate(candidate)
        return target

    def _candidate_patch(self, target):
        return patch.object(target, "input_candidates", return_value=(target._verification_candidate,))

    def test_value_growth_then_clear_verifies_exact_terminal_input(self):
        target = self._target()
        with self._candidate_patch(target), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_terminal_value_length", return_value=0), \
             patch.object(target, "_wait_for_length", side_effect=[True, True]):
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 0)
            self.assertEqual(target.begin_submission_verification(301, baseline), 0)
            result = target.finish_submission_verification(301, 0, "posted-enter (unverified)")
        self.assertEqual(result, "posted-enter (VERIFIED)")


    def test_target_change_after_clear_cannot_claim_verified(self):
        target = self._target()
        with self._candidate_patch(target), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", side_effect=RuntimeError("changed")), \
             patch.object(target, "_wait_for_length", return_value=True):
            result = target.finish_submission_verification(301, 0, "posted-enter (unverified)")
        self.assertEqual(result, "posted-enter (verification-unavailable)")

    def test_missing_value_pattern_is_verification_unavailable(self):
        target = self._target()
        with self._candidate_patch(target), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_terminal_value_length", return_value=-1):
            self.assertIsNone(target.prepare_submission_verification())
            self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_input_that_never_grows_does_not_verify(self):
        target = self._target()
        with self._candidate_patch(target), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_terminal_value_length", return_value=0), \
             patch.object(target, "_wait_for_length", return_value=False):
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 0)
            self.assertIsNone(target.begin_submission_verification(301, baseline))
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_clear_timeout_is_submitted_but_unverified(self):
        target = self._target()
        with self._candidate_patch(target), \
             patch.object(target, "available", return_value=True), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_wait_for_length", return_value=False):
            result = target.finish_submission_verification(301, 2, "posted-enter (unverified)")
        self.assertEqual(result, "posted-enter (unverified)")

    def test_non_terminal_verification_mode_is_unchanged(self):
        target = self._target()
        target.bind(100, 200, spec=SimpleNamespace(verification_mode="unverified", key="generic:test"))
        self.assertIsNone(target.prepare_submission_verification())
        self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (unverified)",
        )


if __name__ == "__main__":
    unittest.main()
