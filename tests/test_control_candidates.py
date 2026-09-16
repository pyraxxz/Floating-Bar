import unittest
from unittest.mock import Mock, patch

from floatingbar.control_candidates import InputCandidate, best_input_candidate
from floatingbar.generic_target import BackgroundTypingTarget
from floatingbar.transaction import TargetScope


class ControlCandidateTests(unittest.TestCase):
    def test_best_candidate_prefers_focused_control_then_area(self):
        large = InputCandidate(10, 20, "Edit", "Edit", 0, 0, 1000, 1000, False, True, True)
        focused = InputCandidate(11, 20, "Edit", "Edit", 0, 0, 100, 40, True, True, True)
        self.assertEqual(best_input_candidate((large, focused)).hwnd, 11)

    def test_candidate_model_contains_no_text_value(self):
        candidate = InputCandidate(10, 20, "Edit", "Edit", 1, 2, 101, 42, True, True, True)
        self.assertFalse(hasattr(candidate, "text"))
        self.assertEqual(candidate.area, 4000)

    def test_generic_target_exposes_structural_candidates_without_sending(self):
        target = BackgroundTypingTarget(100, 200)
        candidate = InputCandidate(300, 200, "Edit", "Edit", 0, 0, 100, 40, True, True, True)
        with patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True), \
             patch("floatingbar.generic_target.winapi.is_minimized", return_value=False), \
             patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.generic_target.enumerate_input_candidates", return_value=(candidate,)):
            self.assertEqual(target.scope(), TargetScope(100, 200))
            self.assertEqual(target.input_candidates(), (candidate,))


if __name__ == "__main__":
    unittest.main()
