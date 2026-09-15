# Transaction safety boundary

The production send path has explicit target/context guards both before the injector starts work and around the transaction preparation boundary.

## Preparation boundary

A send is first authorized by read-only preflight and bound to the exact Telegram `HWND/PID`. The coordinator now validates that lease immediately after binding and again after context/UIA validation. This closes a race where Telegram could be restarted or a window could be replaced while context inspection was still running.

The coordinator therefore requires all of the following before constructing the immutable `SendAttempt`:

- preflight reports a ready state;
- an explicit preferred window, when supplied, remains the selected window;
- the exact target lease matches the preflight `HWND/PID` immediately after binding;
- the captured non-content `WindowContext` still matches;
- the live target lease still matches after context validation.

Any mismatch releases the partially acquired lease and refuses the send instead of rediscovering another Telegram window.

## Final injection boundary

A prepared send already carries the exact Telegram target and the non-content `WindowContext` captured by preflight. The context-aware injector revalidates both immediately before delegating to the underlying send implementation.

The final guard checks:

- the bound Telegram top-level `HWND/PID` still exists and is the same target;
- the captured non-content conversation context still matches when a guard is available;
- malformed or unavailable target state fails closed rather than allowing the legacy injector to continue.

Per-action scope/context checks remain in place after this barrier. The layered checks are deliberate: they close both the preparation-to-context-inspection race and the smaller context-to-injection race without changing the established WM_CHAR submission strategy.

## Why this matters

The preparation phase, UIA context inspection, and actual injection run on a worker thread but are separated by calls into Windows/UIA. Telegram can restart, the bound window can disappear, a window handle can be reused, or the selected conversation can change during those gaps. The transaction must therefore revalidate the exact target at each boundary rather than treating a successful earlier observation as permanent authority.

This also protects the diagnostic `--send` path because it uses the same transaction coordinator and `ContextGuardedRecoveryInjector` as the production orb.

## Regression coverage

The transaction regression suite verifies that:

- stale target scope blocks the send during preflight preparation;
- a silent retarget after preflight is rejected;
- a target replacement during context validation is rejected;
- changed conversation context blocks the send before the worker reaches injection;
- a valid target/context reaches the established injector unchanged;
- lease release occurs on every rejected preparation path.

The context-injector suite additionally verifies the final target/context barrier, per-action checks, unavailable Telegram HWND handling, and compatibility of the no-context path.

This is a safety boundary, not a claim of exact chat identity on every Telegram build. When Telegram exposes no usable non-content context anchor, the existing degraded-context behavior remains explicit rather than fabricating confidence.
