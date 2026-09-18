import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from floatingbar.hardening import (
    HardenedTelegramInjector,
    _is_explicit_send_name,
    _is_voice_name,
)
from floatingbar.injector import InjectionFailed, TelegramInjector, _nested


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

    def test_expected_target_pid_uses_pid_validated_by_scope_guard(self):
        target = Mock()
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        with patch(
            "floatingbar.hardening.winapi.get_window_pid",
            side_effect=[10, 999],
        ):
            self.assertEqual(injector._expected_target_pid(123, "test"), 10)

    def test_land_clicks_compose_before_posting_text_and_uses_focused_child(self):
        events = []
        target = Mock()
        target.compose_click_point.return_value = (77, 88)
        target.scope_matches.return_value = True

        def click(*args, **kwargs):
            events.append("click")

        def text(*args):
            events.append(("text", args[0]))

        injector = HardenedTelegramInjector(target)
        with patch("floatingbar.hardening.winapi.post_click", side_effect=click), \
             patch("floatingbar.hardening.winapi.get_focused_hwnd", return_value=456), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=10), \
             patch("floatingbar.hardening.winapi.post_text", side_effect=text), \
             patch("floatingbar.hardening.time.sleep"):
            result = injector._land_text(SimpleNamespace(), 123, "ignored")

        self.assertEqual(result, "A2-child")
        self.assertEqual(events, ["click", ("text", 456)])

    def test_land_refuses_to_post_text_when_compose_click_fails(self):
        target = Mock()
        target.compose_click_point.return_value = (77, 88)
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)

        with patch(
            "floatingbar.hardening.winapi.post_click",
            side_effect=RuntimeError("click failed"),
        ) as click, patch("floatingbar.hardening.winapi.post_text") as post_text, patch(
            "floatingbar.hardening.trace.trace"
        ), patch("floatingbar.hardening.winapi.get_window_pid", return_value=10):
            with self.assertRaises(InjectionFailed) as raised:
                injector._land_text(SimpleNamespace(), 123, "danger")

        click.assert_called_once_with(123, 77, 88, expected_pid=10)
        post_text.assert_not_called()
        self.assertIn("focused safely", str(raised.exception))

    def test_land_refuses_to_post_text_when_compose_geometry_lookup_fails(self):
        target = Mock()
        target.compose_click_point.side_effect = RuntimeError("UIA failed")
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)

        with patch("floatingbar.hardening.winapi.post_text") as post_text, \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=10):
            with self.assertRaises(InjectionFailed) as raised:
                injector._land_text(SimpleNamespace(), 123, "danger")

        post_text.assert_not_called()
        self.assertIn("located safely", str(raised.exception))

    def test_audit_retry_refuses_when_compose_click_fails(self):
        box = Mock()
        other = Mock()
        target = Mock()
        target.scope_matches.return_value = True
        target.edit_audit.side_effect = [
            (other, [(other, "other")]),
        ]
        target.compose_click_point.side_effect = RuntimeError("retry click failed")
        injector = HardenedTelegramInjector(target)
        injector._audit = Mock(return_value=("found", other))

        with patch("floatingbar.hardening.winapi.post_text") as post_text:
            with self.assertRaises(InjectionFailed):
                injector._audit_and_retarget(box, 123, "danger")

        post_text.assert_not_called()

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
        posted.assert_called_once_with(123, 20, 30, expected_pid=1)

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
        posted.assert_called_once_with(123, 20, 30, expected_pid=1)
        self.assertGreaterEqual(sleeping.call_count, 1)

    def test_poll_compose_clear_returns_none_when_readback_is_unavailable(self):
        with patch("floatingbar.hardening.time.sleep"):
            result = HardenedTelegramInjector._poll_compose_clear(lambda: -1)
        self.assertIsNone(result)

    def test_strategy_b_direct_recovery_path_can_submit(self):
        target = Mock()
        target.hwnd = 123
        target.scope_matches.return_value = True
        injector = HardenedTelegramInjector(target)
        injector._value_length = Mock(return_value=0)
        box = Mock()
        guard = Mock()
        guard.__enter__ = Mock(return_value=guard)
        guard.__exit__ = Mock(return_value=False)

        with patch(
            "floatingbar.hardening.clipboard_guard.preserved_clipboard",
            return_value=guard,
        ), patch(
            "floatingbar.hardening.clipboard_guard.set_text",
            return_value=True,
        ), patch("floatingbar.hardening.winapi.get_foreground_window", return_value=999), \
             patch("floatingbar.hardening.winapi.get_window_pid", return_value=1), \
             patch("floatingbar.hardening.winapi.set_foreground_window", return_value=True), \
             patch("floatingbar.hardening.winapi.ensure_restored"), \
             patch("floatingbar.hardening.time.sleep"):
            self.assertTrue(injector._strategy_b(box, "hello", False, 999))

        box.type_keys.assert_any_call("^a", pause=0.01)
        box.type_keys.assert_any_call("{DEL}", pause=0.01)
        box.type_keys.assert_any_call("^v", pause=0.02)

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

    def test_send_preserves_intentional_leading_and_trailing_whitespace(self):
        class SpyInjector(TelegramInjector):
            def __init__(self, target):
                super().__init__(target)
                self.seen_text = None

            def _land_text(self, box, hwnd, text):
                self.seen_text = text
                return "A2"

            def _audit_and_retarget(self, box, hwnd, text):
                return "compose", box

            def _submit_invisible(self, box, hwnd, primary_ctrl, landing):
                return "posted-click (VERIFIED)"

            @staticmethod
            def _restore_foreground(_telegram_hwnd, _prev_fg):
                pass

        target = Mock()
        target.hwnd = 123
        target.compose_box.return_value = object()
        injector = SpyInjector(target)

        with patch("floatingbar.injector.winapi.is_minimized", return_value=False), \
             patch("floatingbar.injector.winapi.get_foreground_window", return_value=99):
            result = injector.send("  hello world  ")

        self.assertEqual(result, "posted-click (VERIFIED)")
        self.assertEqual(injector.seen_text, "  hello world  ")

    def test_send_skips_whitespace_only_input(self):
        target = Mock()
        injector = TelegramInjector(target)
        self.assertEqual(injector.send(" \t  "), "skipped-empty")
        target.compose_box.assert_not_called()


if __name__ == "__main__":
    unittest.main()