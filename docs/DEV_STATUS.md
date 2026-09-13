# Development status

## Stable release

`v0.1.20` remains the current public/stable release. Small changes on `main`
do not create public releases.

## Current milestone

`0.2.0 Reliability` is tracked in GitHub Issue #2. The code-side reliability
work is substantially implemented and the Windows CI pipeline validates both
the regression suite and the Windows executable build.

## Latest architecture work

The development line now includes:

- immutable `TargetScope`, `SendRequest`, `SendAttempt`, and `SendCompletion` models;
- a runtime-checkable `BackgroundTarget` protocol with explicit target-scope guarding;
- a runtime-checkable `BackgroundInjector` protocol for the common `send()` capability;
- `TelegramTarget.scope()` returning the tuple-compatible `TargetScope`;
- production preflight and non-content context guards;
- exact target binding and guarded recovery;
- explicit retry state and typed submission evidence;
- prepared-send execution that consumes the immutable transaction target without
  repeating target selection;
- early transaction-identity validation before any preflight or target lease
  acquisition;
- content-free UIA context diagnostics and machine-readable preflight output.

The target and injector contracts are intentionally incremental. Compose and
submission interfaces should only be generalized further after real Telegram
desktop validation.

## Validation status

Windows CI run `#314` passed all 147 regression tests and the Windows executable
build after the evidence/completion compatibility fixes. Subsequent contract
changes are each running through the same Windows gate on `main`.

The remaining acceptance gap is real-desktop validation against the current
Telegram Desktop environment. Automated CI cannot prove actual message landing,
chat-switch behavior, mixed-DPI interaction, or UIA behavior on the user's
machine.

## Release rule

Do not tag a new version because a single fix was added. Tag `v0.2.0` only when
Issue #2's automated and real-desktop acceptance gates are satisfied together.

## Next work

1. Complete real-desktop Telegram smoke validation.
2. Continue transaction-state migration so mutable overlay fields gradually
   become data from `SendAttempt` rather than parallel sources of truth.
3. Generalize the compose/submission target capabilities only where Telegram
   behavior is proven and the contract remains small.
4. Only then begin the first non-Telegram adapter using the `BackgroundTarget`
   and `BackgroundInjector` boundaries.
