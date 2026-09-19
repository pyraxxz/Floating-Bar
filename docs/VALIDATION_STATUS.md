# Floating Bar — validation status

This document records the current validation infrastructure on `main`. It is separate from the public release status: passing CI proves the regression suite and Windows packaging build, but does not substitute for real-desktop application smoke testing.

## Automated validation currently in place

- Python source compilation on `windows-latest`.
- Full regression suite on Windows.
- PyInstaller Windows executable build.
- Declarative 33-case real-desktop smoke matrix.
- Smoke-report schema validation with a matrix SHA-256 fingerprint.
- Field-level validation of immutable smoke-case definitions.
- Explicit handling for malformed schema versions, duplicate IDs, unknown IDs, invalid results, and missing cases.
- Release-gate checks for a Windows environment snapshot, valid exact source commit identity, execution timestamps for every completed smoke case, and case-local environment evidence captured when each result is recorded.
- Content-free Windows environment snapshots covering Windows build, Python version, architecture, monitor count, process DPI-awareness, per-monitor geometry/effective DPI, observed supported-app windows, observed executable file versions, and content-free process-instance identities (process name + process-start timestamp).
- Adapter-registry consistency checks for duplicate keys, executable alias collisions, malformed aliases, unsupported capabilities, and inconsistent chat/type metadata.
- Generic background-target leases, recent application targets, conversation rows, Telegram chat rows, retries, and the hover picker preserve content-free process-start identity alongside HWND/PID where available, rejecting same-PID process replacement before reuse.
- Critical/app-specific PASS cases require matching content-free process-instance evidence captured for that case, not merely an observed executable name from the initial report snapshot.
- Verification cannot claim `VERIFIED` solely from an observed clear: the exact pinned control is revalidated afterward, and chat targets additionally revalidate the selected conversation before publishing verified evidence.

## Real Windows validation still required

The smoke matrix remains the source of truth for human desktop validation. The remaining work is empirical rather than more mock coverage:

1. Windows 10 and Windows 11 runs with the supported desktop applications installed.
2. Windows Terminal, Terminal Preview, conhost/CMD, and PowerShell Core acceptance cases.
3. Telegram traces from multiple real Telegram Desktop builds.
4. WhatsApp, Discord, Slack, and Teams real-desktop smoke runs.
5. Mixed-DPI and multi-monitor behavior.
6. Minimized and multiple-window targeting.
7. Application restart/process replacement during active targeting and sending.
8. Unicode, emoji, long-text, and repeated-send behavior.
9. Installer/startup, clean upgrade, signed packaging, and release-update validation.

## Report discipline

A manually completed `smoke-report.json` must be generated from the same code revision that is being evaluated. The report records no message bodies, conversation content, raw window titles, input values, or clipboard content.

The report's matrix fingerprint prevents a report created against an older smoke matrix from silently validating against a newer matrix. `--record` captures a content-free case-local snapshot (process instances and monitor geometry) at the same timestamp as the result, and the release gate requires that evidence to match the case timestamp for critical/app-specific passes. Before publication, the release workflow also requires a successful Windows CI run triggered by a push to `main` for the exact tagged source commit, then verifies that the report's recorded source commit exactly matches the tagged release source.
