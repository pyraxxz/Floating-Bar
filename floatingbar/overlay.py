"""The core UI: an orb (idle) that expands into a transparent input bar
(active), with a small settings dialog and explicit retry/recovery UX.

The orb also provides recovery UX: failed sends keep the unsent text as a
session-only retry draft, while a successful-but-unverified send is shown as
an amber warning instead of being presented as confirmed.
"""

import os
import queue
import threading
import tkinter as tk
import webbrowser

import config
from . import trace
from . import winapi
from .settings import SettingsDialog, SettingsStore
from .update_checker import fetch_latest_release, is_newer_version, ReleaseInfo
from . import __version__
from .injector import InjectionFailed
from .hardening import HardenedTelegramInjector
from .evidence import EvidenceState, from_result
from .target import TelegramTarget, TelegramNotFound
from .transaction import SendCompletion, SendRequest


def _classify_send_result(strategy, error):
    """Compatibility wrapper returning typed submission evidence."""
    return from_result(strategy, error)


class OrbRelayWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Floating Bar")

        self.target = TelegramTarget()
        self.injector = HardenedTelegramInjector(self.target)
        self._result_q = queue.Queue()

        self._state = "orb"
        self._sending = False
        self._attempt_seq = 0
        self._active_attempt_id = 0
        self._active_request = None
        self._work_hwnd = 0
        self._retry_draft = None
        self._retry_target_hwnd = 0
        self._active_send_text = ""
        self._feedback_message = None
        self._feedback_color = config.ERROR_COLOR
        self._pos = (config.DEFAULT_X, config.DEFAULT_Y)
        self._idle_job = None
        self._collapse_job = None
        self._flash_job = None
        self._blink_job = None
        self._dragging = False
        self._press_xy = (0, 0)
        self._win_off = (0, 0)
        self._retry_menu_label = "Retry failed draft"
        self._settings_store = SettingsStore()
        self._update_queue = queue.Queue()
        self._update_checking = False
        config.IDLE_COLLAPSE_MS = self._settings_store.idle_collapse_ms

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=config.TRANSPARENT_KEY_COLOR)
        self.wm_attributes("-transparentcolor", config.TRANSPARENT_KEY_COLOR)

        self.orb = tk.Canvas(
            self,
            width=config.ORB_DIAMETER,
            height=config.ORB_DIAMETER,
            bg=config.TRANSPARENT_KEY_COLOR,
            highlightthickness=0,
            bd=0,
        )
        pad = 2
        self.orb_dot = self.orb.create_oval(
            pad, pad, config.ORB_DIAMETER - pad, config.ORB_DIAMETER - pad,
            fill=config.ORB_COLOR_READY,
            outline="",
        )
        self._bind_drag(self.orb, on_click=self._expand)

        self.bar = tk.Frame(self, bg=config.TRANSPARENT_KEY_COLOR, bd=0)
        self.entry = tk.Entry(
            self.bar,
            font=("Segoe UI", 12),
            bd=0,
            highlightthickness=0,
            bg=config.TRANSPARENT_KEY_COLOR,
            fg=config.TEXT_COLOR,
            insertbackground=config.CURSOR_COLOR,
            disabledbackground=config.TRANSPARENT_KEY_COLOR,
            relief="flat",
        )
        self.feedback_label = tk.Label(
            self.bar,
            bg=config.TRANSPARENT_KEY_COLOR,
            fg=config.ERROR_COLOR,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self._bind_drag(self.bar, on_click=None)

        self.entry.bind("<Return>", self._on_enter_key)
        self.entry.bind("<Escape>", lambda e: self._collapse())
        self.entry.bind("<Key>", self._on_key_typed, add="+")
        self.entry.bind("<FocusIn>", lambda e: self._cancel_scheduled_collapse())
        self.entry.bind("<FocusOut>", lambda e: self._schedule_collapse())

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label=f"Floating Bar v{__version__}", state="disabled")
        self.menu.add_command(label="Open trace folder", command=self._open_trace_folder)
        self.menu.add_command(
            label=self._retry_menu_label,
            command=self._retry_failed_draft,
            state="disabled",
        )
        self.menu.add_command(label="Settings", command=self._open_settings)
        self.menu.add_command(label="Check for updates", command=self._check_for_updates)
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.destroy)
        self.orb.bind("<Button-3>", self._show_menu)
        self.bar.bind("<Button-3>", self._show_menu)

        trace.reset_session(__version__)
        self._show_orb()
        self._poll_results()
        self._poll_updates()

        self.update_idletasks()
        try:
            winapi.hide_from_alt_tab(self.winfo_id())
        except Exception:
            pass

    def _check_for_updates(self) -> None:
        """Check public release metadata without blocking the Tk event loop."""
        if self._update_checking:
            return
        self._update_checking = True
        try:
            self.menu.entryconfig("Check for updates", state="disabled")
        except Exception:
            pass
        self._show_feedback("Checking for updates...", "#a1a1aa")

        def worker():
            try:
                info = fetch_latest_release()
                self._update_queue.put(("release", info))
            except Exception as exc:
                trace.trace_exception("release update check failed safely", exc)
                self._update_queue.put(("error", type(exc).__name__))

        threading.Thread(target=worker, name="FloatingBarUpdateCheck", daemon=True).start()

    def _poll_updates(self) -> None:
        try:
            while True:
                kind, value = self._update_queue.get_nowait()
                self._update_checking = False
                try:
                    self.menu.entryconfig("Check for updates", state="normal")
                except Exception:
                    pass
                if kind == "release" and isinstance(value, ReleaseInfo):
                    try:
                        newer = is_newer_version(__version__, value.version)
                    except Exception:
                        newer = False
                    if newer:
                        self._show_update_dialog(value)
                    else:
                        self._show_feedback("Floating Bar is up to date.", config.ORB_COLOR_OK)
                else:
                    self._show_feedback("Update check could not be completed.", config.ORB_COLOR_UNVERIFIED)
        except queue.Empty:
            pass
        self.after(120, self._poll_updates)

    def _show_update_dialog(self, release: ReleaseInfo) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Floating Bar update")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.attributes("-topmost", True)
        dialog.configure(bg="#18181b")
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

        frame = tk.Frame(dialog, bg="#18181b", padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text=f"New version available: v{release.version}",
            bg="#18181b",
            fg="#f4f4f5",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            frame,
            text=f"Current version: v{__version__}",
            bg="#18181b",
            fg="#a1a1a1",
            anchor="w",
        ).pack(fill="x", pady=(4, 12))

        buttons = tk.Frame(frame, bg="#18181b")
        buttons.pack(fill="x")
        tk.Button(
            buttons,
            text="Open release",
            command=lambda: self._open_release_page(release.url, dialog),
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#f4f4f5",
        ).pack(side="right", padx=(6, 0))
        tk.Button(
            buttons,
            text="Close",
            command=dialog.destroy,
            relief="flat",
            bd=0,
            bg="#27272a",
            fg="#d4d4d8",
        ).pack(side="right")
        dialog.geometry("320x120")

    @staticmethod
    def _open_release_page(url: str, dialog: tk.Toplevel | None = None) -> None:
        try:
            webbrowser.open(url)
        finally:
            if dialog is not None:
                try:
                    dialog.destroy()
                except Exception:
                    pass

    def _open_settings(self) -> None:
        """Open the lightweight application settings dialog."""
        if self._sending:
            return
        SettingsDialog(self, self._settings_store, self._apply_settings)

    def _apply_settings(self, settings) -> None:
        """Apply safe runtime preferences without changing target behavior."""
        config.IDLE_COLLAPSE_MS = int(settings.idle_collapse_ms)
        if self._state == "bar":
            self._reset_idle()

    def _set_retry_menu_enabled(self, enabled: bool) -> None:
        try:
            self.menu.entryconfig(
                self._retry_menu_label,
                state="normal" if enabled else "disabled",
            )
        except Exception:
            pass

    def _apply_alpha(self, alpha: float) -> None:
        if config.USE_WINDOW_ALPHA:
            self.attributes("-alpha", alpha)
        self.wm_attributes("-transparentcolor", config.TRANSPARENT_KEY_COLOR)

    def _set_geometry(self) -> None:
        if self._state == "orb":
            d = config.ORB_DIAMETER
            self.geometry(f"{d}x{d}+{self._pos[0]}+{self._pos[1]}")
        else:
            extra = 16 if self.feedback_label.winfo_ismapped() else 0
            h = config.BAR_HEIGHT + extra
            self.geometry(f"{config.BAR_WIDTH}x{h}+{self._pos[0]}+{self._pos[1]}")

    def _show_orb(self) -> None:
        self._state = "orb"
        self._cancel_idle()
        self._cancel_scheduled_collapse()
        self.bar.place_forget()
        self.orb.place(x=0, y=0)
        self._apply_alpha(config.ORB_ALPHA)
        self._set_geometry()

    def _show_bar(self) -> None:
        self._state = "bar"
        self.orb.place_forget()
        self.bar.place(x=0, y=0, width=config.BAR_WIDTH, height=config.BAR_HEIGHT)
        self.entry.place(x=8, y=10, width=config.BAR_WIDTH - 16, height=20)
        self._apply_alpha(config.BAR_ALPHA)
        self._set_geometry()
        self.lift()
        self.entry.focus_force()

        if self._retry_draft and not self.entry.get():
            self.entry.insert(0, self._retry_draft)
            self.entry.select_range(0, "end")

        if self._feedback_message:
            self._show_feedback(self._feedback_message, self._feedback_color)
        self._reset_idle()

    def _expand(self) -> None:
        if self._sending:
            return
        if self._state != "bar":
            # Capture the window that owns focus BEFORE focus_force() moves
            # focus to our entry. When that window is Telegram, the sender can
            # preserve that exact Telegram window in multi-window setups.
            self._work_hwnd = winapi.get_foreground_window()
            self._update_status()
            self._show_bar()

    def _retry_failed_draft(self) -> None:
        """Restore a failed draft for an explicit, user-confirmed retry.

        Prefer the exact Telegram target captured by the failed send. This is
        safer than sampling the current foreground window because opening the
        orb/right-click menu can itself change foreground focus. The message
        is never sent automatically; Enter is still required.
        """
        if self._sending or not self._retry_draft:
            return
        preferred = self._retry_target_hwnd
        self._work_hwnd = preferred or winapi.get_foreground_window()
        self._hide_feedback()
        self._show_bar()
        self._set_retry_menu_enabled(True)

    def _collapse(self) -> None:
        if self._state == "orb":
            return
        self._hide_feedback()
        self._show_orb()

    def _set_dot_color(self, color: str) -> None:
        self.orb.itemconfig(self.orb_dot, fill=color)

    def _update_status(self) -> None:
        try:
            available = self.target.is_available()
        except Exception:
            available = False
        self._set_dot_color(
            config.ORB_COLOR_READY if available else config.ORB_COLOR_NOT_FOUND
        )

    def _flash_orb(self, color: str) -> None:
        self._set_dot_color(color)
        if self._flash_job:
            try:
                self.after_cancel(self._flash_job)
            except Exception:
                pass
        self._flash_job = self.after(1400, self._update_status)

    def _blink_sending(self, on: bool = True) -> None:
        if not self._sending:
            self._update_status()
            return
        self._set_dot_color(
            config.ORB_COLOR_SENDING if on else config.ORB_COLOR_READY
        )
        self._blink_job = self.after(280, lambda: self._blink_sending(not on))

    def _show_feedback(self, message: str, color: str = None) -> None:
        self._feedback_message = message
        self._feedback_color = color or config.ERROR_COLOR
        if self._state != "bar":
            return
        self.feedback_label.config(
            text=self._feedback_message,
            fg=self._feedback_color,
        )
        self.feedback_label.place(
            x=8,
            y=config.BAR_HEIGHT - 4,
            width=config.BAR_WIDTH - 16,
            height=14,
        )
        self._set_geometry()
        self.after(config.FEEDBACK_TIMEOUT_MS, self._hide_feedback)

    def _hide_feedback(self) -> None:
        try:
            self.feedback_label.place_forget()
        except Exception:
            pass
        self._feedback_message = None
        self._feedback_color = config.ERROR_COLOR
        if self._state == "bar":
            self._set_geometry()

    def _reset_idle(self) -> None:
        self._cancel_idle()
        self._idle_job = self.after(config.IDLE_COLLAPSE_MS, self._on_idle)

    def _cancel_idle(self) -> None:
        if self._idle_job:
            try:
                self.after_cancel(self._idle_job)
            except Exception:
                pass
            self._idle_job = None

    def _on_idle(self) -> None:
        self._idle_job = None
        if not self._sending:
            self._collapse()

    def _schedule_collapse(self) -> None:
        self._cancel_scheduled_collapse()
        self._collapse_job = self.after(
            config.FOCUS_LOST_COLLAPSE_MS,
            self._on_focus_lost,
        )

    def _cancel_scheduled_collapse(self) -> None:
        if self._collapse_job:
            try:
                self.after_cancel(self._collapse_job)
            except Exception:
                pass
            self._collapse_job = None

    def _on_focus_lost(self) -> None:
        self._collapse_job = None
        if not self._sending and self._state == "bar":
            self._collapse()

    def _show_menu(self, event) -> None:
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _open_trace_folder(self) -> None:
        try:
            os.makedirs(trace.dir_path(), exist_ok=True)
            os.startfile(trace.dir_path())
        except Exception:
            pass

    def _bind_drag(self, widget, on_click=None) -> None:
        def press(event):
            self._dragging = False
            self._press_xy = (event.x_root, event.y_root)
            self._win_off = (
                event.x_root - self.winfo_x(),
                event.y_root - self.winfo_y(),
            )

        def motion(event):
            dx = event.x_root - self._press_xy[0]
            dy = event.y_root - self._press_xy[1]
            if not self._dragging and (
                abs(dx) > config.DRAG_THRESHOLD_PX or
                abs(dy) > config.DRAG_THRESHOLD_PX
            ):
                self._dragging = True
            if self._dragging:
                self._pos = (
                    event.x_root - self._win_off[0],
                    event.y_root - self._win_off[1],
                )
                self._set_geometry()

        def release(_event):
            try:
                clicked = not self._dragging
            finally:
                self._dragging = False
            if clicked and on_click and self._state == "orb":
                on_click()

        widget.bind("<ButtonPress-1>", press)
        widget.bind("<B1-Motion>", motion)
        widget.bind("<ButtonRelease-1>", release)

    def _on_key_typed(self, _event) -> None:
        self._reset_idle()
        if self._retry_draft is not None:
            self._retry_draft = None
            self._retry_target_hwnd = 0
            self._set_retry_menu_enabled(False)
        if self._feedback_message:
            self._hide_feedback()

    def _on_enter_key(self, _event=None) -> str:
        if self._sending:
            return "break"
        text = self.entry.get()
        self.entry.delete(0, "end")
        if not text.strip():
            return "break"
        self._sending = True
        self._attempt_seq += 1
        attempt_id = self._attempt_seq
        request = SendRequest(
            attempt_id=attempt_id,
            text=text,
            restore_hwnd=self._work_hwnd,
        )
        if not request.valid:
            self._sending = False
            self._show_feedback(
                "The send request was invalid and was stopped safely.",
                config.ERROR_COLOR,
            )
            return "break"
        self._active_attempt_id = attempt_id
        self._active_request = request
        # Retained temporarily for compatibility with older direct tests and
        # diagnostics. New UI completion logic reads from _active_request.
        self._active_send_text = request.text
        self._retry_draft = None
        self._retry_target_hwnd = 0
        self._set_retry_menu_enabled(False)
        self._work_hwnd = request.restore_hwnd
        self._hide_feedback()
        self._collapse()
        self._blink_sending()
        threading.Thread(
            target=self._send_worker_request,
            args=(request,),
            daemon=True,
            name="floatingbar-send",
        ).start()
        return "break"

    def _send_worker_request(self, request: SendRequest) -> None:
        """Validate the immutable request, then enter the legacy worker adapter."""
        if not isinstance(request, SendRequest) or not request.valid:
            attempt_id = getattr(request, "attempt_id", 0)
            self._result_q.put(
                SendCompletion.from_result(
                    attempt_id=attempt_id,
                    strategy=None,
                    error="The send request was invalid and was stopped safely.",
                )
            )
            return
        self._send_worker(
            request.text,
            request.restore_hwnd,
            request.attempt_id,
        )

    def _send_worker(self, text: str, work_hwnd: int, attempt_id: int) -> None:
        comtypes = None
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            comtypes = None

        strategy = None
        error = None
        try:
            if work_hwnd:
                self.target.select_for_send(preferred_hwnd=work_hwnd)
            strategy = self.injector.send(text, restore_hwnd=work_hwnd)
        except (TelegramNotFound, InjectionFailed) as e:
            error = str(e)
        except Exception as e:
            error = f"Unexpected error: {e}"
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        self._result_q.put(
            SendCompletion.from_result(
                attempt_id=attempt_id,
                strategy=strategy,
                error=error,
            )
        )

    def _coerce_completion(self, value, strategy=None, error=None):
        """Normalize typed and legacy worker results into one immutable object."""
        if isinstance(value, SendCompletion):
            return value
        if strategy is None and error is None:
            try:
                attempt_id, strategy, error = value
            except (TypeError, ValueError):
                return None
        return SendCompletion.from_result(
            attempt_id=value,
            strategy=strategy,
            error=error,
        )

    def _poll_results(self) -> None:
        try:
            while True:
                value = self._result_q.get_nowait()
                completion = self._coerce_completion(value)
                if completion is None:
                    trace.trace("ignoring malformed worker completion")
                    continue
                self._send_finished(completion)
        except queue.Empty:
            pass
        self.after(80, self._poll_results)

    def _send_finished(self, completion_or_attempt_id, strategy=None, error=None) -> None:
        completion = self._coerce_completion(
            completion_or_attempt_id,
            strategy=strategy,
            error=error,
        )
        if completion is None:
            trace.trace("ignoring malformed send completion")
            return

        attempt_id = completion.attempt_id
        strategy = completion.strategy
        error = completion.error
        if attempt_id != self._active_attempt_id:
            trace.trace(
                f"ignoring stale send result attempt={attempt_id}; "
                f"active={self._active_attempt_id}"
            )
            return

        self._sending = False
        if self._blink_job:
            try:
                self.after_cancel(self._blink_job)
            except Exception:
                pass
            self._blink_job = None

        active_request = self._active_request
        active_text = (
            active_request.text
            if isinstance(active_request, SendRequest)
            else self._active_send_text
        )
        self._active_request = None
        self._active_send_text = ""
        evidence = completion.evidence_state
        if evidence is None:
            evidence = _classify_send_result(strategy, error)

        if evidence.state is EvidenceState.FAILED:
            if evidence.retryable and active_text:
                self._retry_draft = active_text
                self._retry_target_hwnd = self._work_hwnd
                self._set_retry_menu_enabled(True)
            else:
                self._retry_target_hwnd = 0
                self._set_retry_menu_enabled(False)
            self._flash_orb(config.ORB_COLOR_ERROR)
            self._show_feedback(
                evidence.detail or "Send failed.",
                config.ERROR_COLOR,
            )
        elif evidence.confirmed:
            self._retry_draft = None
            self._retry_target_hwnd = 0
            self._set_retry_menu_enabled(False)
            self._hide_feedback()
            self._flash_orb(config.ORB_COLOR_OK)
        elif evidence.uncertain:
            # Never offer an uncertain message as an automatic retry: it may
            # already exist in Telegram and retrying could duplicate it.
            self._retry_draft = None
            self._retry_target_hwnd = 0
            self._set_retry_menu_enabled(False)
            self._flash_orb(config.ORB_COLOR_UNVERIFIED)
            self._show_feedback(
                "Telegram did not confirm the send. Verify it before retrying.",
                config.ORB_COLOR_UNVERIFIED,
            )
        else:
            self._retry_draft = None
            self._retry_target_hwnd = 0
            self._set_retry_menu_enabled(False)
            self._flash_orb(config.ORB_COLOR_ERROR)
            self._show_feedback(
                "Send completed without a usable status.",
                config.ERROR_COLOR,
            )

    def run(self) -> None:
        self.update_idletasks()
        self.mainloop()
