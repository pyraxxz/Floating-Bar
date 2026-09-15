# Preflight safety boundary

The send transaction treats Telegram context inspection as a safety decision, not as optional telemetry.

A generic Telegram title with no structural anchors is a supported degraded state: the preflight reports that context could not be verified, but it may still proceed with the exact HWND/PID and per-action scope checks.

A failure to inspect the final context is different. It means the system cannot establish whether the target context stayed stable during preparation. That state is blocked rather than degraded.

This distinction prevents an accessibility/UIA inspection error from being interpreted as an intentional lack of available context signals.

The preflight therefore has three meaningful outcomes:

- `ready` — at least one non-content context anchor is available and stable.
- `ready-with-degraded-context` — no usable context anchor exists, but target scope and compose safety remain valid.
- `blocked` — target inspection, scope validation, compose inspection, or required context validation failed.

The preflight remains read-only. It never posts input, changes foreground focus, or touches the clipboard.
