import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.target import TelegramTarget


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left, self.top = left, top
        self.right, self.bottom = right, bottom

    def width(self):
        return self.right - self.left

    def height(self):
        return self.bottom - self.top


class FakeEdit:
    def __init__(self, rect, rid=(1, 2), readonly=False):
        self._rect = rect
        self.element_info = SimpleNamespace(runtime_id=rid)
        self._readonly = readonly

    def rectangle(self):
        return self._rect

    @property
    def iface_value(self):
        return SimpleNamespace(CurrentIsReadOnly=self._readonly, CurrentValue="")


class FakeButton:
    def __init__(self, rect, name="", enabled=True):
        self._rect = rect
        self.element_info = SimpleNamespace(name=name)
        self._enabled = enabled

    def rectangle(self):
        return self._rect

    def is_enabled(self):
        return self._enabled


class FakeWindow:
    def __init__(self, rect, buttons):
        self._rect = rect
        self._buttons = buttons

    def rectangle(self):
        return self._rect

    def descendants(self, control_type=None):
        if control_type == "Button":
            return self._buttons
        return []


class TargetResilienceTests(unittest.TestCase):
    def test_refresh_clears_remembered_runtime_id_when_window_scope_changes(self):
        target = TelegramTarget()
        target._hwnd = 100
        target._pid = 10
        target._preferred_rid = (7, 8, 9)
        target._preferred_scope = (100, 10)

        with patch(
            "floatingbar.target.winapi.find_windows",
            return_value=[(200, 20, 1000, "Chat", "Telegram.exe")],
        ):
            target.refresh()

        self.assertEqual(target._hwnd, 200)
        self.assertEqual(target._pid, 20)
        self.assertIsNone(target._preferred_rid)
        self.assertIsNone(target._preferred_scope)

    def test_preferred_foreground_telegram_window_is_selected(self):
        target = TelegramTarget()
        matches = [
            (100, 10, 900000, "Telegram", "Telegram.exe"),
            (200, 20, 500000, "Telegram", "Telegram.exe"),
        ]
        with patch(
            "floatingbar.target.winapi.find_windows",
            return_value=matches,
        ), patch(
            "floatingbar.target.winapi.user32.IsWindow",
            return_value=True,
        ):
            selected = target.select_for_send(preferred_hwnd=200)

        self.assertEqual(selected, 200)
        self.assertEqual(target._pid, 20)

    def test_non_telegram_preferred_hwnd_falls_back_to_largest_match(self):
        target = TelegramTarget()
        matches = [
            (100, 10, 900000, "Telegram", "Telegram.exe"),
            (200, 20, 500000, "Telegram", "Telegram.exe"),
        ]
        with patch(
            "floatingbar.target.winapi.find_windows",
            return_value=matches,
        ), patch(
            "floatingbar.target.winapi.user32.IsWindow",
            return_value=True,
        ):
            selected = target.select_for_send(preferred_hwnd=999)

        self.assertEqual(selected, 100)
        self.assertEqual(target._pid, 10)

    def test_remembered_compose_must_stay_in_lower_part_of_window(self):
        window = FakeWindow(Rect(0, 0, 1000, 1000), [])
        valid = FakeEdit(Rect(100, 700, 700, 760))
        invalid = FakeEdit(Rect(100, 80, 700, 140))
        self.assertTrue(TelegramTarget._remembered_compose_is_valid(valid, window))
        self.assertFalse(TelegramTarget._remembered_compose_is_valid(invalid, window))

    def test_send_button_ignores_far_bottom_unrelated_button(self):
        target = TelegramTarget()
        target._hwnd = 100
        target._pid = 10
        window = FakeWindow(
            Rect(0, 0, 1000, 1000),
            [
                FakeButton(Rect(930, 920, 970, 960), "", True),
                FakeButton(Rect(730, 710, 770, 750), "", True),
            ],
        )
        box = FakeEdit(Rect(100, 700, 700, 760))

        with patch("floatingbar.target.winapi.user32.IsWindow", return_value=True), \
             patch.object(target, "_window", return_value=window):
            result = target.send_button_click(near_box=box)

        self.assertIsNotNone(result)
        self.assertEqual(result[1:], (750, 730))

    def test_disabled_button_is_not_selected(self):
        target = TelegramTarget()
        target._hwnd = 100
        target._pid = 10
        window = FakeWindow(
            Rect(0, 0, 1000, 1000),
            [
                FakeButton(Rect(730, 710, 770, 750), "Send", False),
                FakeButton(Rect(780, 710, 820, 750), "Send", True),
            ],
        )
        box = FakeEdit(Rect(100, 700, 700, 760))

        with patch("floatingbar.target.winapi.user32.IsWindow", return_value=True), \
             patch.object(target, "_window", return_value=window):
            result = target.send_button_click(near_box=box)

        self.assertEqual(result[0], "Send")
        self.assertEqual(result[1:], (800, 730))


if __name__ == "__main__":
    unittest.main()
