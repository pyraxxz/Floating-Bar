import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget


class ChatVerificationTests(unittest.TestCase):
    def _target(self):
        target = ChatComposerTarget(100, 200)
        spec = adapter_for_process("whatsapp.exe")
        target.bind(100, 200, spec=spec)
        candidate = SimpleNamespace(
            hwnd=301,
            pid=200,
            control_type="Edit",
            is_likely_composer_shape=True,
        )
        with patch.object(target, "input_candidates", return_value=(candidate,)):
            target._pin_candidate(candidate)
        return target

    def test_whatsapp_contract_verifies_after_baseline_growth_and_clear(self):
        target = self._target()
        with patch.object(
            target,
            "_composer_value_length",
            side_effect=[5, 8, 0],
        ):
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 5)
            self.assertEqual(target.begin_submission_verification(301, baseline), 5)
            result = target.finish_submission_verification(301, 5, "posted-enter (unverified)")

        self.assertEqual(result, "posted-enter (VERIFIED)")

    def test_existing_draft_without_growth_never_becomes_verified(self):
        target = self._target()
        with patch.object(
            target,
            "_composer_value_length",
            side_effect=[5, 5],
        ), patch("floatingbar.chat_composer_target.time.sleep"):
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 5)
            self.assertIsNone(target.begin_submission_verification(301, baseline))

        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_unreadable_baseline_fails_closed(self):
        target = self._target()
        with patch.object(target, "_composer_value_length", return_value=-1):
            self.assertIsNone(target.prepare_submission_verification())
            self.assertIsNone(target.begin_submission_verification(301, None))

        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_non_compose_clear_adapter_keeps_unverified_strategy(self):
        target = ChatComposerTarget(100, 200)
        spec = adapter_for_process("discord.exe")
        target.bind(100, 200, spec=spec)
        self.assertIsNone(target.prepare_submission_verification())
        self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (unverified)",
        )


if __name__ == "__main__":
    unittest.main()
