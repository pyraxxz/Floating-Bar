import unittest
from unittest.mock import patch

from floatingbar.control_candidates import InputCandidate, best_input_candidate, candidate_score
from floatingbar.generic_target import BackgroundTypingTarget, PostSendCheck, TargetProbe
from floatingbar.transaction import TargetScope


class BackgroundTypingTargetTests(unittest.TestCase):
    def setUp(self):
        self.target = BackgroundTypingTarget(100, 200)

    def test_exact_scope_is_immutable_until_rebind(self):
        self.assertEqual(self.target.scope(), TargetScope(100, 200))
        self.target.bind(101, 201)
        self.assertEqual(self.target.scope(), TargetScope(101, 201))

    def test_bind_captures_process_start_identity_when_available(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_process_creation_time", return_value=123), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True):
            self.target.bind(100, 200)

        self.assertEqual(self.target._bound_process_start, 123)
        self.assertTrue(self.target.scope_matches(100, 200))

    def test_available_rejects_reused_pid_when_process_start_changes(self):
        self.target._bound_process_start = 123
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_process_creation_time", return_value=456):
            self.assertFalse(self.target.available())

    def test_scope_matches_rejects_reused_pid_when_process_start_becomes_unreadable(self):
        self.target._bound_process_start = 123
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_process_creation_time", return_value=None):
            self.assertFalse(self.target.scope_matches(100, 200))

    def test_bind_marks_current_window_process_as_verified(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True):
            self.target.bind(100, 200)
            self.assertTrue(self.target.scope_matches(100, 200))

    def test_bind_marks_recycled_or_replaced_scope_unverified(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=999):
            self.target.bind(100, 200)

        self.assertEqual(self.target.scope(), TargetScope(100, 200))
        self.assertFalse(self.target.scope_matches(100, 200))

    def test_bind_liveness_failure_can_recover_after_window_appears(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[999, 200, 200]), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True):
            self.target.bind(100, 200)
            self.assertTrue(self.target.scope_matches(100, 200))

    def test_bind_marks_closed_window_unverified(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=False):
            self.target.bind(100, 200)

        self.assertEqual(self.target.scope(), TargetScope(100, 200))
        self.assertFalse(self.target.scope_matches(100, 200))

    def test_unavailable_when_top_level_window_pid_changes(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=999):
            self.assertFalse(self.target.available())

    def test_unavailable_when_top_level_window_is_hidden(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200):
            self.assertFalse(self.target.available())

    def test_minimized_window_remains_a_valid_background_scope(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200):
            self.assertTrue(self.target.available())

    def test_probe_is_content_free_and_reports_candidates(self):
        candidates = (
            InputCandidate(301, 200, "Edit", "Edit", 0, 0, 400, 30, True, True, True),
            InputCandidate(302, 200, "Edit", "Edit", 0, 40, 400, 80, False, True, True),
        )
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=301), \
             patch("floatingbar.generic_target.enumerate_input_candidates", return_value=candidates):
            probe = self.target.probe()

        self.assertIsInstance(probe, TargetProbe)
        self.assertEqual(probe.scope, TargetScope(100, 200))
        self.assertTrue(probe.available)
        self.assertEqual(probe.focused_hwnd, 301)
        self.assertEqual(probe.candidate_hwnds, (301, 302))
        self.assertEqual(probe.candidate_count, 2)
        self.assertEqual(probe.pinned_hwnd, 0)
        self.assertEqual(probe.reason, "ready")

    def test_probe_reports_unavailable_reason(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=False):
            probe = self.target.probe()
        self.assertEqual(probe.reason, "unavailable")

    def test_probe_reports_missing_input_reason(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=0), \
             patch("floatingbar.generic_target.enumerate_input_candidates", return_value=()):
            probe = self.target.probe()
        self.assertTrue(probe.available)
        self.assertEqual(probe.reason, "no-input")

    def test_probe_reports_inspection_error_reason_without_exposing_exception(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=0), \
             patch("floatingbar.generic_target.enumerate_input_candidates", side_effect=RuntimeError("private UI detail")):
            probe = self.target.probe()
        self.assertTrue(probe.available)
        self.assertEqual(probe.candidate_hwnds, ())
        self.assertEqual(probe.reason, "inspection-error")

    def test_probe_fails_closed_when_target_is_unavailable(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=False):
            probe = self.target.probe()
        self.assertEqual(probe.scope, TargetScope(100, 200))
        self.assertFalse(probe.available)
        self.assertEqual(probe.focused_hwnd, 0)
        self.assertEqual(probe.candidate_hwnds, ())
        self.assertEqual(probe.pinned_hwnd, 0)

    def test_post_send_check_reports_healthy_scope_and_target(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200]):
            check = self.target._post_send_check(301)

        self.assertIsInstance(check, PostSendCheck)
        self.assertTrue(check.healthy)
        self.assertTrue(check.scope_alive)
        self.assertTrue(check.target_alive)
        self.assertEqual(check.target_hwnd, 301)
        self.assertEqual(check.reason, "ok")

    def test_post_send_check_detects_scope_replacement_without_content_read(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=999):
            check = self.target._post_send_check(301)

        self.assertFalse(check.healthy)
        self.assertFalse(check.scope_alive)
        self.assertFalse(check.target_alive)
        self.assertEqual(check.reason, "scope-changed")

    def test_post_send_check_detects_control_replacement(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 999]):
            check = self.target._post_send_check(301)

        self.assertTrue(check.scope_alive)
        self.assertFalse(check.target_alive)
        self.assertFalse(check.healthy)
        self.assertEqual(check.reason, "target-changed")

    def test_send_posts_to_focused_child_inside_bound_process(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = self.target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(300, "hello", expected_pid=200)
        post_enter.assert_called_once_with(300, target=300, expected_pid=200)
        self.assertIsNotNone(self.target.last_post_send_check)
        self.assertTrue(self.target.last_post_send_check.healthy)

    def test_send_surfaces_verification_unavailable_when_target_changes_after_submit(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 999]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            result = self.target.send("hello")

        self.assertEqual(result, "posted-enter (verification-unavailable)")
        post_text.assert_called_once_with(300, "hello", expected_pid=200)
        post_enter.assert_called_once_with(300, target=300, expected_pid=200)
        self.assertIsNotNone(self.target.last_post_send_check)
        self.assertFalse(self.target.last_post_send_check.healthy)
        self.assertEqual(self.target.last_post_send_check.reason, "scope-changed")

    def test_pin_best_input_and_send_uses_pinned_child(self):
        candidate = InputCandidate(301, 200, "Edit", "Edit", 0, 0, 600, 60, False, True, True)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200, 200]), \
             patch.object(self.target, "input_candidates", return_value=(candidate,)), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            pinned = self.target.pin_best_input()
            self.assertEqual(pinned.hwnd, 301)
            self.assertEqual(self.target.pinned_hwnd, 301)
            result = self.target.send("hello")

        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(301, "hello", expected_pid=200)
        post_enter.assert_called_once_with(301, target=301, expected_pid=200)
        self.assertEqual(self.target.pinned_hwnd, 0)
        self.assertIsNotNone(self.target.last_post_send_check)

    def test_pinned_child_runtime_identity_change_is_rejected(self):
        original = InputCandidate(
            301, 200, "RichEdit", "Edit", 0, 0, 400, 30, False, True, True,
            automation_id="composer", framework_id="uia", runtime_id=(1, 2, 3),
        )
        replacement = InputCandidate(
            301, 200, "RichEdit", "Edit", 0, 0, 400, 30, False, True, True,
            automation_id="composer", framework_id="uia", runtime_id=(9, 9, 9),
        )
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch.object(self.target, "input_candidates", side_effect=[(original,), (replacement,)]), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            self.target.pin_best_input()
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.target.send("hello")
        post_text.assert_not_called()

    def test_pinned_child_identity_change_is_rejected_before_posting(self):
        original = InputCandidate(301, 200, "RichEdit", "Edit", 0, 0, 400, 30, False, True, True)
        replacement = InputCandidate(301, 200, "OtherControl", "Edit", 0, 0, 400, 30, False, True, True)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch.object(self.target, "input_candidates", side_effect=[(original,), (replacement,)]), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            self.target.pin_best_input()
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                self.target.send("hello")
        post_text.assert_not_called()

    def test_pinned_child_allows_geometry_change_for_same_control(self):
        original = InputCandidate(301, 200, "RichEdit", "Edit", 0, 0, 400, 30, False, True, True)
        resized = InputCandidate(301, 200, "RichEdit", "Edit", 0, 0, 700, 44, False, True, True)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch.object(self.target, "input_candidates", side_effect=[(original,), (resized,)]), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text, \
             patch("floatingbar.generic_target.winapi.post_enter") as post_enter:
            self.target.pin_best_input()
            result = self.target.send("hello")
        self.assertEqual(result, "posted-enter (unverified)")
        post_text.assert_called_once_with(301, "hello", expected_pid=200)
        post_enter.assert_called_once_with(301, target=301, expected_pid=200)

    def test_pinned_child_must_still_exist_in_structural_inventory(self):
        self.target._pinned_hwnd = 301
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch.object(self.target, "input_candidates", return_value=()), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "no longer editable"):
                self.target.send("hello")
        post_text.assert_not_called()

    def test_send_rejects_focus_from_another_process_before_posting(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 999]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "outside the bound process"):
                self.target.send("hello")
        post_text.assert_not_called()

    def test_send_never_restores_or_foregrounds_target(self):
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.get_window_pid", side_effect=[200, 200, 200, 200]), \
             patch("floatingbar.generic_target.winapi.get_focused_hwnd", return_value=300), \
             patch("floatingbar.generic_target.winapi.post_text"), \
             patch("floatingbar.generic_target.winapi.post_enter"), \
             patch("floatingbar.generic_target.winapi.ensure_restored") as ensure_restored, \
             patch("floatingbar.generic_target.winapi.set_foreground_window") as set_foreground:
            self.target.send("hello")
        ensure_restored.assert_not_called()
        set_foreground.assert_not_called()

    def test_send_rejects_whitespace_only_text(self):
        with self.assertRaises(ValueError):
            self.target.send("   ")


class CandidateScoringTests(unittest.TestCase):
    def test_focused_candidate_beats_unfocused_large_candidate(self):
        focused = InputCandidate(10, 20, "Edit", "Edit", 0, 500, 300, 540, True, True, True)
        large = InputCandidate(11, 20, "Edit", "Edit", 0, 0, 1200, 400, False, True, True)
        self.assertEqual(best_input_candidate((large, focused)), focused)

    def test_composer_shape_and_area_break_ties_deterministically(self):
        wide = InputCandidate(10, 20, "Edit", "Edit", 0, 400, 800, 450, False, True, True)
        small = InputCandidate(11, 20, "Edit", "Edit", 0, 600, 120, 620, False, True, True)
        self.assertGreater(candidate_score(wide), candidate_score(small))
        self.assertEqual(best_input_candidate((small, wide)), wide)


if __name__ == "__main__":
    unittest.main()
