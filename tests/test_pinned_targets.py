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
                    window_class="SlackWindow",
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
            self.assertEqual(payload["version"], 5)
            by_kind = {item["kind"]: item for item in payload["pins"]}
            self.assertEqual(
                set(by_kind["application"]),
                {"kind", "adapter_key", "process_name", "label", "window_class"},
            )
            self.assertEqual(
                set(by_kind["conversation"]),
                {"kind", "adapter_key", "process_name", "label"},
            )
            for item in payload["pins"]:
                self.assertNotIn("hwnd", item)
                self.assertNotIn("pid", item)
            reloaded = PinnedTargetStore(path)
            self.assertEqual(reloaded.items(), store.items())

    def test_application_pin_serializes_window_class_as_safe_identity(self):
        pin = PinnedTarget(
            kind="application",
            adapter_key="slack",
            process_name="slack.exe",
            label="Slack",
            window_class="SlackWindow",
        )
        payload = pin.to_dict()
        self.assertEqual(payload["window_class"], "SlackWindow")
        self.assertNotIn("hwnd", payload)
        self.assertNotIn("pid", payload)

    def test_application_pin_round_trips_window_class_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            self.assertTrue(
                store.toggle_application(
                    adapter_key="discord",
                    process_name="discord.exe",
                    label="Discord",
                    window_class="Chrome_WidgetWin_1",
                )
            )
            reloaded = PinnedTargetStore(os.path.join(directory, "pins.json"))
            self.assertEqual(reloaded.items()[0].window_class, "Chrome_WidgetWin_1")
            with open(os.path.join(directory, "pins.json"), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["pins"][0]["window_class"], "Chrome_WidgetWin_1")

    def test_conversation_pin_round_trips_structural_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            identity = ("ListItem", "row", "uia")
            self.assertTrue(
                store.toggle_conversation(
                    adapter_key="discord",
                    process_name="discord.exe",
                    label="general",
                    control_identity=identity,
                )
            )
            reloaded = PinnedTargetStore(os.path.join(directory, "pins.json"))
            self.assertEqual(reloaded.items()[0].control_identity, identity)
            self.assertIsNone(reloaded.items()[0].container_identity)
            with open(os.path.join(directory, "pins.json"), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["pins"][0]["control_identity"], list(identity))

    def test_conversation_pin_round_trips_container_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            identity = ("ancestor1", "Pane", "workspace", "uia")
            self.assertTrue(
                store.toggle_conversation(
                    adapter_key="slack",
                    process_name="slack.exe",
                    label="Project Chat",
                    container_identity=identity,
                )
            )
            reloaded = PinnedTargetStore(os.path.join(directory, "pins.json"))
            self.assertEqual(reloaded.items()[0].container_identity, identity)
            with open(os.path.join(directory, "pins.json"), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(payload["pins"][0]["container_identity"], list(identity))

    def test_structural_conversation_pin_deduplicates_across_display_name_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            identity = ("ListItem", "row", "uia")
            self.assertTrue(
                store.toggle_conversation(
                    adapter_key="discord",
                    process_name="discord.exe",
                    label="general",
                    control_identity=identity,
                )
            )
            self.assertFalse(
                store.toggle_conversation(
                    adapter_key="discord",
                    process_name="discord.exe",
                    label="general-renamed",
                    control_identity=identity,
                )
            )
            self.assertEqual(len(store), 0)

    def test_structural_pin_matches_renamed_live_conversation(self):
        pin = PinnedTarget(
            kind="conversation",
            adapter_key="discord",
            process_name="discord.exe",
            label="general",
            control_identity=("ListItem", "row", "uia"),
        )
        renamed = type("Row", (), {
            "name": "renamed-general",
            "control_identity": ("ListItem", "channel-42", "row", "uia"),
            "container_identity": None,
        })()
        self.assertTrue(pin.matches_conversation(renamed))

    def test_structural_pin_rejects_changed_live_conversation_identity(self):
        pin = PinnedTarget(
            kind="conversation",
            adapter_key="discord",
            process_name="discord.exe",
            label="general",
            control_identity=("ListItem", "channel-42", "row", "uia"),
        )
        changed = type("Row", (), {
            "name": "general",
            "control_identity": ("ListItem", "row-changed", "uia"),
            "container_identity": None,
        })()
        self.assertFalse(pin.matches_conversation(changed))

    def test_name_only_pin_uses_display_label_as_fallback_identity(self):
        pin = PinnedTarget(
            kind="conversation",
            adapter_key="teams",
            process_name="teams.exe",
            label="Project Chat",
        )
        same = type("Row", (), {
            "name": "Project Chat",
            "control_identity": None,
            "container_identity": None,
        })()
        renamed = type("Row", (), {
            "name": "Renamed Project Chat",
            "control_identity": None,
            "container_identity": None,
        })()
        self.assertTrue(pin.matches_conversation(same))
        self.assertFalse(pin.matches_conversation(renamed))

    def test_schema_four_conversation_pin_drops_legacy_structural_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pins.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": 4,
                        "pins": [
                            {
                                "kind": "conversation",
                                "adapter_key": "discord",
                                "process_name": "discord.exe",
                                "label": "general",
                                "control_identity": ["ListItem", "general", "row", "uia"],
                                "container_identity": ["ancestor1", "Pane", "general", "uia"],
                            }
                        ],
                    },
                    handle,
                )
            store = PinnedTargetStore(path)
            self.assertIsNone(store.items()[0].control_identity)
            self.assertIsNone(store.items()[0].container_identity)
            with open(path, "r", encoding="utf-8") as handle:
                rewritten = json.load(handle)
            self.assertEqual(rewritten["version"], 5)
            self.assertNotIn("control_identity", rewritten["pins"][0])
            self.assertNotIn("container_identity", rewritten["pins"][0])

    def test_schema_one_conversation_pin_loads_without_structural_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pins.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": 1,
                        "pins": [
                            {
                                "kind": "conversation",
                                "adapter_key": "discord",
                                "process_name": "discord.exe",
                                "label": "general",
                            }
                        ],
                    },
                    handle,
                )
            store = PinnedTargetStore(path)
            self.assertEqual(store.items()[0].control_identity, None)
            self.assertEqual(store.items()[0].container_identity, None)
            self.assertEqual(store.items()[0].window_class, None)

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
                    window_class=f"AppWindowClass{index}",
                )
            self.assertEqual(
                [item.label for item in store.items()],
                ["App 2", "App 1"],
            )

    def test_classless_application_pin_is_rejected(self):
        pin = PinnedTarget(
            kind="application",
            adapter_key="demo",
            process_name="demo.exe",
            label="Demo",
            window_class=None,
        )
        self.assertFalse(pin.valid)

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
