import os
import tempfile
import unittest
from unittest.mock import patch

from floatingbar import onboarding


class OnboardingTests(unittest.TestCase):
    def test_missing_marker_is_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "FloatingBar", "first-run-seen")
            with patch.object(onboarding, "_MARKER_PATH", marker):
                self.assertFalse(onboarding.has_seen())

    def test_mark_seen_persists_marker_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "FloatingBar", "first-run-seen")
            with patch.object(onboarding, "_MARKER_PATH", marker):
                onboarding.mark_seen()
                self.assertTrue(os.path.isfile(marker))
                onboarding.mark_seen()
                self.assertTrue(onboarding.has_seen())

    def test_marker_path_exposes_configured_location(self):
        with patch.object(onboarding, "_MARKER_PATH", "C:/FloatingBar/first-run-seen"):
            self.assertEqual(onboarding.marker_path(), "C:/FloatingBar/first-run-seen")


if __name__ == "__main__":
    unittest.main()
