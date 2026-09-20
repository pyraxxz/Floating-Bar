"""Persistent saved quick replies and their small manager dialog.

Quick replies are explicitly user-authored local data. This module never
captures or stores text from background applications; only text the user
chooses to save is written to the quick-reply file.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from . import ui_theme
from uuid import uuid4


_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
_DEFAULT_PATH = os.path.join(_APPDATA, "FloatingBar", "quick-replies.json")
_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class QuickReply:
    id: str
    label: str
    text: str

    @property
    def valid(self) -> bool:
        return bool(self.id and self.label.strip() and self.text)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label, "text": self.text}


class QuickReplyStore:
    """Bounded local store for user-authored quick replies."""

    DEFAULT_LIMIT = 12
    MAX_LABEL_LENGTH = 48
    MAX_TEXT_LENGTH = 4000

    def __init__(self, path: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> None:
        self.path = str(path or _DEFAULT_PATH)
        self.limit = max(1, int(limit))
        self._items: list[QuickReply] = []
        self._load()

    def items(self) -> tuple[QuickReply, ...]:
        return tuple(self._items)

    def get(self, reply_id: str) -> Optional[QuickReply]:
        wanted = str(reply_id)
        return next((item for item in self._items if item.id == wanted), None)

    def upsert(self, label: str, text: str, reply_id: Optional[str] = None) -> QuickReply:
        clean_label = str(label).strip()[: self.MAX_LABEL_LENGTH]
        clean_text = str(text)
        if not clean_label or not clean_text:
            raise ValueError("quick reply label and text are required")
        if len(clean_text) > self.MAX_TEXT_LENGTH:
            raise ValueError("quick reply text is too long")
        target_id = str(reply_id or uuid4().hex)
        reply = QuickReply(target_id, clean_label, clean_text)
        if not reply.valid:
            raise ValueError("invalid quick reply")

        for index, item in enumerate(self._items):
            if item.id == target_id:
                self._items[index] = reply
                self._save()
                return reply
        self._items.insert(0, reply)
        del self._items[self.limit :]
        self._save()
        return reply

    def delete(self, reply_id: str) -> bool:
        wanted = str(reply_id)
        before = len(self._items)
        self._items = [item for item in self._items if item.id != wanted]
        if len(self._items) == before:
            return False
        self._save()
        return True

    def clear(self) -> None:
        self._items.clear()
        self._save()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            self._items = []
            return
        if not isinstance(payload, dict) or payload.get("version") != _SCHEMA_VERSION:
            self._items = []
            return
        raw_items = payload.get("replies")
        if not isinstance(raw_items, list):
            self._items = []
            return
        parsed: list[QuickReply] = []
        seen = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            reply = QuickReply(
                id=str(raw.get("id", "")),
                label=str(raw.get("label", "")).strip()[: self.MAX_LABEL_LENGTH],
                text=str(raw.get("text", "")),
            )
            if (
                not reply.valid
                or len(reply.text) > self.MAX_TEXT_LENGTH
                or reply.id in seen
            ):
                continue
            seen.add(reply.id)
            parsed.append(reply)
            if len(parsed) >= self.limit:
                break
        self._items = parsed

    def _save(self) -> None:
        payload = {
            "version": _SCHEMA_VERSION,
            "replies": [item.to_dict() for item in self._items[: self.limit]],
        }
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=".quick-replies-",
                suffix=".tmp",
                dir=directory,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self.path)
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
        except OSError:
            pass


class QuickReplyManager(tk.Toplevel):
    """CRUD editor for locally saved quick replies with keyboard-friendly UX."""

    def __init__(
        self,
        parent: tk.Misc,
        store: QuickReplyStore,
        on_use: Callable[[QuickReply], None],
        on_change: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_use = on_use
        self.on_change = on_change or (lambda: None)
        self._active_id: Optional[str] = None
        self.title("Quick replies")
        self.resizable(False, False)
        self.transient(parent)
        self.attributes("-topmost", True)
        ui_theme.style_popup(self)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = ui_theme.frame(self, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=2)
        frame.rowconfigure(2, weight=1)

        ui_theme.label(
            frame,
            text="Quick replies",
            fg=ui_theme.TEXT_STRONG,
            font=ui_theme.FONT_TITLE,
        ).grid(row=0, column=0, columnspan=2, sticky="ew")
        ui_theme.label(
            frame,
            text="Save phrases you use often. Only replies you explicitly save are stored locally.",
            muted=True,
            wraplength=620,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 12))

        list_frame = ui_theme.frame(
            frame,
            bg=ui_theme.SURFACE_ELEVATED,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            padx=6,
            pady=6,
        )
        list_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 12))
        list_frame.rowconfigure(1, weight=1)
        list_frame.columnconfigure(0, weight=1)

        ui_theme.label(
            list_frame,
            text="Saved",
            muted=True,
            bold=True,
            small=True,
        ).grid(row=0, column=0, sticky="ew", padx=3, pady=(0, 4))

        self.listbox = tk.Listbox(
            list_frame,
            width=28,
            height=11,
            exportselection=False,
            activestyle="none",
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            selectbackground=ui_theme.ACCENT_DIM,
            selectforeground=ui_theme.TEXT_STRONG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=ui_theme.FONT_BODY,
        )
        self.listbox.grid(row=1, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.listbox.yview,
            bg=ui_theme.SURFACE_ELEVATED,
            troughcolor=ui_theme.SURFACE,
            activebackground=ui_theme.SURFACE_HOVER,
            bd=0,
            highlightthickness=0,
            width=10,
        )
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(4, 0))
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.bind("<<ListboxSelect>>", self._selected)
        self.listbox.bind("<Return>", lambda _event: (self._use(), "break")[1], add="+")
        self.listbox.bind("<Delete>", lambda _event: (self._delete(), "break")[1], add="+")

        detail_frame = ui_theme.frame(frame)
        detail_frame.grid(row=2, column=1, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(4, weight=1)

        ui_theme.label(
            detail_frame,
            text="Edit reply",
            muted=True,
            bold=True,
            small=True,
        ).grid(row=0, column=0, sticky="ew")

        ui_theme.label(
            detail_frame,
            text="Label",
            fg=ui_theme.TEXT,
            bold=True,
            small=True,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 1))
        self.label_entry = tk.Entry(
            detail_frame,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            insertbackground=ui_theme.TEXT_STRONG,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.ACCENT,
            font=ui_theme.FONT_BODY,
        )
        self.label_entry.grid(row=2, column=0, sticky="ew", pady=(2, 8))

        ui_theme.label(
            detail_frame,
            text="Reply",
            fg=ui_theme.TEXT,
            bold=True,
            small=True,
        ).grid(row=3, column=0, sticky="ew")
        self.text = tk.Text(
            detail_frame,
            width=40,
            height=8,
            wrap="word",
            undo=True,
            bg=ui_theme.SURFACE_ELEVATED,
            fg=ui_theme.TEXT,
            insertbackground=ui_theme.TEXT_STRONG,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=ui_theme.BORDER,
            highlightcolor=ui_theme.ACCENT,
            font=ui_theme.FONT_BODY,
        )
        self.text.grid(row=4, column=0, sticky="nsew", pady=(2, 8))

        self._status = ui_theme.label(
            detail_frame,
            text="",
            muted=True,
            small=True,
            wraplength=420,
        )
        self._status.grid(row=5, column=0, sticky="ew", pady=(0, 8))

        buttons = ui_theme.frame(detail_frame)
        buttons.grid(row=6, column=0, sticky="ew")
        for index in range(4):
            buttons.columnconfigure(index, weight=1)

        ui_theme.button(
            buttons,
            text="New",
            command=self._new,
            subtle=True,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ui_theme.button(
            buttons,
            text="Save",
            command=self._save,
            primary=True,
        ).grid(row=0, column=1, sticky="ew", padx=3)
        ui_theme.button(
            buttons,
            text="Use",
            command=self._use,
            subtle=True,
        ).grid(row=0, column=2, sticky="ew", padx=3)
        ui_theme.button(
            buttons,
            text="Delete",
            command=self._delete,
            subtle=True,
        ).grid(row=0, column=3, sticky="ew", padx=(3, 0))

        ui_theme.label(
            detail_frame,
            text="Ctrl+N new  ·  Ctrl+S save  ·  Ctrl+Enter use  ·  Esc close",
            dim=True,
            small=True,
        ).grid(row=7, column=0, sticky="ew", pady=(8, 0))

        self.bind("<Control-n>", lambda _event: (self._new(), "break")[1], add="+")
        self.bind("<Control-s>", lambda _event: (self._save(), "break")[1], add="+")
        self.bind("<Control-Return>", lambda _event: (self._use(), "break")[1], add="+")
        self.bind("<Escape>", lambda _event: self.destroy(), add="+")

        self._refresh_list()
        self.geometry("760x405")
        self.update_idletasks()
        self._center_on_parent(parent)

    def _center_on_parent(self, parent: tk.Misc) -> None:
        try:
            x = parent.winfo_rootx() + max(
                8,
                (parent.winfo_width() - self.winfo_width()) // 2,
            )
            y = parent.winfo_rooty() + max(
                8,
                (parent.winfo_height() - self.winfo_height()) // 2,
            )
            self.geometry(f"+{x}+{y}")
        except (tk.TclError, AttributeError):
            pass

    def _set_status(self, message: str) -> None:
        self._status.config(text=message)

    def _refresh_count(self) -> None:
        count = len(self.store.items())
        self._set_status(
            f"{count} saved · {self.store.limit} maximum"
            if count
            else "No saved replies yet. Choose New to create one."
        )

    def _refresh_list(self, select_id: Optional[str] = None) -> None:
        self.listbox.delete(0, "end")
        items = self.store.items()
        selected_index = None
        for index, reply in enumerate(items):
            self.listbox.insert("end", reply.label)
            if reply.id == select_id:
                selected_index = index

        if selected_index is not None:
            self.listbox.selection_set(selected_index)
            self.listbox.see(selected_index)
            self._load_reply(items[selected_index])
        elif items and self._active_id is None:
            self.listbox.selection_set(0)
            self._load_reply(items[0])
        self._refresh_count()

        if items:
            self.listbox.focus_set()
        else:
            self.label_entry.focus_set()

    def _load_reply(self, reply: QuickReply) -> None:
        self._active_id = reply.id
        self.label_entry.delete(0, "end")
        self.label_entry.insert(0, reply.label)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", reply.text)

    def _selected(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        reply = self.store.items()[selection[0]]
        self._load_reply(reply)
        self._set_status("Selected. Edit the fields or press Enter to use it.")

    def _new(self) -> None:
        self._active_id = None
        self.listbox.selection_clear(0, "end")
        self.label_entry.delete(0, "end")
        self.text.delete("1.0", "end")
        self.label_entry.focus_set()
        self._set_status("New reply. Add a short label and the text you want to reuse.")

    def _save(self) -> None:
        try:
            reply = self.store.upsert(
                self.label_entry.get(),
                self.text.get("1.0", "end-1c"),
                self._active_id,
            )
        except ValueError as exc:
            reason = str(exc)
            if "required" in reason:
                self._set_status("Add both a label and reply text before saving.")
            elif "too long" in reason:
                self._set_status("The reply is too long. Keep it under 4,000 characters.")
            else:
                self._set_status("That quick reply could not be saved.")
            return
        self._active_id = reply.id
        self.on_change()
        self._refresh_list(select_id=reply.id)
        self._set_status("Saved locally.")
        
    def _delete(self) -> None:
        if not self._active_id:
            self._set_status("Select a saved reply before deleting.")
            return
        if not messagebox.askyesno(
            "Delete quick reply",
            "Delete the selected quick reply?",
            parent=self,
        ):
            return
        if not self.store.delete(self._active_id):
            self._set_status("The selected reply is no longer available.")
            return
        self._active_id = None
        self.on_change()
        self._new()
        self._refresh_list()
        self._set_status("Deleted.")

    def _use(self) -> None:
        selection = self.store.get(self._active_id) if self._active_id else None
        if selection is None:
            selected = self.listbox.curselection()
            if selected:
                selection = self.store.items()[selected[0]]
        if selection is None:
            self._set_status("Select a reply before using it.")
            return
        self.on_use(selection)
        self.destroy()


__all__ = ["QuickReply", "QuickReplyManager", "QuickReplyStore"]
