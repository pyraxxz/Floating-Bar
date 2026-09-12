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

    def test_land_clicks_compose_before_posting_text(self):
        events = []
        target = Mock()
        target.compose_click_point.return_value = (77, 88)
        injector = HardenedTelegramInjector(target)

        def click(*args):
            events.append("click")

        def text(*args):
            events.append("text")

        with patch("floatingbar.hardening.winapi.post_click", side_effect=click), \
             patch("floatingbar.hardening.time.sleep"), \
             patch("floatingbar.hardening.TelegramInjector._land_text", side_effect=text):
            result = injector._land_text(SimpleNamespace(), 123, "ignored")

        self.assertEqual(result, None)
        self.assertEqual(events, ["click", "text"])

    def test_unverified_ambiguous_button_falls_back_to_enter_without_click(self):
        target = Mock()
        target.send_button_click.return_value = ("Emoji", 20, 30)
        injector = HardenedTelegramInjector(target)
        posted = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.winapi.post_enter", Mock()), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._submit_invisible(object(), 123, False, "unknown")

        self.assertEqual(result, "posted-enter (unverified)")
        posted.assert_not_called()

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


if __name__ == "__main__":
    unittest.main()
