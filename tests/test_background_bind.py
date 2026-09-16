"""Regression coverage for safe generic-target readiness feedback."""

import unittest
from unittest.mock import Mock

from floatingbar.bound_context_overlay import OrbRelayWindow


class BackgroundBindTests(unittest.TestCase):
    def _window(self):
        window = OrbRelayWindow.__new__(OrbRelayWindow)
        window._background_typer = Mock()
        window._state = "orb"
        window._sending = False
        window._update_status = Mock()
        window._show_bar = Mock()
        window._show_feedback = Mock()
        return window

    def test_bind_shows_bar_when_structural_input_is_available(self):
        window = self._window()
        window._background_typer.probe.return_value = Mock(available=True, candidate_count=1)

        window._bind_generic_target(100, 200)

        window._background_typer.bind.assert_called_once_with(100, 200)
        window._background_typer.probe.assert_called_once_with()
        window._update_status.assert_called_once_with()
        window._show_bar.assert_called_once_with()
        window._show_feedback.assert_not_called()

    def test_bind_reports_unavailable_target_without_opening_dead_bar(self):
        window = self._window()
        window._background_typer.probe.return_value = Mock(available=False, candidate_count=0)

        window._bind_generic_target(100, 200)

        window._background_typer.bind.assert_called_once_with(100, 200)
        window._update_status.assert_called_once_with()
        window._show_bar.assert_not_called()
        window._show_feedback.assert_called_once_with(
            "That app is open, but no safe background typing control is available."
        )

    def test_bind_reports_missing_structural_control_without_opening_dead_bar(self):
        window = self._window()
        window._background_typer.probe.return_value = Mock(available=True, candidate_count=0)

        window._bind_generic_target(100, 200)

        window._show_bar.assert_not_called()
        window._show_feedback.assert_called_once_with(
            "That app is open, but no safe background typing control is available."
        )

    def test_bind_does_not_hide_failure_feedback_when_already_sending(self):
        window = self._window()
        window._sending = True
        window._background_typer.probe.return_value = Mock(available=False, candidate_count=0)

        window._bind_generic_target(100, 200)

        window._show_feedback.assert_called_once()
        window._show_bar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
