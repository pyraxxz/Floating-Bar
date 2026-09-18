import json
import tempfile
import unittest
from pathlib import Path

from floatingbar.settings import AppSettings, SettingsStore, hotkey_spec_for_name, normalize_hotkey


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
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["idle_collapse_seconds"], 15)
            self.assertEqual(payload["summon_hotkey"], "Ctrl+Alt+Space")

    def test_invalid_payload_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"version": 99, "idle_collapse_seconds": 12}', encoding="utf-8")
            store = SettingsStore(str(path))
            self.assertEqual(store.settings, AppSettings())

    def test_non_numeric_idle_value_uses_default(self):
        self.assertEqual(AppSettings.normalize_idle("not-a-number"), 4000)

    def test_hotkey_is_bounded_to_known_choices(self):
        self.assertEqual(normalize_hotkey("Ctrl+Shift+Space"), "Ctrl+Shift+Space")
        self.assertEqual(normalize_hotkey("not-a-hotkey"), "Ctrl+Alt+Space")
        self.assertEqual(hotkey_spec_for_name("Ctrl+Alt+Enter"), (0x0002 | 0x0001, 0x0D))

    def test_hotkey_persists_with_schema_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            store = SettingsStore(str(path))
            store.update_summon_hotkey("Ctrl+Shift+Space")
            reloaded = SettingsStore(str(path))
            self.assertEqual(reloaded.settings.summon_hotkey, "Ctrl+Shift+Space")

    def test_schema_v1_migrates_to_default_hotkey(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                '{"version": 1, "idle_collapse_seconds": 8}',
                encoding="utf-8",
            )
            store = SettingsStore(str(path))
            self.assertEqual(store.settings.idle_collapse_ms, 8000)
            self.assertEqual(store.settings.summon_hotkey, "Ctrl+Alt+Space")


if __name__ == "__main__":
    unittest.main()
