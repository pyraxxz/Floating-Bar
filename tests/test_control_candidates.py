import unittest
from unittest.mock import patch

from floatingbar.control_candidates import (
    InputCandidate,
    best_input_candidate,
    candidate_score,
    _candidate_from_element,
)
from floatingbar.generic_target import BackgroundTypingTarget
from floatingbar.transaction import TargetScope


class ControlCandidateTests(unittest.TestCase):
    def test_best_candidate_prefers_focused_control(self):
        large = InputCandidate(10, 20, "Edit", "Edit", 0, 0, 1000, 1000, False, True, True)
        focused = InputCandidate(11, 20, "Edit", "Edit", 0, 0, 100, 40, True, True, True)
        self.assertEqual(best_input_candidate((large, focused)).hwnd, 11)

    def test_composer_geometry_is_a_structural_signal(self):
        wide = InputCandidate(10, 20, "Edit", "Edit", 0, 400, 800, 450, False, True, True)
        tiny = InputCandidate(11, 20, "Edit", "Edit", 0, 500, 100, 520, False, True, True)
        self.assertGreater(candidate_score(wide), candidate_score(tiny))
        self.assertEqual(best_input_candidate((tiny, wide)), wide)

    def test_candidate_model_contains_no_text_value(self):
        candidate = InputCandidate(10, 20, "Edit", "Edit", 1, 2, 101, 42, True, True, True)
        self.assertFalse(hasattr(candidate, "text"))
        self.assertEqual(candidate.area, 4000)

    def test_candidate_extraction_captures_content_free_uia_identity(self):
        from types import SimpleNamespace

        class Element:
            handle = 301
            element_info = SimpleNamespace(
                control_type="Edit",
                class_name="RichEdit",
                automation_id="composer-1",
                framework_id="uia",
                runtime_id=(7, 8, 9),
            )

            @staticmethod
            def rectangle():
                return SimpleNamespace(left=10, top=20, right=410, bottom=60)

            @staticmethod
            def is_visible():
                return True

            @staticmethod
            def is_enabled():
                return True

        with patch("floatingbar.control_candidates.winapi.get_window_pid", return_value=200), \
             patch("floatingbar.control_candidates.winapi.get_focused_hwnd", return_value=301):
            candidate = _candidate_from_element(Element(), 200, 100)

        self.assertEqual(candidate.automation_id, "composer-1")
        self.assertEqual(candidate.framework_id, "uia")
        self.assertEqual(candidate.runtime_id, (7, 8, 9))

    def test_conflicting_wrappers_for_one_hwnd_are_discarded(self):
        first = InputCandidate(
            300, 200, "Edit", "Edit", 0, 0, 400, 40, True, True, True,
            automation_id="composer", framework_id="uia", runtime_id=(1, 2, 3),
        )
        conflicting = InputCandidate(
            300, 200, "Edit", "Edit", 0, 0, 400, 40, True, True, True,
            automation_id="search", framework_id="uia", runtime_id=(4, 5, 6),
        )
        with patch("floatingbar.control_candidates.winapi.user32.IsWindow", return_value=True), \
             patch("floatingbar.control_candidates.winapi.get_window_pid", return_value=200), \
             patch(
                 "floatingbar.control_candidates._candidate_from_element",
                 side_effect=[first, conflicting],
             ):
            with patch("pywinauto.Desktop") as desktop:
                root = desktop.return_value.window.return_value
                element_a = object()
                element_b = object()
                root.descendants.side_effect = [[], [element_a, element_b]]
                result = enumerate_input_candidates(100)

        self.assertEqual(result, ())

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
