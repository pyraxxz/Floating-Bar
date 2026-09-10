"""The only UI: an orb (idle) that expands into a transparent input bar
(active). Two states, nothing else — no history, no settings window.

Improvements over the spec's reference UI:

* Click vs drag disambiguation: the spec bound <Button-1> (expand) and
  <ButtonPress-1> (drag start) — the SAME Tk event — so every click also
  armed a drag. Here a press only drags after crossing a pixel threshold,
  and expansion happens on release-without-drag.
* The bar is draggable only by its grip bands (the padding around the
  entry). Dragging via the entry itself would fight text selection.
* Sends run on a worker thread (pywinauto + comtypes CoInitialize), so
  the Tk event loop and the idle timer never freeze during injection —
  results come back through a queue polled on the UI thread (after() is
  not thread-safe).
* No blocking MessageBox popups from a topmost transparent app: errors
  surface as a red dot flash + a small label inside the bar.
* The orb's color is a status channel: blue = ready, gray = Telegram not
  found, amber pulse = sending, green/red flash = sent / failed.
"""

import queue
import threading
import tkinter as tk

import config
from . import winapi
from .injector import TelegramInjector, InjectionFailed
from .target import TelegramTarget, TelegramNotFound


class OrbRelayWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Floating Bar")

        self.target = TelegramTarget()
        self.injector = TelegramInjector(self.target)
        self._result_q = queue.Queue()

        self._state = "orb"
        self._sending = False
        self._last_error = None
        self._work_hwnd = 0
        self._pos = (config.DEFAULT_X, config.DEFAULT_Y)
        self._idle_job = None
        self._collapse_job = None
        self._flash_job = None
        self._blink_job = None
        self._dragging = False
        self._press_xy = (0, 0)
        self._win_off = (0, 0)

        # --- window chrome --------------------------------------------------
        self.overrideredirect(True)            # borderless
        self.attributes("-topmost", True)      # always on top
        self.configure(bg=config.TRANSPARENT_KEY_COLOR)
        self.wm_attributes("-transparentcolor", config.TRANSPARENT_KEY_COLOR)

        # --- orb --------------------------------------------------------------
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

        # --- bar --------------------------------------------------------------
        # The frame's padding doubles as the drag grip; the entry itself
        # is NOT drag-bound so click-to-position and selection work.
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
        self.error_label = tk.Label(
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

        # --- state --------------------------------------------------------------
        self._show_orb()
        self._poll_results()

        # Excluded from Alt-Tab (overrideredirect already kills the taskbar
        # entry); needs a real HWND, so after the first layout pass.
        self.update_idletasks()
        try:
            winapi.hide_from_alt_tab(self.winfo_id())
        except Exception:
            pass

    # ================================================================ geometry

    def _apply_alpha(self, alpha: float) -> None:
        if config.USE_WINDOW_ALPHA:
            self.attributes("-alpha", alpha)
        # Defensive: some Tk builds re-issue SetLayeredWindowAttributes
        # with LWA_ALPHA only when -alpha changes, which can drop the color
        # key and show a solid box. Re-asserting keeps both active.
        self.wm_attributes("-transparentcolor", config.TRANSPARENT_KEY_COLOR)

    def _set_geometry(self) -> None:
        if self._state == "orb":
            d = config.ORB_DIAMETER
            self.geometry(f"{d}x{d}+{self._pos[0]}+{self._pos[1]}")
        else:
            extra = 16 if self.error_label.winfo_ismapped() else 0
            h = config.BAR_HEIGHT + extra
            self.geometry(
                f"{config.BAR_WIDTH}x{h}+{self._pos[0]}+{self._pos[1]}"
            )

    # ================================================================ states

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
        if self._last_error:
            self._show_error(self._last_error)
        self._reset_idle()

    def _expand(self) -> None:
        """Orb click -> bar. Captures the user's current foreground window
        FIRST, so the focus-stealing fallback can hand control back to it
        after sending (R8)."""
        if self._sending:
            return
        if self._state != "bar":
            self._work_hwnd = winapi.get_foreground_window()
            self._update_status()
            self._show_bar()

    def _collapse(self) -> None:
        if self._state == "orb":
            return
        self._hide_error()
        self._show_orb()

    # ================================================================ status

    def _set_dot_color(self, color: str) -> None:
        self.orb.itemconfig(self.orb_dot, fill=color)

    def _update_status(self) -> None:
        """Cheap availability check (no UIA) — recolors the dot."""
        try:
            available = self.target.is_available()
        except Exception:
            available = False
        self._set_dot_color(
            config.ORB_COLOR_READY if available else config.ORB_COLOR_NOT_FOUND
        )

    def _flash_orb(self, color: str) -> None:
        """Flash a result color on the dot, then revert to the status color."""
        self._set_dot_color(color)
        if self._flash_job:
            try:
                self.after_cancel(self._flash_job)
            except Exception:
                pass
        self._flash_job = self.after(1400, self._update_status)

    def _blink_sending(self, on: bool = True) -> None:
        """Amber pulse while an injection is in flight."""
        if not self._sending:
            self._update_status()
            return
        self._set_dot_color(
            config.ORB_COLOR_SENDING if on else config.ORB_COLOR_READY
        )
        self._blink_job = self.after(280, lambda: self._blink_sending(not on))

    # ================================================================ errors

    def _show_error(self, message: str) -> None:
        self._last_error = message
        if self._state != "bar":
            return
        self.error_label.config(text=message)
        self.error_label.place(
            x=8, y=config.BAR_HEIGHT - 4, width=config.BAR_WIDTH - 16, height=14
        )
        self._set_geometry()
        self.after(4000, self._hide_error)

    def _hide_error(self) -> None:
        self.error_label.place_forget()
        self._last_error = None
        if self._state == "bar":
            self._set_geometry()

    # ================================================================ timers

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
            config.FOCUS_LOST_COLLAPSE_MS, self._on_focus_lost
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

    # ================================================================ drag

    def _bind_drag(self, widget, on_click=None) -> None:
        """Press + drag with a pixel threshold; on_click fires on a clean
        release (press+release without crossing the threshold)."""

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
                abs(dx) > config.DRAG_THRESHOLD_PX
                or abs(dy) > config.DRAG_THRESHOLD_PX
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

    # ================================================================ send

    def _on_key_typed(self, _event) -> None:
        self._reset_idle()
        if self._last_error:
            self._hide_error()

    def _on_enter_key(self, _event=None) -> str:
        if self._sending:
            return "break"
        text = self.entry.get()
        self.entry.delete(0, "end")
        if not text.strip():
            return "break"  # empty send is a no-op (spec §6)
        self._sending = True
        work_hwnd = self._work_hwnd
        self._hide_error()
        self._collapse()
        self._blink_sending()
        threading.Thread(
            target=self._send_worker,
            args=(text, work_hwnd),
            daemon=True,
            name="floatingbar-send",
        ).start()
        return "break"

    def _send_worker(self, text: str, work_hwnd: int) -> None:
        """Worker thread: pywinauto drives COM, so CoInitialize here.
        Results are marshalled back through a queue — self.after() is not
        thread-safe to call from off-thread."""
        comtypes = None
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            comtypes = None

        strategy = None
        error = None
        try:
            strategy = self.injector.send(text, restore_hwnd=work_hwnd)
        except (TelegramNotFound, InjectionFailed) as e:
            error = str(e)
        except Exception as e:  # never crash the worker silently
            error = f"Unexpected error: {e}"
        finally:
            if comtypes:
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass
        self._result_q.put((strategy, error))

    def _poll_results(self) -> None:
        try:
            while True:
                strategy, error = self._result_q.get_nowait()
                self._send_finished(strategy, error)
        except queue.Empty:
            pass
        self.after(80, self._poll_results)

    def _send_finished(self, strategy: str, error) -> None:
        self._sending = False
        if self._blink_job:
            try:
                self.after_cancel(self._blink_job)
            except Exception:
                pass
            self._blink_job = None
        if error:
            self._flash_orb(config.ORB_COLOR_ERROR)
            self._last_error = error
        else:
            self._flash_orb(config.ORB_COLOR_OK)
            self._last_error = None

    # ================================================================ run

    def run(self) -> None:
        self.update_idletasks()
        self.mainloop()
