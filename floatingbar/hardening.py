"""Safety hardening layered on top of the established Telegram injector.

The hardened path keeps the proven injector implementation intact while
making the target/focus decisions more deterministic and keeping unsafe
submission guesses out of the default path.
"""

import time

import config
from . import trace
from . import winapi
from .injector import InjectionFailed, TelegramInjector


_VOICE_TERMS = ("voice", "record", "mic", "audio")


def _is_voice_name(name: str) -> bool:
    normalized = (name or "").strip().lower()
    return any(term in normalized for term in _VOICE_TERMS)


def _is_explicit_send_name(name: str) -> bool:
    normalized = (name or "").strip().lower()
    return bool(normalized) and "send" in normalized and not _is_voice_name(normalized)


class HardenedTelegramInjector(TelegramInjector):
    """v0.1.9 reliability layer over the established cascade."""

    @staticmethod
    def _pick_compose_text_edit(box, fallback, entries):
        """Prefer a positive-value Edit that overlaps the chosen compose.

        Telegram may already have non-empty text in another Edit, such as the
        search field. The base audit returns the first positive-value Edit;
        that is not necessarily the field we just targeted. Among overlapping
        candidates, prefer the smallest control: Telegram's real inner Edit is
        slightly smaller than its wrapper on observed builds.
        """
        overlapping = []
        for edit, _line in entries:
            try:
                if not self._same_field(edit, box) and edit is not box:
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
        """Target the compose first, then post characters to its focused child.

        The posted click never moves the real mouse or intentionally raises
        Telegram. After the click, GetGUIThreadInfo often exposes the actual
        native child HWND receiving keyboard messages; using it is more direct
        than posting WM_CHAR only to the top-level Qt window.
        """
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
                        f"phase 0 focused hwnd={focused} belongs to a "
                        "different process; using Telegram top-level"
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
                "audit: overriding first text Edit with overlapping "
                "compose candidate"
            )
        return "found", preferred

    def _audit_and_retarget(self, box, hwnd: int, text: str):
        """Audit and re-target while using the focused native child on retry."""
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
            "landing in a different field — retrying compose click + "
            "focused-child text post"
        )
        point = self.target.compose_click_point(box)
        if point:
            try:
                winapi.post_click(hwnd, point[0], point[1])
                time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
            except Exception as exc:
                trace.trace(f"compose retry click failed: {exc}")
        focused = winapi.get_focused_hwnd(hwnd)
        target_hwnd = hwnd
        try:
            if focused and winapi.get_window_pid(focused) == winapi.get_window_pid(hwnd):
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

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool,
                          landing: str):
        """Keep verified behavior; harden the unverified button path."""
        if landing == "compose":
            return super()._submit_invisible(box, hwnd, primary_ctrl, landing)

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
                trace.trace(
                    f"unverified submit: explicit Send button at "
                    f"({cx},{cy}) name={name!r}"
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
                "unverified submit: no button candidate; "
                "falling back to posted Enter combos"
            )
        winapi.post_enter(hwnd, ctrl=primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        winapi.post_enter(hwnd, ctrl=not primary_ctrl)
        time.sleep(config.POSTED_ENTER_WAIT_MS / 1000.0)
        return "posted-enter (unverified)"
