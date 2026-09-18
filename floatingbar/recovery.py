"""Scope-aware variants of the opt-in recovery strategies.

The normal invisible path already lives in :mod:`floatingbar.hardening`.
This module extends that class only for the optional focus-steal and
clipboard-recovery strategies, adding target-scope checks before each
critical interaction with the Telegram window.
"""

import time

import config
from . import clipboard_guard
from . import trace
from . import winapi
from .hardening import HardenedTelegramInjector, _is_voice_name
from .injector import InjectionFailed, _combo


class ScopeGuardedRecoveryInjector(HardenedTelegramInjector):
    """Hardened injector with per-action guards in opt-in recovery."""

    def send(self, text: str, restore_hwnd: int = 0) -> str:
        """Capture one immutable Telegram scope for the whole send transaction."""
        hwnd = self.target.hwnd or 0
        pid = winapi.get_window_pid(hwnd) if hwnd else 0
        self._recovery_scope = (hwnd, pid)
        try:
            return super().send(text, restore_hwnd=restore_hwnd)
        finally:
            self._recovery_scope = None

    @staticmethod
    def _previous_foreground_scope(hwnd: int) -> tuple[int, int]:
        """Capture the previous foreground HWND/PID before recovery changes focus."""
        if not hwnd:
            return 0, 0
        try:
            return hwnd, winapi.get_window_pid(hwnd)
        except Exception:
            return hwnd, 0

    @staticmethod
    def _restore_previous_foreground(
        prev_hwnd: int,
        prev_pid: int,
        target_hwnd: int,
        target_pid: int,
    ) -> None:
        """Restore focus only when the saved HWND still belongs to the saved PID.

        A recycled HWND must never become an accidental foreground target after
        Telegram is restarted or another process takes the old handle.
        """
        if not prev_hwnd or not prev_pid:
            return
        try:
            if not winapi.user32.IsWindow(prev_hwnd):
                return
            current_pid = winapi.get_window_pid(prev_hwnd)
            if current_pid != prev_pid:
                trace.trace(
                    f"recovery: skipped foreground restore for recycled hwnd={prev_hwnd}"
                )
                return
            if prev_hwnd == target_hwnd and (
                not target_pid or current_pid != target_pid
            ):
                trace.trace(
                    f"recovery: skipped foreground restore after target replacement "
                    f"hwnd={prev_hwnd}"
                )
                return
            winapi.set_foreground_window(prev_hwnd)
        except Exception as exc:
            trace.trace_exception("recovery: foreground restore skipped safely", exc)

    def _submit_focus_steal(self, box, hwnd: int, primary_ctrl: bool,
                            restore_hwnd: int) -> bool:
        """Opt-in foreground recovery with a guard before every target action."""
        prev = restore_hwnd or winapi.get_foreground_window()
        prev_hwnd, prev_pid = self._previous_foreground_scope(prev)
        target_pid = 0
        try:
            target_pid = winapi.get_window_pid(hwnd) if hwnd else 0
        except Exception:
            target_pid = 0
        try:
            self._assert_target_scope(hwnd, "before focus-steal restore")
            winapi.ensure_restored(hwnd)

            self._assert_target_scope(hwnd, "before focus-steal foreground")
            if not winapi.set_foreground_window(hwnd):
                return False
            time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)

            self._assert_target_scope(hwnd, "before focus-steal focus")
            box.set_focus()

            self._assert_target_scope(hwnd, "before focus-steal primary Enter")
            box.type_keys(_combo(primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._value_length(box) == 0:
                return True

            self._assert_target_scope(hwnd, "before focus-steal alternate Enter")
            box.type_keys(_combo(not primary_ctrl), pause=0.02)
            time.sleep(config.PASTE_SETTLE_MS / 1000.0)
            if self._value_length(box) == 0:
                return True

            self._assert_target_scope(hwnd, "before focus-steal Send discovery")
            info = self.target.send_button_click(near_box=box)
            if info and not _is_voice_name(info[0]):
                self._assert_target_scope(hwnd, "before focus-steal Send click")
                self._post_target_click(hwnd, info[1], info[2], "before recovery Send click")
                verified = self._poll_compose_clear(
                    lambda: self._value_length(box)
                )
                return verified is True
            return False
        except InjectionFailed:
            raise
        except Exception as exc:
            trace.trace_exception("scope-guarded focus-steal submit failed", exc)
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                self._restore_previous_foreground(
                    prev_hwnd,
                    prev_pid,
                    hwnd,
                    target_pid,
                )

    def _strategy_b(self, box, text: str, primary_ctrl: bool,
                    restore_hwnd: int) -> bool:
        """Opt-in clipboard recovery with a fixed send-transaction scope."""
        prev = restore_hwnd or winapi.get_foreground_window()
        prev_hwnd, prev_pid = self._previous_foreground_scope(prev)
        target_pid = 0
        try:
            with clipboard_guard.preserved_clipboard(
                retries=config.CLIPBOARD_RETRIES,
                delay=config.CLIPBOARD_RETRY_DELAY_S,
            ):
                fixed_scope = getattr(self, "_recovery_scope", None)
                if fixed_scope and fixed_scope[0] and fixed_scope[1]:
                    hwnd = fixed_scope[0]
                    target_pid = fixed_scope[1]
                else:
                    hwnd = self.target.hwnd or 0
                    try:
                        target_pid = winapi.get_window_pid(hwnd) if hwnd else 0
                    except Exception:
                        target_pid = 0

                self._assert_target_scope(hwnd, "before clipboard recovery")
                winapi.ensure_restored(hwnd)

                self._assert_target_scope(hwnd, "before clipboard recovery foreground")
                if not winapi.set_foreground_window(hwnd):
                    return False
                time.sleep(config.FOREGROUND_SETTLE_MS / 1000.0)

                self._assert_target_scope(hwnd, "before clipboard recovery focus")
                box.set_focus()

                self._assert_target_scope(hwnd, "before clipboard recovery clear")
                box.type_keys("^a", pause=0.01)
                box.type_keys("{DEL}", pause=0.01)

                self._assert_target_scope(hwnd, "before clipboard recovery clipboard write")
                if not clipboard_guard.set_text(
                    text,
                    retries=config.CLIPBOARD_RETRIES,
                    delay=config.CLIPBOARD_RETRY_DELAY_S,
                ):
                    raise InjectionFailed(
                        "The clipboard could not be prepared safely; paste recovery was refused."
                    )

                self._assert_target_scope(hwnd, "before clipboard recovery paste")
                box.type_keys("^v", pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)

                self._assert_target_scope(hwnd, "before clipboard recovery primary Enter")
                box.type_keys(_combo(primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True

                self._assert_target_scope(hwnd, "before clipboard recovery alternate Enter")
                box.type_keys(_combo(not primary_ctrl), pause=0.02)
                time.sleep(config.PASTE_SETTLE_MS / 1000.0)
                if self._value_length(box) == 0:
                    return True

                self._assert_target_scope(hwnd, "before clipboard recovery Send discovery")
                info = self.target.send_button_click(near_box=box)
                if info and not _is_voice_name(info[0]):
                    self._assert_target_scope(hwnd, "before clipboard recovery Send click")
                    self._post_target_click(hwnd, info[1], info[2], "before recovery Send click")
                    verified = self._poll_compose_clear(
                        lambda: self._value_length(box)
                    )
                    return verified is True
                return False
        except InjectionFailed:
            raise
        except Exception as exc:
            trace.trace_exception("scope-guarded clipboard recovery failed", exc)
            return False
        finally:
            if prev:
                time.sleep(config.FOREGROUND_RESTORE_MS / 1000.0)
                self._restore_previous_foreground(
                    prev_hwnd,
                    prev_pid,
                    hwnd if 'hwnd' in locals() else 0,
                    target_pid,
                )
