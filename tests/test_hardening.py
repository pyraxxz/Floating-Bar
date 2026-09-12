import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.hardening import (
    HardenedTelegramInjector,
    _is_explicit_send_name,
    _is_voice_name,
)
from floatingbar.injector import InjectionFailed, _nested


class Rect:
    def __init__(self, left, top, right, bottom):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeEdit:
    def __init__(self, rect, length):
        self._rect = rect
        self.length = length
        self.element_info = SimpleNamespace(runtime_id=(1, 2, length))

    def rectangle(self):
        return self._rect

    @property
    def iface_value(self):
        return SimpleNamespace(CurrentValue="x" * self.length)


class HardeningTests(unittest.TestCase):
    def test_nested_rects_detect_same_visual_field(self):
        outer = Rect(100, 200, 500, 260)
        inner = Rect(101, 201, 499, 259)
        separate = Rect(100, 300, 500, 360)
        self.assertTrue(_nested(outer, inner))
        self.assertFalse(_nested(outer, separate))

    def test_voice_names_are_never_explicit_send(self):
        for name in ("Microphone", "Record voice", "Audio message", "Voice"):
            self.assertTrue(_is_voice_name(name))
            self.assertFalse(_is_explicit_send_name(name))

    def test_explicit_send_name_is_safe_candidate(self):
        self.assertTrue(_is_explicit_send_name("Send"))
        self.assertTrue(_is_explicit_send_name("Send message"))
        self.assertFalse(_is_explicit_send_name(""))
        self.assertFalse(_is_explicit_send_name("Emoji"))

    def test_land_clicks_compose_before_posting_text_and_uses_focused_child(self):
        events = []
        target = Mock()
        target.compose_click_point.return_value = (77, 88)
        injector = HardenedTelegramInjector(target)

        def click(*args):
            events.append("click")

        def text(*args):
            events.append(("text", args[0]))

        with patch("floatingbar.hardening.winapi.post_click", side_effect=click), \
             patch("floatingbar.hardening.winapi.get_focused_hwnd", return_value=456), \
             patch("floatingbar.hardening.winapi.get_window_pid", side_effect=[10, 10]), \
             patch("floatingbar.hardening.winapi.post_text", side_effect=text), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._land_text(SimpleNamespace(), 123, "ignored")

        self.assertEqual(result, "A2-child")
        self.assertEqual(events, ["click", ("text", 456)])

    def test_unverified_ambiguous_button_falls_back_to_enter_without_click(self):
        target = Mock()
        target.send_button_click.return_value = ("Emoji", 20, 30)
        injector = HardenedTelegramInjector(target)
        posted = Mock()
        enter = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.winapi.post_enter", enter), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._submit_invisible(object(), 123, False, "unknown")

        self.assertEqual(result, "posted-enter (unverified)")
        posted.assert_not_called()
        self.assertEqual(enter.call_count, 2)

    def test_unverified_explicit_send_button_is_clicked(self):
        target = Mock()
        target.send_button_click.return_value = ("Send", 20, 30)
        injector = HardenedTelegramInjector(target)
        posted = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._submit_invisible(object(), 123, False, "unknown")

        self.assertEqual(result, "posted-click (unverified-explicit-send)")
        posted.assert_called_once_with(123, 20, 30)

    def test_unverified_voice_button_raises_and_never_clicks(self):
        target = Mock()
        target.send_button_click.return_value = ("Voice message", 20, 30)
        injector = HardenedTelegramInjector(target)
        posted = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted):
            with self.assertRaises(InjectionFailed):
                injector._submit_invisible(object(), 123, False, "unknown")

        posted.assert_not_called()

    def test_audit_prefers_compose_over_prefilled_search_field(self):
        compose = FakeEdit(Rect(100, 700, 700, 760), 12)
        search = FakeEdit(Rect(100, 80, 500, 120), 6)
        target = Mock()
        target.edit_audit.return_value = (search, [(search, "search"), (compose, "compose")])
        injector = HardenedTelegramInjector(target)

        with patch("floatingbar.hardening.time.sleep"):
            result, edit = injector._audit(compose)

        self.assertEqual(result, "found")
        self.assertIs(edit, compose)


if __name__ == "__main__":
    unittest.main()
