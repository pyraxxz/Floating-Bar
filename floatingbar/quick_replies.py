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
from typing import Callable, Optional
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
    """Small CRUD editor for locally saved quick replies."""

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
        self.configure(bg="#18181b")
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        frame = tk.Frame(self, bg="#18181b", padx=12, pady=12)
        frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(
            frame,
            width=28,
            height=9,
            exportselection=False,
            bg="#27272a",
            fg="#f4f4f5",
            selectbackground="#3f3f46",
            selectforeground="#ffffff",
            relief="flat",
            bd=0,
        )
        self.listbox.grid(row=0, column=0, rowspan=5, sticky="nsew", padx=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self._selected)

        tk.Label(
            frame, text="Label", bg="#18181b", fg="#a1a1aa", anchor="w",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=0, column=1, sticky="ew")
        self.label_entry = tk.Entry(
            frame, bg="#27272a", fg="#f4f4f5", insertbackground="#ffffff",
            relief="flat", bd=0,
        )
        self.label_entry.grid(row=1, column=1, sticky="ew", pady=(2, 8))

        tk.Label(
            frame, text="Reply", bg="#18181b", fg="#a1a1aa", anchor="w",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=2, column=1, sticky="ew")
        self.text = tk.Text(
            frame, width=36, height=7, wrap="word",
            bg="#27272a", fg="#f4f4f5", insertbackground="#ffffff",
            relief="flat", bd=0,
        )
        self.text.grid(row=3, column=1, sticky="nsew", pady=(2, 8))

        buttons = tk.Frame(frame, bg="#18181b")
        buttons.grid(row=4, column=1, sticky="ew")
        for index in range(4):
            buttons.columnconfigure(index, weight=1)
        tk.Button(
            buttons, text="New", command=self._new,
            relief="flat", bd=0, bg="#27272a", fg="#d4d4d8",
        ).grid(row=0, column=0, sticky="ew", padx=2)
        tk.Button(
            buttons, text="Save", command=self._save,
            relief="flat", bd=0, bg="#27272a", fg="#d4d4d8",
        ).grid(row=0, column=1, sticky="ew", padx=2)
        tk.Button(
            buttons, text="Use", command=self._use,
            relief="flat", bd=0, bg="#27272a", fg="#d4d4d8",
        ).grid(row=0, column=2, sticky="ew", padx=2)
        tk.Button(
            buttons, text="Delete", command=self._delete,
            relief="flat", bd=0, bg="#27272a", fg="#d4d4d8",
        ).grid(row=0, column=3, sticky="ew", padx=2)

        self._refresh_list()
        self.geometry("640x285")

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

    def _new(self) -> None:
        self._active_id = None
        self.label_entry.delete(0, "end")
        self.text.delete("1.0", "end")
        self.label_entry.focus_set()

    def _save(self) -> None:
        try:
            reply = self.store.upsert(
                self.label_entry.get(),
                self.text.get("1.0", "end-1c"),
                self._active_id,
            )
        except ValueError:
            return
        self._active_id = reply.id
        self.on_change()
        self._refresh_list(select_id=reply.id)

    def _delete(self) -> None:
        if not self._active_id:
            return
        if not self.store.delete(self._active_id):
            return
        self._active_id = None
        self.on_change()
        self._new()
        self._refresh_list()

    def _use(self) -> None:
        selection = self.store.get(self._active_id) if self._active_id else None
        if selection is None:
            selected = self.listbox.curselection()
            if selected:
                selection = self.store.items()[selected[0]]
        if selection is not None:
            self.on_use(selection)
            self.destroy()


__all__ = ["QuickReply", "QuickReplyManager", "QuickReplyStore"]
