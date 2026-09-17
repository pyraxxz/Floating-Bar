"""Session-only recent background targets.

The history is deliberately in-memory only. It stores structural identity
needed to re-bind a target (HWND/PID, adapter/process identity, and optional
UIA row identity), never message bodies, previews, window titles, or files.
Stale entries are revalidated before they are exposed again.
"""

from dataclasses import dataclass
from typing import Optional, Sequence

from .app_adapters import actionable_adapter_for_process
from .background_windows import BackgroundWindow
from .transaction import TargetScope
from . import winapi


@dataclass(frozen=True)
class RecentTarget:
    """Immutable, session-only description of one background target."""

    kind: str
    adapter_key: str
    process_name: str
    label: str
    scope: TargetScope
    runtime_id: tuple[int, ...] | None = None
    control_identity: tuple[str, ...] | None = None
    left: int = 0
    top: int = 0
    right: int = 0
    bottom: int = 0

    @property
    def valid(self) -> bool:
        return self.scope.valid and bool(self.adapter_key and self.process_name)


class RecentTargetHistory:
    """Bounded LRU-like history that exists only for the current process."""

    DEFAULT_LIMIT = 6

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self.limit = max(1, int(limit))
        self._items: list[RecentTarget] = []

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def items(self, *, kind: Optional[str] = None) -> tuple[RecentTarget, ...]:
        if kind is None:
            return tuple(self._items)
        return tuple(item for item in self._items if item.kind == kind)

    def _remember(self, target: RecentTarget) -> RecentTarget:
        self._items = [
            item
            for item in self._items
            if self._dedupe_key(item) != self._dedupe_key(target)
        ]
        self._items.insert(0, target)
        del self._items[self.limit :]
        return target

    @staticmethod
    def _dedupe_key(target: RecentTarget) -> tuple[object, ...]:
        return (
            target.kind,
            target.adapter_key,
            target.scope.hwnd,
            target.scope.pid,
            target.runtime_id,
            target.control_identity,
            target.label if target.kind != "application" else "",
        )

    def record_application(
        self,
        *,
        hwnd: int,
        pid: int,
        process_name: str,
        label: str,
        adapter_key: str,
    ) -> RecentTarget:
        """Remember a successfully bound application target."""
        target = RecentTarget(
            kind="application",
            adapter_key=str(adapter_key),
            process_name=str(process_name).casefold(),
            label=str(label or process_name or "Application"),
            scope=TargetScope(int(hwnd), int(pid)),
        )
        return self._remember(target)

    def record_conversation(self, conversation, *, adapter_key: str) -> RecentTarget:
        """Remember a successfully guarded generic conversation target."""
        target = RecentTarget(
            kind="conversation",
            adapter_key=str(adapter_key),
            process_name=self._process_name_for_pid(conversation.pid),
            label=str(getattr(conversation, "name", "Conversation") or "Conversation"),
            scope=TargetScope(int(conversation.hwnd), int(conversation.pid)),
            runtime_id=getattr(conversation, "runtime_id", None),
            control_identity=getattr(conversation, "control_identity", None),
            left=int(getattr(conversation, "left", 0)),
            top=int(getattr(conversation, "top", 0)),
            right=int(getattr(conversation, "right", 0)),
            bottom=int(getattr(conversation, "bottom", 0)),
        )
        return self._remember(target)

    @staticmethod
    def _process_name_for_pid(pid: int) -> str:
        try:
            image = winapi.get_process_image_name(int(pid))
        except Exception:
            image = ""
        return image.rsplit("\\", 1)[-1].casefold() if image else ""

    @staticmethod
    def application_is_live(target: RecentTarget) -> bool:
        """Revalidate exact HWND/PID plus current adapter/process identity."""
        if target.kind != "application" or not target.valid:
            return False
        try:
            if not winapi.user32.IsWindow(target.scope.hwnd):
                return False
            current_pid = winapi.get_window_pid(target.scope.hwnd)
            if current_pid != target.scope.pid:
                return False
            image = winapi.get_process_image_name(current_pid)
            process_name = image.rsplit("\\", 1)[-1].casefold() if image else ""
            if process_name != target.process_name:
                return False
            spec = actionable_adapter_for_process(process_name)
            return bool(spec and spec.implemented and spec.key == target.adapter_key)
        except Exception:
            return False

    def live_applications(self) -> tuple[RecentTarget, ...]:
        """Return live app entries and silently discard stale process scopes."""
        live: list[RecentTarget] = []
        for item in self._items:
            if item.kind != "application":
                continue
            if self.application_is_live(item):
                live.append(item)
        self._items = [
            item
            for item in self._items
            if item.kind != "application" or item in live
        ]
        return tuple(live)

    def match_conversation(self, target: RecentTarget):
        """Re-enumerate a stored conversation and return a fresh row if safe."""
        if target.kind != "conversation" or not target.valid:
            return None
        try:
            if not winapi.user32.IsWindow(target.scope.hwnd):
                return None
            if winapi.get_window_pid(target.scope.hwnd) != target.scope.pid:
                return None
            process = self._process_name_for_pid(target.scope.pid)
            if process != target.process_name:
                return None
            spec = actionable_adapter_for_process(process)
            if spec is None or not spec.implemented or spec.key != target.adapter_key:
                return None
            from .conversation_rows import enumerate_conversations

            rows = enumerate_conversations(target.scope.hwnd, limit=32)
            if target.runtime_id is not None:
                matches = [row for row in rows if row.runtime_id == target.runtime_id]
                if len(matches) == 1 and matches[0].name == target.label:
                    return matches[0]
                if matches:
                    return None
            if target.control_identity is not None:
                matches = [
                    row
                    for row in rows
                    if row.control_identity == target.control_identity and row.name == target.label
                ]
                if len(matches) == 1:
                    return matches[0]
                if len(matches) > 1:
                    return None
            candidates = [row for row in rows if row.name == target.label]
            if len(candidates) != 1:
                return None
            row = candidates[0]
            distance = abs(row.left - target.left) + abs(row.top - target.top)
            return row if distance <= 24 else None
        except Exception:
            return None

    def live_conversations(self) -> tuple[tuple[RecentTarget, object], ...]:
        """Return recent conversations paired with freshly validated rows."""
        pairs = []
        stale = set()
        for item in self._items:
            if item.kind != "conversation":
                continue
            fresh = self.match_conversation(item)
            if fresh is None:
                stale.add(self._dedupe_key(item))
            else:
                pairs.append((item, fresh))
        if stale:
            self._items = [
                item for item in self._items
                if self._dedupe_key(item) not in stale
            ]
        return tuple(pairs)


__all__ = ["RecentTarget", "RecentTargetHistory"]
