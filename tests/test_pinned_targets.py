import json
import os
import tempfile
import unittest

from floatingbar.pinned_targets import PinnedTarget, PinnedTargetStore


class PinnedTargetStoreTests(unittest.TestCase):
    def _store(self, directory, limit=6):
        return PinnedTargetStore(os.path.join(directory, "pins.json"), limit=limit)

    def test_round_trip_persists_only_safe_identity_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            self.assertTrue(
                store.toggle_application(
                    adapter_key="slack",
                    process_name="slack.exe",
                    label="Slack",
                )
            )
            self.assertTrue(
                store.toggle_conversation(
                    adapter_key="slack",
                    process_name="slack.exe",
                    label="Project Chat",
                )
            )
            path = os.path.join(directory, "pins.json")
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["version"], 1)
            self.assertEqual(set(payload["pins"][0]), {"kind", "adapter_key", "process_name", "label"})
            self.assertNotIn("hwnd", payload["pins"][0])
            self.assertNotIn("pid", payload["pins"][0])
            reloaded = PinnedTargetStore(path)
            self.assertEqual(reloaded.items(), store.items())

    def test_toggle_is_idempotent_by_stable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            first = store.toggle_conversation(
                adapter_key="teams", process_name="teams.exe", label="Team Chat"
            )
            second = store.toggle_conversation(
                adapter_key="teams", process_name="TEAMS.EXE", label="team chat"
            )
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertEqual(len(store), 0)

    def test_limit_keeps_most_recent_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory, limit=2)
            for index in range(3):
                store.toggle_application(
                    adapter_key=f"adapter-{index}",
                    process_name=f"app-{index}.exe",
                    label=f"App {index}",
                )
            self.assertEqual(
                [item.label for item in store.items()],
                ["App 2", "App 1"],
            )

    def test_malformed_file_fails_closed_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pins.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not json")
            store = PinnedTargetStore(path)
            self.assertEqual(store.items(), ())

    def test_invalid_target_is_never_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            self.assertFalse(
                store._toggle(PinnedTarget("invalid", "", "", ""))
            )
            self.assertEqual(store.items(), ())


if __name__ == "__main__":
    unittest.main()
