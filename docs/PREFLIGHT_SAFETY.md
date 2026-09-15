# Preflight safety boundary

The send transaction treats Telegram context inspection as a safety decision, not as optional telemetry.

A generic Telegram title with no structural anchors is a supported degraded state: the preflight reports that context could not be verified, but it may still proceed with the exact HWND/PID and per-action scope checks.

A failure to inspect the final context is different. It means the system cannot establish whether the target context stayed stable during preparation. That state is blocked rather than degraded.

This distinction prevents an accessibility/UIA inspection error from being interpreted as an intentional lack of available context signals.

The preflight therefore has three meaningful outcomes:

- `ready` — at least one non-content context anchor is available and stable.
- `ready-with-degraded-context` — no usable context anchor exists, but target scope and compose safety remain valid.
- `blocked` — target inspection, scope validation, compose inspection, or required context validation failed.

Every result also carries stable, content-free `reason_codes` for automated smoke tests. `primary_reason_code` identifies the dominant signal: a blocked result prefers the first fatal safety code over non-blocking warnings such as missing Send-button evidence; otherwise the first reported code is retained. A fully successful guarded preflight reports `ok`. These codes are deliberately independent of the human-readable notes so test tooling does not need to parse prose. The JSON diagnostic schema is version `2`.

Current codes include:

| Code | Meaning |
| --- | --- |
| `TARGET_NOT_FOUND` | No usable Telegram target was discovered. |
| `TARGET_INSPECTION_FAILED` | Target discovery/inspection raised unexpectedly. |
| `TARGET_SCOPE_INSPECTION_FAILED` | Initial HWND/PID scope could not be inspected. |
| `TARGET_MINIMIZED` | Telegram is minimized, so background interaction is blocked. |
| `TARGET_SCOPE_CHANGED` | The target HWND/PID changed during preflight. |
| `TARGET_SCOPE_REVALIDATION_FAILED` | Final target scope could not be revalidated safely. |
| `INITIAL_CONTEXT_INSPECTION_FAILED` | Initial conversation context inspection failed. |
| `FINAL_CONTEXT_INSPECTION_FAILED` | Final conversation context inspection failed. |
| `CONTEXT_CHANGED` | An initially available conversation anchor changed or disappeared. |
| `CONTEXT_VERIFICATION_FAILED` | Context validation failed even though transition comparison did not identify the exact anchor. |
| `CONTEXT_GUARD_UNAVAILABLE` | No usable non-content context anchor was exposed; the result is degraded rather than blocked. |
| `COMPOSE_NOT_FOUND` | The compose surface was not available. |
| `COMPOSE_INSPECTION_FAILED` | Compose UIA inspection failed unexpectedly. |
| `COMPOSE_GEOMETRY_UNAVAILABLE` | Compose control was found but no safe click geometry was available. |
| `SEND_BUTTON_UNAVAILABLE` | No semantically safe Send button was exposed; Enter fallback is required. |
| `FOCUS_INSPECTION_FAILED` | Focus ownership could not be inspected safely. |
| `FOCUS_OWNERSHIP_MISMATCH` | The focused child HWND belongs to another process. |
| `MINIMIZED_INSPECTION_FAILED` | Minimized state could not be inspected safely. |

The preflight remains read-only. It never posts input, changes foreground focus, or touches the clipboard.
