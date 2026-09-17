import unittest
from types import SimpleNamespace
from unittest.mock import patch

from floatingbar.app_adapters import adapter_for_process
from floatingbar.chat_composer_target import ChatComposerTarget


class ChatConversationGuardTests(unittest.TestCase):
    def _target(self):
        target = ChatComposerTarget(100, 200)
        target.bind(100, 200, spec=adapter_for_process("whatsapp.exe"))
        return target

    def _conversation(self, selected=True):
        return SimpleNamespace(
            hwnd=100,
            pid=200,
            name="Conversation",
            left=10,
            top=100,
            right=300,
            bottom=140,
            selected=selected,
            runtime_id=(1, 2, 3),
            control_identity=("ListItem", "", "ConversationRow"),
        )

    def _scope_patches(self):
        return (
            patch("floatingbar.generic_target.winapi.user32.IsWindow", return_value=True),
            patch("floatingbar.generic_target.winapi.user32.IsWindowVisible", return_value=True),
            patch("floatingbar.generic_target.winapi.get_window_pid", return_value=200),
        )

    def test_scope_without_selected_conversation_guard_remains_compatible(self):
        target = self._target()
        runtime = self._scope_patches()
        with runtime[0], runtime[1], runtime[2]:
            self.assertTrue(target.available())

    def test_bound_conversation_requires_same_row_to_remain_selected(self):
        target = self._target()
        target._conversation_guard = self._conversation(selected=True)
        runtime = self._scope_patches()
        with runtime[0], runtime[1], runtime[2], \
             patch("floatingbar.chat_composer_target.refresh_conversation", return_value=self._conversation(selected=False)):
            self.assertFalse(target.available())

    def test_bound_conversation_allows_send_when_same_row_remains_selected(self):
        target = self._target()
        target._conversation_guard = self._conversation(selected=True)
        runtime = self._scope_patches()
        with runtime[0], runtime[1], runtime[2], \
             patch("floatingbar.chat_composer_target.refresh_conversation", return_value=self._conversation(selected=True)):
            self.assertTrue(target.available())

    def test_conversation_switch_blocks_before_text_injection(self):
        target = self._target()
        target._conversation_guard = self._conversation(selected=True)
        runtime = self._scope_patches()
        with runtime[0], runtime[1], runtime[2], \
             patch.object(target, "_conversation_is_still_selected", return_value=False), \
             patch("floatingbar.generic_target.winapi.post_text") as post_text:
            with self.assertRaisesRegex(RuntimeError, "discovered editable composer"):
                target.send("hello")

        post_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
