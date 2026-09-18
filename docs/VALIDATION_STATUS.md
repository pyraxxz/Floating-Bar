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
- Release-gate checks for a Windows environment snapshot, valid source commit ancestry, and an execution timestamp for every completed smoke case.
- Content-free Windows environment snapshots covering Windows build, Python version, architecture, monitor count, DPI-awareness, observed supported-app windows, and observed executable file versions.
- Adapter-registry consistency checks for duplicate keys, executable alias collisions, malformed aliases, unsupported capabilities, and inconsistent chat/type metadata.
- Generic background-target leases can add a content-free process-start identity to HWND/PID validation, rejecting rare PID-reuse cases while degrading safely to the existing scope checks when the metadata cannot be queried.
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

The report's matrix fingerprint prevents a report created against an older smoke matrix from silently validating against a newer matrix. The release workflow also verifies that the recorded source commit is an ancestor of the tagged release source before publication.
