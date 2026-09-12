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
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)

        def click(*args):
            events.append("click")

        def text(*args):
            events.append(("text", args[0]))

        with patch("floatingbar.hardening.winapi.post_click", side_effect=click), \
             patch("floatingbar.hardening.winapi.get_focused_hwnd", return_value=456), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=10), \
             patch("floatingbar.hardening.winapi.post_text", side_effect=text), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._land_text(SimpleNamespace(), 123, "ignored")

        self.assertEqual(result, "A2-child")
        self.assertEqual(events, ["click", ("text", 456)])

    def test_unverified_ambiguous_button_falls_back_to_enter_without_click(self):
        target = Mock()
        target.send_button_click.return_value = ("Emoji", 20, 30)
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        posted = Mock()
        enter = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.winapi.post_enter", enter), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._submit_invisible(object(), 123, False, "unknown")

        self.assertEqual(result, "posted-enter (unverified)")
        posted.assert_not_called()
        self.assertEqual(enter.call_count, 2)

    def test_unverified_explicit_send_button_is_clicked(self):
        target = Mock()
        target.send_button_click.return_value = ("Send", 20, 30)
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        posted = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._submit_invisible(object(), 123, False, "unknown")

        self.assertEqual(result, "posted-click (unverified-explicit-send)")
        posted.assert_called_once_with(123, 20, 30)

    def test_unverified_voice_button_raises_and_never_clicks(self):
        target = Mock()
        target.send_button_click.return_value = ("Voice message", 20, 30)
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        posted = Mock()

        with patch("floatingbar.hardening.winapi.post_click", posted), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1):
            with self.assertRaises(InjectionFailed):
                injector._submit_invisible(object(), 123, False, "unknown")

        posted.assert_not_called()

    def test_audit_prefers_compose_over_prefilled_search_field(self):
        compose = FakeEdit(Rect(100, 700, 700, 760), 12)
        search = FakeEdit(Rect(100, 80, 500, 120), 6)
        target = Mock()
        target.edit_audit.return_value = (
            search,
            [(search, "search"), (compose, "compose")],
        )
        injector = HardenedTelegramInjector(target)

        with patch("floatingbar.hardening.time.sleep"):
            result, edit = injector._audit(compose)

        self.assertEqual(result, "found")
        self.assertIs(edit, compose)

    def test_submit_verification_accepts_delayed_compose_clear(self):
        box = Mock()
        target = Mock()
        target.send_button_click.return_value = ("Send", 20, 30)
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        injector._value_length = Mock(side_effect=[12, 12, 0])

        with patch("floatingbar.hardening.winapi.post_click") as posted, \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1), \
             patch("floatingbar.hardening.time.sleep") as sleeping:
            result = injector._submit_invisible(box, 123, False, "compose")

        self.assertEqual(result, "posted-click (VERIFIED)")
        posted.assert_called_once_with(123, 20, 30)
        self.assertGreaterEqual(sleeping.call_count, 1)

    def test_poll_compose_clear_returns_none_when_readback_is_unavailable(self):
        with patch("floatingbar.hardening.time.sleep"):
            result = HardenedTelegramInjector._poll_compose_clear(lambda: -1)
        self.assertIsNone(result)

    def test_strategy_b_refuses_failed_clipboard_write(self):
        target = Mock()
        target.hwnd = 123
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        box = Mock()
        guard = Mock()
        guard.__enter__ = Mock(return_value=guard)
        guard.__exit__ = Mock(return_value=False)

        with patch(
            "floatingbar.hardening.clipboard_guard.preserved_clipboard",
            return_value=guard,
        ), patch(
            "floatingbar.hardening.clipboard_guard.set_text",
            return_value=False,
        ), patch("floatingbar.hardening.winapi.get_foreground_window", return_value=999), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1), \
             patch("floatingbar.hardening.winapi.set_foreground_window", return_value=True), \
             patch("floatingbar.hardening.winapi.ensure_restored"), \
             patch("floatingbar.hardening.time.sleep"):
            self.assertFalse(injector._strategy_b(box, "hello", False, 999))

        pasted = [call for call in box.type_keys.call_args_list if call.args and call.args[0] == "^v"]
        self.assertEqual(pasted, [])

    def test_two_consecutive_sends_reuse_the_orchestrator_safely(self):
        target = Mock()
        target.hwnd = 123
        box1, box2 = object(), object()
        target.compose_box.side_effect = [box1, box2]
        injector = HardenedTelegramInjector(target)
        injector._land_text = Mock(return_value="A2")
        injector._audit_and_retarget = Mock(
            side_effect=[("compose", box1), ("compose", box2)]
        )
        injector._submit_invisible = Mock(
            side_effect=["posted-click (VERIFIED)", "posted-click (VERIFIED)"]
        )

        with patch("floatingbar.injector.winapi.is_minimized", return_value=False), \
             patch("floatingbar.injector.winapi.get_foreground_window", return_value=999), \
             patch.object(injector, "_restore_foreground"):
            first = injector.send("first")
            second = injector.send("second")

        self.assertEqual(first, "posted-click (VERIFIED)")
        self.assertEqual(second, "posted-click (VERIFIED)")
        self.assertEqual(target.compose_box.call_count, 2)
        self.assertEqual(injector._submit_invisible.call_count, 2)
        self.assertEqual(
            injector._land_text.call_args_list,
            [unittest.mock.call(box1, 123, "first"),
             unittest.mock.call(box2, 123, "second")],
        )


if __name__ == "__main__":
    unittest.main()
