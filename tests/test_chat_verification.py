import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget


class ChatVerificationTests(unittest.TestCase):
    def _target(self, process_name="whatsapp.exe"):
        target = ChatComposerTarget(100, 200)
        spec = adapter_for_process(process_name)
        target.bind(100, 200, spec=spec)
        candidate = SimpleNamespace(
            hwnd=301,
            pid=200,
            control_type="Edit",
            class_name="Edit",
            is_likely_composer_shape=True,
        )
        target._verification_candidate = candidate
        return target

    def _candidate_patch(self, target):
        return patch.object(
            target,
            "input_candidates",
            return_value=(target._verification_candidate,),
        )

    def _live_target_patch(self, target):
        return patch.object(target, "available", return_value=True)

    def test_shared_compose_clear_contract_verifies_discord_slack_teams_and_whatsapp(self):
        for process_name in ("whatsapp.exe", "discord.exe", "slack.exe", "teams.exe"):
            with self.subTest(process_name=process_name):
                target = self._target(process_name)
                with self._candidate_patch(target), self._live_target_patch(target), patch.object(
                    target,
                    "_composer_value_length",
                    side_effect=[5, 8, 0],
                ):
                    target._pin_candidate(target._verification_candidate)
                    baseline = target.prepare_submission_verification()
                    self.assertEqual(baseline, 5)
                    self.assertEqual(target.begin_submission_verification(301, baseline), 5)
                    result = target.finish_submission_verification(301, 5, "posted-enter (unverified)")

                self.assertEqual(result, "posted-enter (VERIFIED)")

    def test_existing_draft_without_growth_never_becomes_verified(self):
        target = self._target()
        with self._candidate_patch(target), self._live_target_patch(target), patch.object(
            target,
            "_composer_value_length",
            side_effect=[5, 5],
        ), patch("floatingbar.chat_composer_target.time.sleep"):
            target._pin_candidate(target._verification_candidate)
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 5)
            self.assertIsNone(target.begin_submission_verification(301, baseline))

        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_unreadable_baseline_fails_closed(self):
        target = self._target()
        with self._candidate_patch(target), self._live_target_patch(target), patch.object(
            target, "_composer_value_length", return_value=-1
        ):
            target._pin_candidate(target._verification_candidate)
            self.assertIsNone(target.prepare_submission_verification())
            self.assertIsNone(target.begin_submission_verification(301, None))

        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (verification-unavailable)",
        )

    def test_non_compose_clear_adapter_keeps_unverified_strategy(self):
        target = self._target("terminal.exe")
        self.assertIsNone(target.prepare_submission_verification())
        self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(
            target.finish_submission_verification(301, None, "posted-enter (unverified)"),
            "posted-enter (unverified)",
        )


if __name__ == "__main__":
    unittest.main()
