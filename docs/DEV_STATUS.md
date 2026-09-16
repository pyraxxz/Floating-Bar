# Development status

Stable public release: `v0.1.20`

Current milestone: **0.2.0 Reliability** (GitHub Issue #2)

`main` is the development line. The 0.2.0 tag is intentionally withheld until both the automated Windows gate and the real desktop acceptance matrix pass.

## Current architecture

The production Telegram path has explicit immutable transaction data plus a monotonic `TransactionLifecycle` state machine. A send attempt moves through `PREPARING -> READY -> SENDING` and then terminates as `VERIFIED`, `UNCERTAIN`, `FAILED`, or `REJECTED`. Overlay integration is guarded so stale completions cannot advance or release a newer attempt.

The production boundary also includes exact HWND/PID target binding, read-only preflight, content-free diagnostics, non-content context protection, typed Send/submission evidence, explicit failed-draft retry, target-scope checks around recovery, per-monitor-v2 DPI bootstrap, and UTF-16 WM_CHAR posting with surrogate-pair support.

The newer generic background-input layer now has dedicated structural composer/terminal targets, exact control pinning with identity revalidation, minimized-window support for background selection, and an adapter evidence policy that prevents unsupported generic paths from claiming verified sends.

## Validation discipline

Windows CI is the authoritative automated gate. A change is not considered complete merely because it compiles; the regression suite and Windows executable build must pass together.

A recent Windows CI run exposed stale regression fixtures and legacy error-message expectations after the target hardening batch. Those failures were isolated to tests: Python compilation succeeded and the newly added evidence/background-window tests passed. The fixtures are now aligned with the current target contract and a fresh Windows run is validating the corrected state.

## Next engineering target

Finish the reliability phase by turning the adapter evidence contract into real app-specific verification hooks. The immediate focus is bounded post-send checks for the generic chat and terminal adapters, while keeping all identity and diagnostics content-free. After that, proceed to stronger conversation targeting and real desktop smoke validation.

## Release gate

Before `v0.2.0`:

1. exact release source passes Windows CI;
2. read-only preflight passes on the real Windows/Telegram environment;
3. invisible send works in the intended chat;
4. multiple Telegram windows remain correctly targeted;
5. Telegram restart is refused safely;
6. conversation-switch protection works when useful title or structural context evidence exists;
7. degraded no-anchor behavior is accurately reported;
8. failed-send retry is explicit and never automatic;
9. Send-button safety is validated against unrelated and voice controls;
10. mixed-DPI/multi-monitor behavior is validated;
11. emoji and intentional whitespace survive intact;
12. opt-in recovery stops safely when the original target is replaced;
13. diagnostic JSON remains content-free and useful for support snapshots.
