"""Safety hardening layered on top of the established Telegram injector.

Keeps the existing injector implementation intact while fixing two failure
modes found during review of v0.1.7:

1. Deterministically target the selected compose field before posting text.
2. Never click an ambiguous/unnamed button when the post-landing audit cannot
   prove that the text is in the compose. Explicitly named Send buttons remain
   safe in the unverified path; verified compose landings retain the stronger
   rightmost-button heuristic from the existing implementation.
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
    """v0.1.8 hardening without replacing the established cascade."""

    def _land_text(self, box, hwnd: int, text: str):
        """Click the chosen compose field first, then use the v0.1.7 WM_CHAR path.

        The click is posted to Telegram's existing window and does not move the
        real mouse cursor or intentionally raise the window. If geometry is
        unavailable, fall back to the parent implementation so its audit/retry
        logic still gets a chance to recover.
        """
        try:
            point = self.target.compose_click_point(box)
            if point is not None:
                trace.trace(
                    f"phase 0 compose click: ({point[0]},{point[1]})"
                )
                winapi.post_click(hwnd, point[0], point[1])
                time.sleep(config.COMPOSE_CLICK_SETTLE_MS / 1000.0)
            else:
                trace.trace(
                    "phase 0 compose click: geometry unavailable; "
                    "falling back to existing focus"
                )
        except Exception as exc:
            trace.trace(f"phase 0 compose click failed: {exc}")

        return super()._land_text(box, hwnd, text)

    def _submit_invisible(self, box, hwnd: int, primary_ctrl: bool,
                          landing: str):
        """Keep verified behavior; harden the unverified button path."""
        if landing == "compose":
            return super()._submit_invisible(
                box, hwnd, primary_ctrl, landing
            )

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
