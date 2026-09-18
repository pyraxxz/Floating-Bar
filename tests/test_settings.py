import json
import tempfile
import unittest
from pathlib import Path

from floatingbar.settings import AppSettings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_defaults_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(str(Path(directory) / "settings.json"))
            self.assertEqual(store.idle_collapse_ms, 4000)

    def test_idle_setting_is_bounded_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(str(path))
            store.update_idle_collapse_ms(1)
            self.assertEqual(store.idle_collapse_ms, 2000)
            store.update_idle_collapse_ms(30)
            self.assertEqual(store.idle_collapse_ms, 15000)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["idle_collapse_seconds"], 15)

    def test_invalid_payload_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"version": 99, "idle_collapse_seconds": 12}', encoding="utf-8")
            store = SettingsStore(str(path))
            self.assertEqual(store.settings, AppSettings())

    def test_non_numeric_idle_value_uses_default(self):
        self.assertEqual(AppSettings.normalize_idle("not-a-number"), 4000)


if __name__ == "__main__":
    unittest.main()
