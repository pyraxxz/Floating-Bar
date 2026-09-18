import unittest

from floatingbar.app_adapters import adapter_for_process
from floatingbar.windows_validation import (
    AdapterObservation,
    MonitorObservation,
    WindowsValidationSnapshot,
    _observe_adapters,
    format_report,
)


class WindowsValidationTests(unittest.TestCase):
    def test_observation_counts_multiple_windows_for_one_adapter(self):
        observations = _observe_adapters(
            ["telegram.exe", "telegram.exe", "discord.exe", "msteams.exe"]
        )
        by_key = {item.key: item for item in observations}

        self.assertEqual(by_key["telegram"].open_window_count, 2)
        self.assertEqual(by_key["telegram"].observed_processes, ("telegram.exe",))
        self.assertEqual(by_key["discord"].open_window_count, 1)
        self.assertEqual(by_key["teams"].open_window_count, 1)

    def test_aliases_share_one_adapter_observation(self):
        observations = _observe_adapters(["teams.exe", "msteams.exe", "ms-teams.exe"])
        teams = next(item for item in observations if item.key == "teams")

        self.assertEqual(teams.open_window_count, 3)
        self.assertEqual(
            teams.observed_processes,
            ("msteams.exe", "ms-teams.exe", "teams.exe"),
        )

    def test_snapshot_serialization_is_content_free(self):
        snapshot = WindowsValidationSnapshot(
            schema_version=1,
            platform="Windows",
            windows_release="11",
            windows_version="10.0.26100",
            windows_service_pack="",
            architecture="AMD64",
            python_version="3.13.0",
            monitor_count=2,
            dpi_awareness="per-monitor",
            observed_window_count=4,
            adapters=(
                AdapterObservation(
                    "telegram",
                    "Telegram",
                    ("telegram.exe",),
                    2,
                    ("telegram.exe",),
                ),
            ),
            monitors=(
                MonitorObservation(0, 1920, 1080, 96, 96),
                MonitorObservation(1, 2560, 1440, 144, 144),
            ),
        )
        payload = snapshot.to_dict()
        self.assertNotIn("title", str(payload).lower())
        self.assertNotIn("message", str(payload).lower())
        self.assertEqual(payload["monitor_count"], 2)
        self.assertEqual(len(payload["monitors"]), 2)
        self.assertEqual(payload["monitors"][1]["dpi_x"], 144)
        self.assertEqual(payload["adapters"][0]["open_window_count"], 2)

    def test_report_uses_adapter_labels_not_window_titles(self):
        snapshot = WindowsValidationSnapshot(
            2,
            "Windows",
            "11",
            "10.0.26100",
            "",
            "AMD64",
            "3.13.0",
            1,
            "per-monitor",
            1,
            (
                AdapterObservation(
                    adapter_for_process("telegram.exe").key,
                    "Telegram",
                    ("telegram.exe",),
                    1,
                    ("telegram.exe",),
                ),
            ),
        )
        report = format_report(snapshot)
        self.assertIn("Telegram: open_window_count=1", report)
        self.assertNotIn("chat", report.lower())


if __name__ == "__main__":
    unittest.main()
