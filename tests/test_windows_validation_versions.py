import unittest

from floatingbar.windows_validation import AdapterObservation, WindowsValidationSnapshot, _observe_adapters, format_report


class WindowsValidationVersionTests(unittest.TestCase):
    def test_observation_can_carry_content_free_executable_versions(self):
        observations = _observe_adapters(
            ["telegram.exe", "telegram.exe", "discord.exe"],
            {"telegram.exe": {"5.9.1.0", "5.9.1.0"}, "discord.exe": {"1.0.2.0"}},
        )
        by_key = {item.key: item for item in observations}

        self.assertEqual(by_key["telegram"].observed_versions, ("5.9.1.0",))
        self.assertEqual(by_key["discord"].observed_versions, ("1.0.2.0",))

    def test_version_data_is_serialized_without_window_content(self):
        snapshot = WindowsValidationSnapshot(
            1,
            "Windows",
            "11",
            "10.0.26100",
            "",
            "AMD64",
            "3.12.10",
            1,
            "per-monitor",
            1,
            (
                AdapterObservation(
                    "telegram",
                    "Telegram",
                    ("telegram.exe",),
                    1,
                    ("telegram.exe",),
                    ("5.9.1.0",),
                ),
            ),
        )
        payload = snapshot.to_dict()
        self.assertEqual(payload["adapters"][0]["observed_versions"], ["5.9.1.0"])
        self.assertNotIn("title", str(payload).lower())
        self.assertNotIn("message", str(payload).lower())
        self.assertIn("versions=5.9.1.0", format_report(snapshot))


if __name__ == "__main__":
    unittest.main()
