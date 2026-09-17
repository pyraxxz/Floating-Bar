# Development status

Stable public release: `v0.1.20`

Current milestone: **0.2.0 Reliability** (GitHub Issue #2)

`main` is the development line. The 0.2.0 tag is intentionally withheld until both the automated Windows gate and the real desktop acceptance matrix pass.

## Current architecture

The production Telegram path has explicit immutable transaction data plus a monotonic `TransactionLifecycle` state machine. A send attempt moves through `PREPARING -> READY -> SENDING` and then terminates as `VERIFIED`, `UNCERTAIN`, `FAILED`, or `REJECTED`. Overlay integration is guarded so stale completions cannot advance or release a newer attempt.

The production boundary also includes exact HWND/PID target binding, read-only preflight, content-free diagnostics, non-content context protection, typed Send/submission evidence, explicit failed-draft retry, target-scope checks around recovery, per-monitor-v2 DPI bootstrap, and UTF-16 WM_CHAR posting with surrogate-pair support.

The newer generic background-input layer now has dedicated structural composer/terminal targets, exact control pinning with identity revalidation, minimized-window support for background selection, and an adapter evidence policy that prevents unsupported generic paths from claiming verified sends.

Terminal, CMD, and PowerShell adapters now also have a bounded `terminal-input-clear` verification hook. When the exact pinned input control exposes a readable UI Automation value, the path observes only value length: it requires post-injection growth and a return to zero after Enter. It never stores, logs, or compares command content, and it cannot claim command execution semantics.

The release workflow now requires a completed `smoke-report.json` with a valid Windows environment snapshot before packaging a milestone release. The report must also have every smoke case resolved to PASS, FAIL, or BLOCKED; FAIL or unresolved cases stop the release gate.

## Validation discipline

Windows CI is the authoritative automated gate. A change is not considered complete merely because it compiles; the regression suite and Windows executable build must pass together.

The terminal verification batch initially exposed one stale test fixture: the verified-evidence test referenced `terminal.exe`, which is not a registered adapter alias. The fixture was corrected to `wt.exe` while the actual terminal registry remained unchanged. Windows CI run `#657` then completed successfully with the full regression suite and Windows executable build passing.

The real-Windows smoke report remains separate from CI. CI proves deterministic logic and packaging on a Windows runner; the smoke report records acceptance against actual installed desktop applications, monitor/DPI layouts, restarts, repeated sends, and application-specific behavior.

## Next engineering target

Run the real desktop acceptance matrix for the terminal input-clear contract across Windows Terminal, Terminal Preview, conhost/CMD, and PowerShell Core variants. In parallel, continue app-specific semantic verification where shared compose-clear or input-clear evidence is insufficient, without weakening the fail-closed/content-free boundary. Then close the remaining multi-monitor, minimized/background, restart, Unicode, repeated-send, and application-version trace cases required for the `v0.2.0` gate.

## Release gate

Before `v0.2.0`:

1. exact release source passes Windows CI;
2. the release source contains a completed `smoke-report.json` from a real Windows validation run;
3. the smoke report environment identifies Windows and contains the required runtime fields;
4. every applicable smoke case is PASS or explicitly BLOCKED, with no FAIL or pending case;
5. read-only preflight passes on the real Windows/Telegram environment;
6. invisible send works in the intended chat;
7. multiple Telegram windows remain correctly targeted;
8. Telegram restart is refused safely;
9. conversation-switch protection works when useful title or structural context evidence exists;
10. degraded no-anchor behavior is accurately reported;
11. failed-send retry is explicit and never automatic;
12. Send-button safety is validated against unrelated and voice controls;
13. mixed-DPI/multi-monitor behavior is validated;
14. emoji and intentional whitespace survive intact;
15. opt-in recovery stops safely when the original target is replaced;
16. diagnostic JSON remains content-free and useful for support snapshots;
17. terminal input-control verification is validated on the supported Windows console variants without reading terminal content.
