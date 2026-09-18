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
        candidate = SimpleNamespace(hwnd=301, pid=200, control_type="Edit", class_name="Edit", is_likely_composer_shape=True)
        target._verification_candidate = candidate
        return target

    def _candidate_patch(self, target):
        return patch.object(target, "input_candidates", return_value=(target._verification_candidate,))

    def _runtime_patches(self):
        return (
            patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True),
            patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True),
            patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200),
        )

    def _live_target_patch(self, target):
        return patch.object(target, "available", return_value=True)

    def test_shared_compose_clear_contract_verifies_discord_slack_teams_and_whatsapp(self):
        for process_name in ("whatsapp.exe", "discord.exe", "slack.exe", "teams.exe"):
            with self.subTest(process_name=process_name):
                target = self._target(process_name)
                target._pin_candidate(target._verification_candidate)
                runtime = self._runtime_patches()
                with runtime[0], runtime[1], runtime[2], self._candidate_patch(target), self._live_target_patch(target), \
                     patch.object(target, "_verification_target", return_value=301), \
                     patch.object(target, "_composer_value_length", return_value=5), \
                     patch.object(target, "_wait_for_length", side_effect=[True, True]):
                    baseline = target.prepare_submission_verification()
                    self.assertEqual(baseline, 5)
                    self.assertEqual(target.begin_submission_verification(301, baseline), 5)
                    result = target.finish_submission_verification(301, 5, "posted-enter (unverified)")
                self.assertEqual(result, "posted-enter (VERIFIED)")


    def test_conversation_change_after_clear_cannot_claim_verified(self):
        target = self._target()
        target._pin_candidate(target._verification_candidate)
        runtime = self._runtime_patches()
        with runtime[0], runtime[1], runtime[2], self._candidate_patch(target), self._live_target_patch(target), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_wait_for_length", return_value=True), \
             patch.object(target, "_conversation_is_still_selected", return_value=False):
            result = target.finish_submission_verification(301, 5, "posted-enter (unverified)")
        self.assertEqual(result, "posted-enter (verification-unavailable)")

    def test_existing_draft_without_growth_never_becomes_verified(self):
        target = self._target()
        target._pin_candidate(target._verification_candidate)
        runtime = self._runtime_patches()
        with runtime[0], runtime[1], runtime[2], self._candidate_patch(target), self._live_target_patch(target), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_composer_value_length", return_value=5), \
             patch.object(target, "_wait_for_length", return_value=False):
            baseline = target.prepare_submission_verification()
            self.assertEqual(baseline, 5)
            self.assertIsNone(target.begin_submission_verification(301, baseline))
        self.assertEqual(target.finish_submission_verification(301, None, "posted-enter (unverified)"), "posted-enter (verification-unavailable)")

    def test_unreadable_baseline_fails_closed(self):
        target = self._target()
        target._pin_candidate(target._verification_candidate)
        runtime = self._runtime_patches()
        with runtime[0], runtime[1], runtime[2], self._candidate_patch(target), self._live_target_patch(target), \
             patch.object(target, "_verification_target", return_value=301), \
             patch.object(target, "_composer_value_length", return_value=-1):
            self.assertIsNone(target.prepare_submission_verification())
            self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(target.finish_submission_verification(301, None, "posted-enter (unverified)"), "posted-enter (verification-unavailable)")

    def test_non_compose_clear_adapter_keeps_unverified_strategy(self):
        target = self._target("terminal.exe")
        self.assertIsNone(target.prepare_submission_verification())
        self.assertIsNone(target.begin_submission_verification(301, None))
        self.assertEqual(target.finish_submission_verification(301, None, "posted-enter (unverified)"), "posted-enter (unverified)")


if __name__ == "__main__":
    unittest.main()
