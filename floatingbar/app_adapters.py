"""Central registry for supported background application capabilities.

The picker and production routing consume this table rather than each
maintaining executable-name logic. Capability metadata also defines the
contract that per-app target and verification adapters implement.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AppAdapterSpec:
    key: str
    label: str
    processes: tuple[str, ...]
    action: str
    target_mode: str = "focused-child"
    submit_mode: str = "enter"
    verification_mode: str = "unverified"
    implemented: bool = True
    supports_background_type: bool = True
    chat_picker: Optional[str] = None


_ADAPTERS = (
    AppAdapterSpec(
        key="telegram",
        label="Telegram",
        processes=("telegram.exe",),
        action="Chats",
        target_mode="telegram-compose",
        submit_mode="telegram-send",
        verification_mode="typed",
        chat_picker="telegram",
    ),
    AppAdapterSpec(key="whatsapp", label="WhatsApp", processes=("whatsapp.exe",), action="Type"),
    AppAdapterSpec(key="discord", label="Discord", processes=("discord.exe",), action="Type"),
    AppAdapterSpec(key="slack", label="Slack", processes=("slack.exe",), action="Type"),
    AppAdapterSpec(
        key="teams",
        label="Microsoft Teams",
        processes=("msteams.exe", "ms-teams.exe", "teams.exe"),
        action="Type",
    ),
    AppAdapterSpec(
        key="terminal",
        label="Terminal",
        processes=("windowsterminal.exe", "wt.exe"),
        action="Type",
        target_mode="terminal-structured-focus",
        submit_mode="enter",
        verification_mode="unverified",
    ),
    AppAdapterSpec(key="cmd", label="Command Prompt", processes=("cmd.exe",), action="Type"),
    AppAdapterSpec(key="powershell", label="PowerShell", processes=("powershell.exe",), action="Type"),
)

_BY_PROCESS = {
    process: spec
    for spec in _ADAPTERS
    for process in spec.processes
}


def adapter_for_process(process_name: str) -> Optional[AppAdapterSpec]:
    """Return capability metadata for a normalized executable name."""
    return _BY_PROCESS.get((process_name or "").casefold())


def is_actionable_process(process_name: str) -> bool:
    """Return whether the executable has a production action today."""
    spec = adapter_for_process(process_name)
    return bool(spec and spec.implemented and spec.supports_background_type)


__all__ = ["AppAdapterSpec", "adapter_for_process", "is_actionable_process"]
