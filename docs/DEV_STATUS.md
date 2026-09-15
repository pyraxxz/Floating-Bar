# Development status

Stable public release: `v0.1.20`

Current milestone: **0.2.0 Reliability** (GitHub Issue #2)

`main` is the development line. The 0.2.0 tag is intentionally withheld until both the automated Windows gate and the real desktop acceptance matrix pass.

## Current architecture

The production Telegram path now has explicit immutable transaction data plus a monotonic `TransactionLifecycle` state machine. A send attempt moves through `PREPARING -> READY -> SENDING` and then terminates as `VERIFIED`, `UNCERTAIN`, `FAILED`, or `REJECTED`. Overlay integration is guarded so stale completions cannot advance or release a newer attempt.

The production boundary also includes exact HWND/PID target binding, read-only preflight, content-free diagnostics, non-content context protection, typed Send/submission evidence, explicit failed-draft retry, target-scope checks around recovery, per-monitor-v2 DPI bootstrap, and UTF-16 WM_CHAR posting with surrogate-pair support.

## Validation discipline

Windows CI is the authoritative automated gate. A change is not considered complete merely because it compiles; the regression suite and Windows executable build must pass together.

Recent lifecycle work exposed a compatibility edge in the Tk overlay test doubles. That failure is being treated as a test-contract defect to fix at the source, rather than repeatedly rerunning or stacking speculative commits.

The repository is now being worked in single-change slices: diagnose the current CI result, make the smallest targeted correction, verify the replacement run, then proceed. This avoids repeated failing notifications while the mobile GitHub client is enabled.

## Next engineering target

Finish the reliability phase by improving context-guard observability and desktop smoke coverage without reading message content or adding speculative chat-identification heuristics. After that, continue the planned composition cleanup and only then begin a generic non-Telegram adapter.

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
