import json
import os
import tempfile
import unittest

from floatingbar.quick_replies import QuickReplyStore


class QuickReplyStoreTests(unittest.TestCase):
    def _store(self, directory, limit=12):
        return QuickReplyStore(os.path.join(directory, "replies.json"), limit=limit)

    def test_round_trip_preserves_user_authored_reply(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            reply = store.upsert("On my way", "I will be there shortly.")
            reloaded = self._store(directory)
            self.assertEqual(reloaded.items(), (reply,))

    def test_update_keeps_identifier_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            first = store.upsert("One", "First")
            second = store.upsert("Two", "Second")
            updated = store.upsert("Two updated", "Changed", second.id)
            self.assertEqual(updated.id, second.id)
            self.assertEqual([item.id for item in store.items()], [second.id, first.id])
            self.assertEqual(store.get(second.id).text, "Changed")

    def test_new_replies_are_bounded_and_most_recent_first(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory, limit=2)
            store.upsert("One", "1")
            store.upsert("Two", "2")
            store.upsert("Three", "3")
            self.assertEqual([item.label for item in store.items()], ["Three", "Two"])

    def test_invalid_empty_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            with self.assertRaises(ValueError):
                store.upsert("", "text")
            with self.assertRaises(ValueError):
                store.upsert("label", "")

    def test_malformed_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "replies.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("not json")
            store = QuickReplyStore(path)
            self.assertEqual(store.items(), ())

    def test_storage_contains_only_explicitly_saved_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory)
            store.upsert("Greeting", "Hello there")
            with open(os.path.join(directory, "replies.json"), "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertEqual(set(payload["replies"][0]), {"id", "label", "text"})
            self.assertNotIn("hwnd", payload["replies"][0])
            self.assertNotIn("pid", payload["replies"][0])


if __name__ == "__main__":
    unittest.main()
