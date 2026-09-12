# Floating Bar architecture and implementation roadmap

## 1. Product boundary

Floating Bar is a small Windows desktop overlay that captures a short-lived draft and injects it into a currently selected background application without using that application's API or credentials.

The current production target is Telegram Desktop. The architecture is deliberately being shaped so Telegram-specific discovery can later become one target adapter for a broader background-app injector.

The core product invariant is **safe best-effort background interaction**: when target identity or submission evidence becomes ambiguous, the application must stop rather than guess.

## 2. Current runtime architecture

```text
Tk overlay
  |
  +--> attempt state / retry draft / evidence state
  |
  +--> preflight gate
  |      |
  |      +--> TelegramTarget discovery
  |      +--> compose discovery
  |      +--> Send-button evidence
  |      +--> HWND/PID stability
  |      +--> optional conversation-context fingerprint
  |
  +--> ContextGuardedRecoveryInjector
         |
         +--> HardenedTelegramInjector
                |
                +--> ScopeGuardedRecoveryInjector
                       |
                       +--> existing injector cascade
                              |
                              +--> invisible WM_CHAR posting
                              +--> audit / re-target
                              +--> safe Send click
                              +--> Enter fallback
                              +--> optional focus-steal recovery
                              +--> optional clipboard recovery
```

The inheritance is historical: the hardening layers intentionally preserve the established injector while adding guards. A later cleanup phase should move toward composition/interfaces so the generic send transaction does not depend on Telegram-specific implementation classes.

## 3. Target discovery

`floatingbar.target.TelegramTarget` owns Telegram-specific UI discovery.

### Window identity

Discovery prefers the Telegram process image name and can fall back to a strict Telegram title pattern for portable/renamed installations. A selected window is represented by its top-level HWND and PID.

A remembered UI Automation runtime ID is only a session-local hint. It is invalidated when the Telegram HWND/PID scope changes, and remembered compose geometry is revalidated before reuse.

### Compose discovery

Telegram can expose nested Edit controls. The usable compose is selected using geometry and editability rather than trusting one permanent UIA identity. A remembered compose is accepted only if it still has plausible geometry in the lower part of the Telegram window and is not read-only.

### Send discovery

The Send-button selector uses multiple evidence sources:

- accessible name containing Send;
- automation ID containing Send;
- Invoke-pattern availability;
- alignment with the compose row;
- horizontal proximity to the compose control;
- plausible button dimensions.

Voice/record/microphone/audio controls are always rejected. Named controls that do not identify themselves as Send are rejected even when their geometry is plausible. Weak unnamed icons do not get clicked and fall through to Enter submission.

## 4. Preflight contract

`floatingbar.preflight.run()` is deliberately read-only. It may discover controls and inspect state, but it must not:

- post mouse or keyboard messages;
- change foreground focus;
- read message content;
- modify the clipboard.

The result captures the exact Telegram HWND/PID selected for the operation, compose geometry, submission path, scope stability, and optional context-guard availability.

A Send is blocked when the hard prerequisites are not safe: Telegram missing, minimized, compose geometry unavailable, or the HWND/PID scope changes during preflight.

A generic Telegram title does not automatically block the operation. In that configuration the system reports degraded context protection while retaining the stronger HWND/PID guard.

## 5. Send transaction invariants

Every production send should satisfy these invariants:

1. **Exact target binding.** The HWND/PID selected by preflight is the target for the transaction. A later discovery pass must not silently retarget another Telegram window.
2. **Context binding when available.** When Telegram exposes useful title context, the title fingerprint is compared before critical actions. Raw title text is not retained or logged.
3. **Minimized-target refusal.** A minimized Telegram window is not treated as a viable invisible target.
4. **No accidental mic click.** Voice/record/mic/audio controls are never considered a safe Send target.
5. **No ambiguous named-button click.** A named control must explicitly identify itself as Send; otherwise the transaction falls back to Enter or stops safely.
6. **Content-free diagnostics.** Logs contain lengths, identifiers, geometry, labels, stage names, scores, and booleans rather than message content.
7. **No automatic uncertain retry.** A submission that cannot be confirmed is represented as uncertain and is not automatically resent.
8. **Session-only failed drafts.** Retry text is held only for the current application session and is never persisted as history.
9. **Recovery remains opt-in.** Focus-steal and clipboard recovery are disabled unless explicitly configured, and target scope is checked before critical actions.
10. **Foreground restoration.** If a recovery path raises Telegram, the user's prior foreground window is restored afterward when possible.

## 6. Context protection

`floatingbar.context` captures a one-way HMAC fingerprint of the Telegram window title using a per-process secret. The purpose is not to identify the user or expose the chat name; it is only to detect a title change between the start of a send and later interaction.

The context model intentionally degrades when the title is empty or generic. In that case HWND/PID remains protected, but a chat switch inside the same Telegram window cannot be inferred from the title alone.

This is an important boundary: the application must never claim stronger conversation protection than the available UI evidence supports.

## 7. Injection stages

### Phase 0: target the compose row

Where geometry is available, the injector posts a click to the selected compose control. This is designed to preserve the application's background interaction model rather than taking foreground focus.

### Phase 1: land text

Text is posted as UTF-16 code units through the established WM_CHAR path. The implementation explicitly supports astral Unicode by emitting the required surrogate pair.

### Phase 1.5: audit and re-target

The injector inspects Edit controls through value-length-only reads. If the usable text is found in a nested Edit that overlaps the selected compose, that nested control becomes the trusted verification channel and is remembered for subsequent sends.

If text appears in a non-overlapping Edit, the injector performs one bounded compose retry. It then fails honestly rather than guessing at another control.

### Phase 2: submit

A verified compose uses asynchronous clear-on-submit verification. A safe Send button is preferred. If no safe button is available, Enter submission is attempted and verified where the read channel allows it.

The result is typed into an evidence model (`confirmed`, `failed/retryable`, or `uncertain`) so the UI cannot accidentally present an uncertain result as confirmed or auto-retry it.

## 8. Overlay state model

The UI intentionally remains small:

```text
orb
  -> expanded compose
  -> sending
  -> confirmed / uncertain / failed
  -> orb

failed
  -> retry failed draft
  -> explicit Enter
```

The retry path preserves the original target HWND when available and, when context protection exists, also preserves the original context guard. Opening the retry menu itself must not cause the retry to retarget to whatever happens to be foreground at that moment.

Stale worker results are ignored through an attempt ID so an older background send cannot overwrite newer UI state.

## 9. Diagnostics and privacy

`tools/diagnose.py --preflight` is intended as the primary support tool. Preflight diagnostics should remain read-only and should be safe to run while the user is working.

The trace file is session-scoped and reset at application startup. The trace contract is:

- message content: never logged;
- raw Telegram title: never logged;
- value reads: reduced to lengths/booleans;
- useful troubleshooting evidence: geometry, stage, semantic label, identifier, scores, and state transitions.

## 10. Automated validation

Windows CI is the authoritative automated gate. The workflow compiles Python sources, runs the regression suite, and builds the Windows executable.

The regression suite currently covers:

- conversation fingerprint semantics;
- context-aware aborts;
- preflight blocking/degraded modes;
- exact preflight target binding;
- DPI API behavior;
- evidence classification;
- compose targeting and nested Edit behavior;
- asynchronous submission verification;
- voice/unrelated Send-button rejection;
- overlay retry and stale-result handling;
- recovery target-scope guards;
- Telegram target cache/geometry resilience;
- UTF-16 text posting.

## 11. Release policy

Do not create a public release for every small fix. `main` is the development line. A release should represent a coherent accumulated milestone and must satisfy both automated and real-desktop acceptance.

The current release milestone is tracked in GitHub Issue #2 as **0.2.0 Reliability**.

The 0.2.0 release gate is:

1. exact release source passes Windows CI;
2. read-only preflight passes on the real Windows/Telegram environment;
3. invisible send works in the intended chat;
4. multiple Telegram windows remain correctly targeted;
5. Telegram restart is refused safely;
6. conversation-switch protection works when useful title context exists;
7. degraded generic-title behavior is accurately reported;
8. failed-send retry is explicit and never automatic;
9. Send-button safety is validated against unrelated and voice controls;
10. mixed-DPI/multi-monitor behavior is validated;
11. emoji and intentional whitespace survive intact;
12. opt-in recovery stops safely when the original target is replaced.

Only after those gates pass should `v0.2.0` be tagged and published.

## 12. Next implementation phases

### Phase A — Reliability completion

Current phase. Finish automated edge cases, keep the Windows build green, and validate the desktop smoke-test matrix. Do not expand the feature surface until the send transaction is trustworthy.

### Phase B — Separate target interface

Introduce a small target contract such as:

```python
class BackgroundTarget(Protocol):
    def discover(self, preferred_hwnd: int = 0) -> TargetScope: ...
    def preflight(self, scope: TargetScope) -> PreflightResult: ...
    def locate_compose(self, scope: TargetScope) -> ComposeTarget: ...
    def submit(self, scope: TargetScope, compose: ComposeTarget) -> SubmissionResult: ...
```

Telegram-specific UIA/window discovery stays inside `TelegramTarget`; the overlay and transaction state machine should depend on the interface, not on Telegram details.

Do not generalize prematurely. The contract should only abstract behavior that is already proven stable in the Telegram implementation.

### Phase C — Generic background-app adapters

Add adapters for one or two non-Telegram desktop applications using the same target contract. Prefer deterministic Windows UI automation patterns and per-app safety evidence over a universal "click whatever looks right" strategy.

### Phase D — Transaction object and explicit state machine

Replace scattered mutable fields with a send-attempt object containing:

- immutable attempt ID;
- target scope;
- optional context fingerprint;
- compose target identity/geometry;
- draft text lifetime;
- submission strategy;
- evidence state.

The goal is to make invalid state transitions difficult to represent rather than merely checked after the fact.

### Phase E — Packaging and release engineering

Once the runtime behavior is stable, consolidate versioning, release notes, artifact naming, and reproducible packaging. Keep public version tags tied to milestone completion rather than individual bug fixes.

## 13. Known boundaries and non-goals

- No Telegram API, bot token, or login integration.
- No message history database.
- No cloud synchronization.
- No silent automatic retry after uncertain submission.
- No claim of exact chat identity when Telegram exposes insufficient non-content UI evidence.
- No universal guarantee that every future Telegram UI build will expose the same controls; failures should degrade safely and produce actionable diagnostics.

## 14. Practical engineering rule

When choosing between **send less often** and **send to the wrong place**, always choose the former.

That rule should dominate future changes to discovery, caching, recovery, heuristics, and adapter design.
