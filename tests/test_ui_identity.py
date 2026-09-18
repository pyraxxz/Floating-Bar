import unittest
from types import SimpleNamespace

from floatingbar.ui_identity import ancestor_identity, control_identity


class UiIdentityTests(unittest.TestCase):
    def test_control_identity_excludes_automation_id(self):
        info = SimpleNamespace(
            control_type="ListItem",
            automation_id="Private Chat",
            class_name="ChatRow",
            framework_id="uia",
        )
        self.assertEqual(control_identity(info), ("ListItem", "ChatRow", "uia"))

    def test_ancestor_identity_excludes_automation_id(self):
        ancestor = SimpleNamespace(
            element_info=SimpleNamespace(
                control_type="Pane",
                automation_id="Private Chat",
                class_name="ChatList",
                framework_id="uia",
            ),
            parent=lambda: (_ for _ in ()).throw(RuntimeError("no parent")),
        )
        child = SimpleNamespace(parent=lambda: ancestor)
        self.assertEqual(
            ancestor_identity(child),
            ("ancestor1", "Pane", "ChatList", "uia"),
        )


if __name__ == "__main__":
    unittest.main()
