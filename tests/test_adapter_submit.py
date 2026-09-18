import unittest
from unittest.mock import patch

from floatingbar.adapter_submit import submit_background_target
from floatingbar.app_adapters import adapter_for_process


class AdapterSubmitTests(unittest.TestCase):
    def test_enter_adapter_posts_enter_to_exact_target(self):
        spec = adapter_for_process("discord.exe")
        with patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            strategy = submit_background_target(spec, 401)

        self.assertEqual(strategy, "posted-enter (unverified)")
        post_enter.assert_called_once_with(401, target=401)


    def test_enter_adapter_forwards_process_instance_identity(self):
        spec = adapter_for_process("discord.exe")
        with patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            strategy = submit_background_target(
                spec,
                401,
                expected_pid=200,
                expected_process_start=123,
            )

        self.assertEqual(strategy, "posted-enter (unverified)")
        post_enter.assert_called_once_with(
            401,
            target=401,
            expected_pid=200,
            expected_process_start=123,
        )

    def test_unknown_submit_mode_fails_closed_without_injection(self):
        class Spec:
            submit_mode = "click"

        with patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            with self.assertRaisesRegex(RuntimeError, "unsupported"):
                submit_background_target(Spec(), 401)

        post_enter.assert_not_called()

    def test_legacy_none_policy_preserves_direct_target_compatibility(self):
        with patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            strategy = submit_background_target(None, 401)

        self.assertEqual(strategy, "posted-enter (unverified)")
        post_enter.assert_called_once_with(401, target=401)

    def test_zero_target_is_rejected_before_injection(self):
        spec = adapter_for_process("slack.exe")
        with patch("floatingbar.adapter_submit.winapi.post_enter") as post_enter:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                submit_background_target(spec, 0)
        post_enter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
