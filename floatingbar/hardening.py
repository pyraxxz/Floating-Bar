"""Safety hardening layered on top of the established Telegram injector.

This module keeps the proven injector implementation intact while making
focus targeting, target-scope validation, audit selection, and submission
verification safer.
"""

import time
from typing import Optional

import config
from . import clipboard_guard
from . import trace
from . import winapi
from .injector import InjectionFailed, TelegramInjector


_VOICE_TERMS = ("voice", "record", "mic", "audio")
VERIFY_ATTEMPTS = 10
VERIFY_INTERVAL_MS = 100


def _is_voice_name(name: str) -> bool:
    normalized = (name or "").strip().lower()
    return any(term in normalized for term in _VOICE_TERMS)


def _is_explicit_send_name(name: str) -> bool:
    normalized = (name or "").strip().lower()
    return bool(normalized) and "send" in normalized and not _is_voice_name(normalized)


class HardenedTelegramInjector(TelegramInjector):
    """Production reliability layer over the established cascade."""

    def _assert_target_scope(self, hwnd: int, stage: str) -> None:
        """Refuse to continue if Telegram's top-level target changed mid-send."""
        try:
            pid = winapi.get_window_pid(hwnd)
        except Exception:
            pid = 0
        try:
            stable = self.target.scope_matches(hwnd, pid)
        except Exception as exc:
            trace.trace(f"scope check failed at {stage}: {exc}")
            stable = False
        if not stable:
            trace.trace(
                f"scope changed at {stage}; refusing to continue with stale target"
            )
            raise InjectionFailed(
                "Telegram changed or restarted while the message was being sent. "
                "The send was stopped safely; try again."
            )

    def _pick_compose_text_edit(self, box, fallback, entries):
        """Prefer a positive-value Edit that overlaps the chosen compose."""
        overlapping = []
        for edit, _line in entries:
            try:
                if edit is not box and not self._same_field(edit, box):
                    continue
                length = self._value_length(edit)
                if length <= 0:
                    continue
                try:
                    r = edit.rectangle()
                    area = max(1, (r.right - r.left) * (r.bottom - r.top))
                except Exception:
                    area = 2**63 - 1
                overlapping.append((area, edit))
            except Exception:
                continue
        if overlapping:
            overlapping.sort(key=lambda item: item[0])
            return overlapping[0][1]
        return fallback

    def _land_text(self, box, hwnd: int, text: str):
        """Target the compose first, then post characters to its focused child."""
        self._assert_target_scope(hwnd, "before compose click")
        try:
            point = self.target.compose_click_point(box)
            if point is not None:
                trace.trace(f"phase 0 compose click: ({point[0]},{point[1]})")
                winapi.post_click(hwnd, point[0], point[1])
                time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
            else:
                trace.trace(
                    "phase 0 compose click: geometry unavailable; "
                    "falling back to existing focus"
                )
        except Exception as exc:
            trace.trace(f"phase 0 compose click failed: {exc}")

        self._assert_target_scope(hwnd, "after compose click")
        focused = winapi.get_focused_hwnd(hwnd)
        target_hwnd = hwnd
        try:
            if focused and focused != hwnd:
                focused_pid = winapi.get_window_pid(focused)
                target_pid = winapi.get_window_pid(hwnd)
                if focused_pid and focused_pid == target_pid:
                    target_hwnd = focused
                    trace.trace(f"phase 0 focused child hwnd={focused}")
                else:
                    trace.trace(
                        f"phase 0 focused hwnd={focused} belongs to a different process; "
                        "using Telegram top-level"
                    )
        except Exception as exc:
            trace.trace(f"phase 0 focused-child lookup failed: {exc}")

        try:
            winapi.post_text(target_hwnd, text)
            return "A2-child" if target_hwnd != hwnd else "A2"
        except Exception as exc:
            trace.trace(f"focused-child WM_CHAR post failed: {exc}")
            if target_hwnd != hwnd:
                try:
                    winapi.post_text(hwnd, text)
                    return "A2-top-level-retry"
                except Exception as retry_exc:
                    trace.trace(f"top-level WM_CHAR retry failed: {retry_exc}")
            return None

    def _audit(self, box):
        """Audit all Edits, preferring the text-holding compose control."""
        try:
            text_edit, entries = self.target.edit_audit()
        except Exception as exc:
            trace.trace(f"audit failed: {exc}")
            return "none", None
        for _, line in entries:
            trace.trace(f"audit: {line}")

        preferred = self._pick_compose_text_edit(box, text_edit, entries)
        if preferred is None:
            trace.trace(
                "audit: no Edit reports text — reads stale or unreadable, "
                "proceeding empirically"
            )
            return "none", None
        if preferred is not text_edit:
            trace.trace(
                "audit: overriding first text Edit with overlapping compose candidate"
            )
        return "found", preferred

    def _audit_and_retarget(self, box, hwnd: int, text: str):
        """Audit and re-target while using the focused native child on retry."""
        self._assert_target_scope(hwnd, "before audit")
        time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
        _landing, real = self._audit(box)
        if real is None:
            return "unknown", box

        if self._same_field(real, box):
            trace.trace(
                "audit: text is in the NESTED inner field — "
                "re-targeting compose (reads now verifiable)"
            )
            self.target.remember_compose(real)
            return "compose", real

        trace.trace(
            "landing in a different field — retrying compose click + focused-child text post"
        )
        self._assert_target_scope(hwnd, "before compose retry")
        point = self.target.compose_click_point(box)
        if point:
            try:
                winapi.post_click(hwnd, point[0], point[1])
                time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
            except Exception as exc:
                trace.trace(f"compose retry click failed: {exc}")

        self._assert_target_scope(hwnd, "after compose retry click")
        focused = winapi.get_focused_hwnd(hwnd)
        target_hwnd = hwnd
        try:
            telegram_pid = winapi.get_window_pid(hwnd)
            if focused and winapi.get_window_pid(focused) == telegram_pid:
                target_hwnd = focused
        except Exception:
            pass
        try:
            winapi.post_text(target_hwnd, text)
        except Exception as exc:
            trace.trace(f"compose retry text post failed: {exc}")
        time.sleep(config.AUDIT_SETTLE_MS / 1000.0)
        _landing, real = self._audit(box)
        if real is not None and self._same_field(real, box):
            self.target.remember_compose(real)
            return "compose", real
        return "elsewhere", box

    @staticmethod
    def _poll_compose_clear(value_reader) -> Optional[bool]:
        """Return True when clear is observed, False on timeout, None unreadable."""
        for attempt in range(VERIFY_ATTEMPTS):
            length = value_reader()
            if length == 0:
                return True
            if length < 0:
                return None
            if attempt < VERIFY_ATTEMPTS - 1:
                time.sleep(VERIFY_INTERVAL_MS / 1000.0)
        return False

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool,
                          landing: str):
        """Submit invisibly with bounded asynchronous-clear verification."""
        self._assert_target_scope(hwnd, "before submission")

        if landing != "compose":
            info = self.target.send_button_click(near_box=box)
            if info is not None:
                name, cx, cy = info
                if _is_voice_name(name):
                    trace.trace(
                        f"unverified submit: refusing voice/mic button {name!r}"
                    )
                    raise InjectionFailed(
                        "Telegram exposed a voice/record control instead of a "
                        "safe Send button; message submission was refused."
                    )
                if _is_explicit_send_name(name):
                    self._assert_target_scope(hwnd, "before unverified Send click")
                    trace.trace(
                        f"unverified submit: explicit Send button at ({cx},{cy}) name={name!r}"
                    )
                    winapi.post_click(hwnd, cx, cy)
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return "posted-click (unverified-explicit-send)"
                trace.trace(
                    f"unverified submit: refusing ambiguous button {name!r}; "
                    "falling back to posted Enter combos"
                )
            else:
                trace.trace(
                    "unverified submit: no button candidate; falling back to posted Enter combos"
                )
            self._assert_target_scope(hwnd, "before unverified Enter")
            winapi.post_enter(hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            self._assert_target_scope(hwnd, "before alternate unverified Enter")
            winapi.post_enter(hwnd, ctrl=not primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            return "posted-enter (unverified)"

        before = self._value_length(box)
        trace.trace(f"submit: verified channel, compose value_len={before}")
        if before == 0:
            raise InjectionFailed("The message text is not in Telegram's compose box.")
        if before < 0:
            raise InjectionFailed(
                "Telegram's compose value could not be verified before submission."
            )

        info = self.target.send_button_click(near_box=box)
        if info is None:
            trace.trace("send button: no candidate — posting enter combos")
            self._assert_target_scope(hwnd, "before primary Enter")
            winapi.post_enter(hwnd, ctrl=primary_ctrl)
            time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
            verified = self._poll_compose_clear(lambda: self._value_length(box))
            if verified is True:
                return "posted-enter (VERIFIED)"
            if verified is False:
                self._assert_target_scope(hwnd, "before alternate Enter")
                winapi.post_enter(hwnd, ctrl=not primary_ctrl)
                verified = self._poll_compose_clear(lambda: self._value_length(box))
                if verified is True:
                    return "posted-enter (VERIFIED)"
            if verified is None:
                trace.trace(
                    "enter submission succeeded empirically but read-back became unavailable"
                )
                return "posted-enter (verification-unavailable)"
            raise InjectionFailed(
                "Message sits in Telegram's compose box but could not be submitted."
            )

        name, cx, cy = info
        if _is_voice_name(name):
            trace.trace(f"button scan returned the mic ({name!r}) — refusing to click")
            raise InjectionFailed(
                "Telegram's voice button is showing — the compose is empty, "
                "so the text did not land."
            )

        self._assert_target_scope(hwnd, "before Send click")
        trace.trace(f"posted click on send button at ({cx},{cy}) name={name!r}")
        winapi.post_click(hwnd, cx, cy)
        verified = self._poll_compose_clear(lambda: self._value_length(box))
        trace.trace(f"submit verification result={verified!r}")
        if verified is True:
            return "posted-click (VERIFIED)"
        if verified is None:
            trace.trace("submit clear could not be read after successful click")
            return "posted-click (verification-unavailable)"
        raise InjectionFailed(
            "The Send button was clicked but the message is still in the compose box."
        )

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """Opt-in recovery: never paste unless the clipboard write succeeded."""
        prev = restore_hwnd or winapi.get_foreground_window()
        try:
            with clipboard_guard.preserved_clipboard(
                retries=config.CLIPBOARD_RETRIES,
                delay=config.CLIPBOARD_RETRY_DELAY_S,
            ):
                hwnd = self.target.hwnd or 0
                self._assert_target_scope(hwnd, "before clipboard recovery")
                winapi.ensure_restored(hwnd)
                if not winapi.set_foreground_window(hwnd):
                    return False
                time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)
                box.set_focus()
                box.type_keys("^a", pause=0.01)
                box.type_keys("{DEL}", pause=0.01)
                if not clipboard_guard.set_text(
                    text,
                    retries=config.CLIPBOARD_RETRIES,
                    delay=config.CLIPBOARD_RETRY_DELAY_S,
                ):
                    raise InjectionFailed(
                        "The clipboard could not be prepared safely; paste recovery was refused."
                    )
                box.type_keys("^v", pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True
                self._assert_target_scope(hwnd, "before recovery Send click")
                info = self.target.send_button_click(near_box=box)
                if info and not _is_voice_name(info[0]):
                    winapi.post_click(hwnd, info[1], info[2])
                    time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                    return self._value_length(box) == 0
                return False
        except Exception as exc:
            trace.trace(f"B failed: {exc}")
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                winapi.set_foreground_window(prev)
