# ADR-001: Background target contract

## Status
Accepted for incremental adoption on the `main` development line.

## Context

The Telegram implementation accumulated several reliability layers around one
concrete target class: discovery, compose selection, Send evidence, preflight,
context protection, and recovery. Reusing that inheritance chain for another
application would make the second adapter depend on Telegram-specific details.

At the same time, the Telegram behavior is not stable enough yet to justify a
large generic framework. The next abstraction should therefore name only the
smallest proven operations shared by a background target.

## Decision

Introduce `floatingbar.target_contract.BackgroundTarget` as a structural
protocol with four operations:

- `select_for_send(preferred_hwnd=0) -> int`
- `scope() -> TargetScope`
- `is_available() -> bool`
- `release() -> None` for deterministic transaction-lease cleanup

The protocol is the contract for a **bound transaction target**, not the raw
Telegram discovery object. `BoundTelegramTarget` is the current production
implementation; its `release()` operation clears the active lease and any
session-only chat confirmation.

`TargetScope` is an immutable tuple-compatible `(HWND, PID)` value. Returning a
named immutable value preserves existing tuple-unpacking callers while making
target identity explicit to new transaction code.

The existing `TelegramTarget` remains the concrete discovery/interaction
implementation underneath the bound facade. No generic UI automation framework
is introduced yet.

## Consequences

### Positive

- The overlay can eventually depend on a target contract instead of Telegram.
- Target identity can move through the send transaction as a typed value.
- Future adapters can be tested against the same minimum contract.
- The abstraction is small enough to remove or expand without rewriting the
  current Telegram injector.

### Negative

- Some existing code still calls Telegram-specific methods directly.
- The contract does not yet express compose discovery or submission evidence.
- The transaction coordinator still needs a target-specific preparation policy
  for preflight/context rules.
- The adapter boundary is therefore transitional, not the final architecture.

## Follow-up

The next architectural step is to introduce typed compose/submit contracts
only after the Telegram implementation has real-desktop validation. Do not
create a universal target interface merely for symmetry.

The reliability rule remains: when evidence is ambiguous, stop rather than
retarget or guess.
