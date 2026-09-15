# Transaction safety boundary

The production send path now has an explicit final guard immediately before the injector begins any work against Telegram.

## Boundary

A prepared send already carries the exact Telegram target and the non-content `WindowContext` captured by preflight. The context-aware injector now revalidates both immediately before delegating to the underlying send implementation.

The final guard checks:

- the bound Telegram top-level `HWND/PID` still exists and is the same target;
- the captured non-content conversation context still matches when a guard is available;
- malformed or unavailable target state fails closed rather than allowing the legacy injector to continue.

Per-action scope/context checks remain in place after this barrier. The new check is deliberately additive: it closes the small gap between transaction preparation and the first injection action without changing the established WM_CHAR submission strategy.

## Why this matters

The preparation phase and actual injection run on the worker thread but are still separated by Python/UIA work. Telegram can restart, the bound window can disappear, or the selected conversation can change during that gap. Previously the first hard guard occurred when the injector reached the compose phase. Now the send cannot cross into that phase without a fresh target/context check.

This also protects the diagnostic `--send` path because it uses the same `ContextGuardedRecoveryInjector` as the production orb.

## Regression coverage

The context-injector regression suite now verifies that:

- stale target scope blocks the send before the parent injector is entered;
- changed conversation context blocks the send before the parent injector is entered;
- unavailable Telegram HWND blocks the send;
- a valid target/context reaches the established parent injector unchanged;
- existing per-action context checks remain enforced;
- no-context operation remains compatible with the previous behavior.

This is a safety boundary, not a claim of exact chat identity on every Telegram build. When Telegram exposes no usable non-content context anchor, the existing degraded-context behavior remains explicit rather than fabricating confidence.
