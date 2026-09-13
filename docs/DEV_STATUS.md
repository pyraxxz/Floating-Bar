# Development status

## Stable release

`v0.1.20` remains the current public/stable release. Small changes on `main`
do not create public releases.

## Current milestone

`0.2.0 Reliability` is tracked in GitHub Issue #2. The code-side reliability
work is substantially implemented and Windows CI has repeatedly validated the
source and packaged executable.

## Latest architecture work

The development line now includes:

- immutable `TargetScope`, `SendAttempt`, and `SendCompletion` models;
- a runtime-checkable `BackgroundTarget` protocol;
- `TelegramTarget.scope()` returning the tuple-compatible `TargetScope`;
- production preflight and context guards;
- exact target binding and guarded recovery;
- explicit retry state and typed submission evidence.

The target contract is intentionally incremental. Compose and submission
interfaces should only be generalized after real Telegram desktop validation.

## Release rule

Do not tag a new version because a single fix was added. Tag `v0.2.0` only when
Issue #2's automated and real-desktop acceptance gates are satisfied together.

## Next work

1. Complete real-desktop Telegram smoke validation.
2. Continue transaction-state migration so mutable overlay fields gradually
   become data from `SendAttempt` rather than parallel sources of truth.
3. Introduce typed compose/submission target contracts after the Telegram path
   is proven stable.
4. Only then begin the first non-Telegram adapter.
