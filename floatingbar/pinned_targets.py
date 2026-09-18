"""Persistent, content-free pinned background targets.

Pins store stable app/adapter identity and, for conversation pins, the
visible conversation name plus optional structural UI identity. They never
persist HWND/PID/runtime IDs, window titles, message text, or UIA values.
Live HWND/PID and row identity are resolved and validated afresh before a
pin is offered for use.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import tempfile
from typing import Optional, Sequence


_APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
_DEFAULT_PATH = os.path.join(_APPDATA, "FloatingBar", "pinned-targets.json")
_SCHEMA_VERSION = 4
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1, 2, 3, 4})


@dataclass(frozen=True)
class PinnedTarget:
    kind: str
    adapter_key: str
    process_name: str
    label: str
    control_identity: tuple[str, ...] | None = None
    window_class: str | None = None
    container_identity: tuple[str, ...] | None = None

    @property
    def valid(self) -> bool:
        if self.kind not in {"application", "conversation"}:
            return False
        if not self.adapter_key or not self.process_name or not self.label:
            return False
        if self.kind == "application" and not str(self.window_class or "").strip():
            return False
        return True

    @property
    def key(self) -> tuple[object, ...]:
        base = (
            self.kind,
            self.adapter_key,
            self.process_name.casefold(),
        )
        if self.kind == "conversation" and (
            self.control_identity is not None or self.container_identity is not None
        ):
            return base + (
                "structural",
                self.control_identity,
                self.container_identity,
            )
        return base + (
            self.label.casefold(),
            self.control_identity,
            self.window_class,
            self.container_identity,
        )

    def matches_conversation(self, item) -> bool:
        """Return whether a live row matches this pin's strongest safe identity."""
        if self.kind != "conversation":
            return False
        control = getattr(item, "control_identity", None)
        container = getattr(item, "container_identity", None)
        if self.control_identity is not None or self.container_identity is not None:
            if self.control_identity is not None and control != self.control_identity:
                return False
            if self.container_identity is not None and container != self.container_identity:
                return False
            return True
        return str(getattr(item, "name", "")) == self.label

    def to_dict(self) -> dict:
        payload = {
            "kind": self.kind,
            "adapter_key": self.adapter_key,
            "process_name": self.process_name,
            "label": self.label,
        }
        if self.control_identity:
            payload["control_identity"] = list(self.control_identity)
        if self.window_class:
            payload["window_class"] = self.window_class
        if self.container_identity:
            payload["container_identity"] = list(self.container_identity)
        return payload


class PinnedTargetStore:
    """Small bounded JSON store containing only stable pin identity."""

    DEFAULT_LIMIT = 6

    def __init__(self, path: Optional[str] = None, limit: int = DEFAULT_LIMIT) -> None:
        self.path = str(path or _DEFAULT_PATH)
        self.limit = max(1, int(limit))
        self._items: list[PinnedTarget] = []
        self._load()

    def items(self, *, kind: Optional[str] = None) -> tuple[PinnedTarget, ...]:
        if kind is None:
            return tuple(self._items)
        return tuple(item for item in self._items if item.kind == kind)

    def __len__(self) -> int:
        return len(self._items)

    def contains(self, target: PinnedTarget) -> bool:
        return target.key in {item.key for item in self._items}

    def clear(self) -> None:
        self._items.clear()
        self._save()

    def toggle_application(
        self,
        *,
        adapter_key: str,
        process_name: str,
        label: str,
        window_class: Optional[str] = None,
    ) -> bool:
        return self._toggle(
            PinnedTarget(
                kind="application",
                adapter_key=str(adapter_key),
                process_name=str(process_name).casefold(),
                label=str(label).strip(),
                window_class=str(window_class or "").strip() or None,
            )
        )

    def toggle_conversation(
        self,
        *,
        adapter_key: str,
        process_name: str,
        label: str,
        control_identity: Optional[Sequence[str]] = None,
        container_identity: Optional[Sequence[str]] = None,
    ) -> bool:
        identity = tuple(
            str(part).strip() for part in (control_identity or ()) if str(part).strip()
        ) or None
        container = tuple(
            str(part).strip() for part in (container_identity or ()) if str(part).strip()
        ) or None
        return self._toggle(
            PinnedTarget(
                kind="conversation",
                adapter_key=str(adapter_key),
                process_name=str(process_name).casefold(),
                label=str(label).strip(),
                control_identity=identity,
                container_identity=container,
            )
        )

    def _toggle(self, target: PinnedTarget) -> bool:
        if not target.valid:
            return False
        for index, item in enumerate(self._items):
            if item.key == target.key:
                del self._items[index]
                self._save()
                return False
        self._items.insert(0, target)
        del self._items[self.limit :]
        self._save()
        return True

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            self._items = []
            return
        if not isinstance(payload, dict) or payload.get("version") not in _SUPPORTED_SCHEMA_VERSIONS:
            self._items = []
            return
        raw_items = payload.get("pins")
        if not isinstance(raw_items, list):
            self._items = []
            return
        parsed: list[PinnedTarget] = []
        seen = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                target = PinnedTarget(
                    kind=str(raw.get("kind", "")),
                    adapter_key=str(raw.get("adapter_key", "")),
                    process_name=str(raw.get("process_name", "")).casefold(),
                    label=str(raw.get("label", "")).strip(),
                    control_identity=(
                        tuple(
                            str(part).strip()
                            for part in raw.get("control_identity", ())
                            if str(part).strip()
                        ) or None
                        if isinstance(raw.get("control_identity", ()), (list, tuple))
                        else None
                    ),
                    window_class=str(raw.get("window_class", "")).strip() or None,
                    container_identity=(
                        tuple(
                            str(part).strip()
                            for part in raw.get("container_identity", ())
                            if str(part).strip()
                        ) or None
                        if isinstance(raw.get("container_identity", ()), (list, tuple))
                        else None
                    ),
                )
            except (TypeError, ValueError):
                continue
            if not target.valid or target.key in seen:
                continue
            seen.add(target.key)
            parsed.append(target)
            if len(parsed) >= self.limit:
                break
        self._items = parsed

    def _save(self) -> None:
        payload = {
            "version": _SCHEMA_VERSION,
            "pins": [item.to_dict() for item in self._items[: self.limit]],
        }
        directory = os.path.dirname(self.path)
        if not directory:
            directory = "."
        try:
            os.makedirs(directory, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(
                prefix=".pinned-targets-",
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


__all__ = ["PinnedTarget", "PinnedTargetStore"]
