"""Structured manual smoke-test matrix for real Windows validation.

The matrix is deliberately declarative: it does not drive applications or read
window/message content. A runner can generate a blank result record, then a
human tester records PASS, FAIL, or BLOCKED after exercising the real desktop.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Iterable, Mapping

from .app_adapters import registry_validation_errors


SCHEMA_VERSION = 4

RESULT_PENDING = "PENDING"
RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
RESULT_BLOCKED = "BLOCKED"
RESULTS = frozenset({RESULT_PENDING, RESULT_PASS, RESULT_FAIL, RESULT_BLOCKED})


@dataclass(frozen=True)
class SmokeCase:
    case_id: str
    area: str
    title: str
    apps: tuple[str, ...]
    priority: str = "normal"
    destructive: bool = False


@dataclass(frozen=True)
class SmokeResult:
    case_id: str
    result: str = RESULT_PENDING
    notes: str = ""
    tested_at: str = ""

    def __post_init__(self) -> None:
        if self.result not in RESULTS:
            raise ValueError(f"unsupported smoke result: {self.result}")


def default_cases() -> tuple[SmokeCase, ...]:
    """Return the complete real-Windows manual matrix in execution order."""
    return (
        SmokeCase("env.launch", "environment", "Launch, idle, collapse, and clean shutdown", ("all",), "critical"),
        SmokeCase("env.focus", "environment", "Foreground application remains protected", ("all",), "critical"),
        SmokeCase("env.dpi", "environment", "Mixed-DPI and multi-monitor geometry", ("all",), "critical"),
        SmokeCase("env.minimized", "environment", "Minimized background target is rejected or safely handled", ("all",), "high"),
        SmokeCase("env.restart", "environment", "Target process restart cannot reuse stale HWND/PID", ("all",), "critical"),
        SmokeCase("env.repeated", "environment", "Repeated sends do not leak attempts, leases, or drafts", ("all",), "high"),
        SmokeCase("text.unicode", "fidelity", "Unicode, emoji, and surrogate-pair delivery", ("all chat",), "high"),
        SmokeCase("text.whitespace", "fidelity", "Intentional leading/trailing whitespace is preserved", ("all chat",), "normal"),
        SmokeCase("picker.multiple", "picker", "Multiple windows remain distinguishable without titles", ("all",), "high"),
        SmokeCase("picker.refresh", "picker", "Conversation refresh/pagination preserves safe identity", ("WhatsApp", "Discord", "Slack", "Microsoft Teams"), "high"),
        SmokeCase("generic.discovery", "target", "Generic structural input discovery gates readiness", ("unknown app",), "high"),
        SmokeCase("generic.blocked", "target", "Generic app with no safe input is blocked without injection", ("unknown app",), "high"),
        SmokeCase("telegram.send", "telegram", "Background send through selected Telegram chat", ("Telegram",), "critical"),
        SmokeCase("telegram.multiwindow", "telegram", "Exact Telegram window selection is preserved", ("Telegram",), "critical"),
        SmokeCase("telegram.restart", "telegram", "Telegram restart blocks stale transaction", ("Telegram",), "critical"),
        SmokeCase("telegram.context", "telegram", "Chat-context drift is blocked when a non-content anchor changes", ("Telegram",), "critical"),
        SmokeCase("telegram.unverified", "telegram", "Uncertain submission is surfaced without automatic retry", ("Telegram",), "critical"),
        SmokeCase("telegram.retry", "telegram", "Genuine failure preserves an explicit, non-automatic retry", ("Telegram",), "high"),
        SmokeCase("chat.whatsapp", "chat", "WhatsApp conversation selection, compose, send, and clear verification", ("WhatsApp",), "high"),
        SmokeCase("chat.discord", "chat", "Discord conversation targeting, compose, send, and clear verification", ("Discord",), "high"),
        SmokeCase("chat.slack", "chat", "Slack conversation targeting, compose, send, and clear verification", ("Slack",), "high"),
        SmokeCase("chat.teams", "chat", "Teams conversation targeting, compose, send, and clear verification", ("Microsoft Teams",), "high"),
        SmokeCase("chat.restart", "chat", "Chat-app process replacement invalidates the active target", ("WhatsApp", "Discord", "Slack", "Microsoft Teams"), "high"),
        SmokeCase("terminal.discovery", "terminal", "Terminal structural target discovery when focus is elsewhere", ("Terminal", "Command Prompt", "PowerShell"), "high"),
        SmokeCase("terminal.submit", "terminal", "Terminal Enter submission reaches the pinned control", ("Terminal", "Command Prompt", "PowerShell"), "critical"),
        SmokeCase("terminal.acceptance.wt", "terminal", "Windows Terminal stable input-clear verification proves the pinned control accepted and cleared the line without reading command content", ("Windows Terminal stable",), "critical"),
        SmokeCase("terminal.acceptance.preview", "terminal", "Windows Terminal Preview input-clear verification proves the pinned control accepted and cleared the line without reading command content", ("Windows Terminal Preview",), "critical"),
        SmokeCase("terminal.acceptance.conhost", "terminal", "conhost/CMD input-clear verification proves the pinned control accepted and cleared the line without reading command content", ("conhost/CMD",), "critical"),
        SmokeCase("terminal.acceptance.pwsh", "terminal", "PowerShell Core input-clear verification proves the pinned control accepted and cleared the line without reading command content", ("PowerShell Core",), "critical"),
        SmokeCase("terminal.uncertain", "terminal", "Terminal outcome remains submitted-but-unverified when acceptance is unproven", ("Terminal", "Command Prompt", "PowerShell"), "critical"),
        SmokeCase("terminal.restart", "terminal", "Terminal process replacement blocks the stale target", ("Terminal", "Command Prompt", "PowerShell"), "high"),
        SmokeCase("privacy.trace", "privacy", "Diagnostics and traces contain no message or conversation content", ("all",), "critical"),
        SmokeCase("privacy.retry", "privacy", "Retry state remains session-only and content-free outside the active draft", ("all",), "high"),
    )


def case_ids(cases: Iterable[SmokeCase] | None = None) -> tuple[str, ...]:
    """Return stable case identifiers for template/report generation."""
    selected = tuple(cases or default_cases())
    return tuple(case.case_id for case in selected)


def matrix_fingerprint(cases: Iterable[SmokeCase] | None = None) -> str:
    """Return a stable hash of the safe smoke-case definitions.

    The fingerprint makes a manual report self-describing: a report created
    from an older matrix cannot silently validate against a newer matrix.
    """
    selected = tuple(cases or default_cases())
    payload = [
        {
            "case_id": case.case_id,
            "area": case.area,
            "title": case.title,
            "apps": list(case.apps),
            "priority": case.priority,
            "destructive": case.destructive,
        }
        for case in selected
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_report(
    environment: Mapping[str, object] | None = None,
    cases: Iterable[SmokeCase] | None = None,
) -> dict:
    """Build a JSON-safe blank report for manual desktop execution."""
    selected = tuple(cases or default_cases())
    return {
        "schema_version": SCHEMA_VERSION,
        "matrix_fingerprint": matrix_fingerprint(selected),
        "environment": dict(environment or {}),
        "cases": [
            {
                **asdict(case),
                "apps": list(case.apps),
                "result": RESULT_PENDING,
                "notes": "",
                "tested_at": "",
                "evidence": {},
            }
            for case in selected
        ],
    }


def validate_report(report: Mapping[str, object]) -> tuple[str, ...]:
    """Return stable validation errors for a manually edited smoke report."""
    errors: list[str] = []
    registry_errors = registry_validation_errors()
    errors.extend(f"adapter registry: {error}" for error in registry_errors)

    raw_schema = report.get("schema_version", -1)
    try:
        schema_version = int(raw_schema)
    except (TypeError, ValueError):
        errors.append("invalid schema_version")
    else:
        if schema_version != SCHEMA_VERSION:
            errors.append("unsupported schema_version")

    expected_fingerprint = matrix_fingerprint()
    actual_fingerprint = str(report.get("matrix_fingerprint", "")).strip()
    if not actual_fingerprint:
        errors.append("matrix_fingerprint is missing")
    elif actual_fingerprint != expected_fingerprint:
        errors.append("matrix_fingerprint does not match current smoke matrix")

    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        return tuple(errors) + ("cases must be a list",)

    expected_cases = {case.case_id: case for case in default_cases()}
    seen = set()
    immutable_fields = ("area", "title", "apps", "priority", "destructive")
    for item in raw_cases:
        if not isinstance(item, Mapping):
            errors.append("case entry must be an object")
            continue
        case_id = str(item.get("case_id", ""))
        if not case_id:
            errors.append("case missing case_id")
            continue
        if case_id in seen:
            errors.append(f"duplicate case_id: {case_id}")
        seen.add(case_id)
        expected_case = expected_cases.get(case_id)
        if expected_case is None:
            errors.append(f"unknown case_id: {case_id}")
            continue
        for field in immutable_fields:
            expected_value = getattr(expected_case, field)
            actual_value = item.get(field)
            if field == "apps":
                actual_value = tuple(actual_value) if isinstance(actual_value, (list, tuple)) else actual_value
                expected_value = tuple(expected_value)
            if actual_value != expected_value:
                errors.append(f"case definition mismatch for {case_id}: {field}")
        result = str(item.get("result", RESULT_PENDING))
        if result not in RESULTS:
            errors.append(f"invalid result for {case_id}: {result}")

    missing = sorted(set(expected_cases) - seen)
    errors.extend(f"missing case_id: {case_id}" for case_id in missing)
    return tuple(errors)


def environment_case_errors(report: Mapping[str, object]) -> tuple[str, ...]:
    """Return environment-evidence errors for completed PASS cases."""
    environment = report.get("environment")
    if not isinstance(environment, Mapping):
        return ("environment snapshot is missing",)

    errors: list[str] = []
    raw_cases = report.get("cases", ())
    if not isinstance(raw_cases, list):
        return tuple(errors)

    raw_adapters = environment.get("adapters", ())
    adapters: dict[str, Mapping[str, object]] = {}
    if isinstance(raw_adapters, list):
        for item in raw_adapters:
            if isinstance(item, Mapping):
                key = str(item.get("key", "")).strip()
                if key:
                    adapters[key] = item

    for item in raw_cases:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("case_id", "")) != "env.dpi":
            continue
        if str(item.get("result", RESULT_PENDING)) != RESULT_PASS:
            continue
        evidence = item.get("evidence")
        if not isinstance(evidence, Mapping):
            errors.append("environment case evidence missing for env.dpi")
            continue
        if str(evidence.get("recorded_at", "")).strip() != str(item.get("tested_at", "")).strip():
            errors.append("environment case evidence timestamp mismatch for env.dpi")
            continue
        raw_monitors = evidence.get("monitors", ())
        monitors = raw_monitors if isinstance(raw_monitors, list) else []
        dpi_values = {
            (int(monitor.get("dpi_x", 0) or 0), int(monitor.get("dpi_y", 0) or 0))
            for monitor in monitors
            if isinstance(monitor, Mapping)
            and int(monitor.get("dpi_x", 0) or 0) > 0
            and int(monitor.get("dpi_y", 0) or 0) > 0
        }
        if len(monitors) < 2 or len(dpi_values) < 2:
            errors.append("env.dpi PASS requires at least two monitors with distinct effective DPI values")

    required_processes = {
        "terminal.acceptance.wt": (("terminal",), {"windowsterminal.exe", "wt.exe"}),
        "terminal.acceptance.preview": (("terminal",), {"windowsterminalpreview.exe"}),
        "terminal.acceptance.conhost": (("terminal", "cmd"), {"conhost.exe", "cmd.exe"}),
        "terminal.acceptance.pwsh": (("powershell",), {"pwsh.exe"}),
    }
    restart_process_requirements = {
        "env.restart": {
            "all": {"telegram.exe", "whatsapp.exe", "discord.exe", "slack.exe", "teams.exe", "msteams.exe", "ms-teams.exe", "windowsterminal.exe", "windowsterminalpreview.exe", "conhost.exe", "cmd.exe", "pwsh.exe"},
        },
        "telegram.restart": {"telegram": {"telegram.exe"}},
        "chat.restart": {
            "whatsapp": {"whatsapp.exe"},
            "discord": {"discord.exe"},
            "slack": {"slack.exe"},
            "teams": {"teams.exe", "msteams.exe", "ms-teams.exe"},
        },
        "terminal.restart": {
            "terminal": {"windowsterminal.exe", "wt.exe", "windowsterminalpreview.exe", "conhost.exe"},
            "cmd": {"cmd.exe"},
            "powershell": {"pwsh.exe"},
        },
    }
    adapter_cases = {
        "telegram": {"telegram"},
        "whatsapp": {"whatsapp"},
        "discord": {"discord"},
        "slack": {"slack"},
        "teams": {"teams"},
        "terminal": {"terminal"},
        "cmd": {"cmd"},
        "powershell": {"powershell"},
    }
    critical_app_process_requirements = {
        "telegram.send": {"telegram": {"telegram.exe"}},
        "telegram.multiwindow": {"telegram": {"telegram.exe"}},
        "telegram.context": {"telegram": {"telegram.exe"}},
        "telegram.unverified": {"telegram": {"telegram.exe"}},
        "telegram.retry": {"telegram": {"telegram.exe"}},
        "chat.whatsapp": {"whatsapp": {"whatsapp.exe"}},
        "chat.discord": {"discord": {"discord.exe"}},
        "chat.slack": {"slack": {"slack.exe"}},
        "chat.teams": {"teams": {"teams.exe", "msteams.exe", "ms-teams.exe"}},
        "terminal.submit": {
            "terminal": {
                "windowsterminal.exe",
                "wt.exe",
                "windowsterminalpreview.exe",
                "conhost.exe",
            }
        },
    }

    expected_case_map = {case.case_id: case for case in default_cases()}
    for item in raw_cases:
        if not isinstance(item, Mapping) or str(item.get("result", RESULT_PENDING)) != RESULT_PASS:
            continue
        case_id = str(item.get("case_id", "")).strip()
        expected_case = expected_case_map.get(case_id)
        if expected_case is None:
            continue
        process_requirement = required_processes.get(case_id)
        if process_requirement:
            adapter_keys, expected_processes = process_requirement
            observed = set()
            for adapter_key in adapter_keys:
                spec = adapters.get(adapter_key)
                case_evidence = item.get("evidence")
                raw_instances = case_evidence.get("process_instances", ()) if isinstance(case_evidence, Mapping) else ()
                if isinstance(raw_instances, list):
                    for instance in raw_instances:
                        if isinstance(instance, Mapping):
                            name = str(instance.get("process_name", "")).casefold()
                            start = instance.get("process_start")
                            if name in expected_processes and isinstance(start, int) and not isinstance(start, bool) and start > 0:
                                observed.add(name)
            case_evidence = item.get("evidence")
            if not isinstance(case_evidence, Mapping):
                errors.append(f"environment case evidence missing for {case_id}")
            elif str(case_evidence.get("recorded_at", "")).strip() != str(item.get("tested_at", "")).strip():
                errors.append(f"environment case evidence timestamp mismatch for {case_id}")
            elif not (observed & expected_processes):
                errors.append(f"environment evidence missing for {case_id}")
            continue

        restart_requirement = restart_process_requirements.get(case_id)
        if restart_requirement:
            for adapter_key, expected_processes in restart_requirement.items():
                if adapter_key == "all":
                    relevant = {
                        key: spec
                        for key, spec in adapters.items()
                        if isinstance(spec, Mapping)
                    }
                else:
                    spec = adapters.get(adapter_key)
                    relevant = {adapter_key: spec} if spec is not None else {}
                instances = set()
                case_evidence = item.get("evidence")
                raw_instances = case_evidence.get("process_instances", ()) if isinstance(case_evidence, Mapping) else ()
                if isinstance(raw_instances, list):
                    for item_instance in raw_instances:
                        if not isinstance(item_instance, Mapping):
                            continue
                        name = str(item_instance.get("process_name", "")).casefold()
                        start = item_instance.get("process_start")
                        recorded_adapter = str(item_instance.get("adapter_key", "")).strip()
                        if (
                            recorded_adapter == adapter_key
                            and name in expected_processes
                            and isinstance(start, int)
                            and not isinstance(start, bool)
                            and start > 0
                        ):
                            instances.add((name, start))
                if not isinstance(case_evidence, Mapping):
                    errors.append(f"environment case evidence missing for {case_id} ({adapter_key})")
                elif str(case_evidence.get("recorded_at", "")).strip() != str(item.get("tested_at", "")).strip():
                    errors.append(f"environment case evidence timestamp mismatch for {case_id} ({adapter_key})")
                elif not instances:
                    errors.append(f"environment process-instance evidence missing for {case_id} ({adapter_key})")
            continue

        critical_requirement = critical_app_process_requirements.get(case_id)
        if critical_requirement:
            for adapter_key, expected_processes in critical_requirement.items():
                instances = set()
                case_evidence = item.get("evidence")
                raw_instances = case_evidence.get("process_instances", ()) if isinstance(case_evidence, Mapping) else ()
                if isinstance(raw_instances, list):
                    for item_instance in raw_instances:
                        if not isinstance(item_instance, Mapping):
                            continue
                        name = str(item_instance.get("process_name", "")).casefold()
                        start = item_instance.get("process_start")
                        recorded_adapter = str(item_instance.get("adapter_key", "")).strip()
                        if (
                            recorded_adapter == adapter_key
                            and name in expected_processes
                            and isinstance(start, int)
                            and not isinstance(start, bool)
                            and start > 0
                        ):
                            instances.add((name, start))
                if not isinstance(case_evidence, Mapping):
                    errors.append(
                        f"environment case evidence missing for {case_id} ({adapter_key})"
                    )
                elif str(case_evidence.get("recorded_at", "")).strip() != str(item.get("tested_at", "")).strip():
                    errors.append(
                        f"environment case evidence timestamp mismatch for {case_id} ({adapter_key})"
                    )
                elif not instances:
                    errors.append(
                        f"environment process-instance evidence missing for {case_id} ({adapter_key})"
                    )
            continue

        adapter_key = next(
            (adapter for adapter in adapter_cases if case_id == f"chat.{adapter}"),
            None,
        )
        if case_id.startswith("telegram."):
            adapter_key = "telegram"
        if adapter_key:
            spec = adapters.get(adapter_key)
            observed_count = int(spec.get("open_window_count", 0) or 0) if spec is not None else 0
            if observed_count <= 0:
                errors.append(f"environment evidence missing for {case_id}")

    return tuple(errors)


def summarize_report(report: Mapping[str, object]) -> dict[str, int]:
    """Return stable counts for a smoke report without inspecting its notes."""
    counts = {result.lower(): 0 for result in RESULTS}
    raw_cases = report.get("cases", ())
    if isinstance(raw_cases, list):
        for item in raw_cases:
            if isinstance(item, Mapping):
                result = str(item.get("result", RESULT_PENDING))
                if result in RESULTS:
                    counts[result.lower()] += 1
    counts["total"] = sum(counts.values())
    return counts


def pending_case_ids(report: Mapping[str, object]) -> tuple[str, ...]:
    """Return case IDs still awaiting a manual result."""
    raw_cases = report.get("cases", ())
    pending = []
    if isinstance(raw_cases, list):
        for item in raw_cases:
            if isinstance(item, Mapping) and str(item.get("result", RESULT_PENDING)) == RESULT_PENDING:
                case_id = str(item.get("case_id", ""))
                if case_id:
                    pending.append(case_id)
    return tuple(pending)


def completion_errors(report: Mapping[str, object]) -> tuple[str, ...]:
    """Return completed cases that lack the operator timestamp."""
    raw_cases = report.get("cases", ())
    errors = []
    if isinstance(raw_cases, list):
        for item in raw_cases:
            if not isinstance(item, Mapping):
                continue
            result = str(item.get("result", RESULT_PENDING))
            case_id = str(item.get("case_id", "")).strip()
            tested_at = str(item.get("tested_at", "")).strip()
            if result != RESULT_PENDING and case_id and not tested_at:
                errors.append(f"missing tested_at for {case_id}")
    return tuple(errors)


__all__ = [
    "RESULT_BLOCKED",
    "RESULT_FAIL",
    "RESULT_PASS",
    "RESULT_PENDING",
    "RESULTS",
    "SCHEMA_VERSION",
    "SmokeCase",
    "SmokeResult",
    "build_report",
    "case_ids",
    "completion_errors",
    "environment_case_errors",
    "default_cases",
    "matrix_fingerprint",
    "pending_case_ids",
    "summarize_report",
    "validate_report",
]
