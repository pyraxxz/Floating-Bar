# Floating Bar — Windows / Real-Desktop Smoke-Test Protocol

This checklist is the manual validation gate for real Windows desktop behavior. The automated suite covers deterministic logic and mocked Win32/UIA boundaries; this document covers the parts that require real desktop applications.

## Test environment record

Record these before a run:

- Windows version/build:
- Application versions/builds under test:
- Floating Bar commit SHA:
- Display count:
- Display scaling per monitor:
- `ENTER_SEND_MODE`:
- `ALLOW_FOCUS_STEAL`:
- Result: PASS / FAIL / BLOCKED

Do not record message content, chat names, screenshots containing private conversations, or clipboard contents in the repository.

## Structured report workflow

Create a fresh, content-free report on the Windows test machine:

```powershell
python tools/smoke_report.py --init smoke-report.json
```

That command captures the machine/environment snapshot already used by the validation tooling, records the Git commit being tested as `environment.source_commit`, and creates one result entry for every smoke case. It does not read message bodies or store window titles.

After performing the tests, edit only the result metadata you need and validate the report:

```powershell
python tools/smoke_report.py --validate smoke-report.json
```

Use `--require-complete` for the release gate; it fails until every case is resolved to PASS, FAIL, or BLOCKED and the report contains a complete Windows environment snapshot including the tested source commit:

```powershell
python tools/smoke_report.py --validate smoke-report.json --require-complete
```

For a milestone release, commit the completed `smoke-report.json` into the exact release source before creating the version tag. The release workflow requires that file, verifies its required Windows environment fields, and checks that the recorded `source_commit` exactly matches the tagged release commit before installing release dependencies or building the Windows executable. This keeps the downloadable build tied to a recorded real-Windows acceptance result instead of treating unit-test success as desktop validation.

The validator checks the schema, duplicate/missing case IDs, result values, completion state, and the required Windows environment fields. Keep notes content-free; use short failure reasons such as `compose-not-found`, `target-replaced`, `uipi-blocked`, or `coordinate-offset` rather than copying private UI content.

## 1. Clean launch and idle behavior

1. Start Floating Bar with the target application already running.
2. Confirm the orb appears, stays always-on-top, and does not steal focus.
3. Open the orb into the bar.
4. Confirm the previously focused application remains the intended restore target.
5. Leave the bar idle long enough for the normal collapse timer to fire.
6. Confirm it returns to the orb without opening another window.

Expected: no unexpected foreground activation, no extra window, and no unexpected focus movement.

## 2. Background application picker

1. Open several supported background applications.
2. Hover the orb to open the app picker.
3. Confirm the picker shows application labels/actions without exposing window titles.
4. Test more than one window of the same application.
5. Hover across the app list and action popup without losing the transition.

Expected: the intended window remains selectable by structural HWND/PID identity; titles and message content are never shown.

## 3. Basic background send/reply

For each supported chat application that is installed and signed in:

1. Open the target conversation.
2. Focus a different application before opening Floating Bar.
3. Choose the background app and, where supported, choose its conversation from the picker.
4. Type a short test message and submit.
5. Confirm the message arrives in the intended conversation.
6. Repeat at least five times.

Expected: all sends land in the intended target; no duplicate sends occur; Floating Bar remains usable after each send.

## 4. Unicode and whitespace fidelity

Use separate sends containing:

- BMP Unicode text.
- Emoji and other astral Unicode characters.
- Leading whitespace that is intentionally meaningful.
- Trailing whitespace that is intentionally meaningful.
- A whitespace-only input.

Expected: meaningful whitespace and emoji survive unchanged; whitespace-only input is ignored without starting a send transaction.

## 5. Multiple application windows

1. Open two windows of the same supported application where the application permits this.
2. Put different conversations or workspaces in the windows.
3. Select each window through the background picker.
4. Repeat while Floating Bar is opened from a third application.

Expected: deterministic app ordinals distinguish duplicate labels, and the selected HWND/PID cannot silently change during the active send.

## 6. Conversation refresh/pagination

For WhatsApp, Discord, Slack, and Teams where conversation discovery is exposed:

1. Open enough conversations to exceed one picker page when practical.
2. Open the conversation picker.
3. Exercise Next, Previous, and Refresh.
4. Select a row after a refresh.

Expected: pagination is deterministic; Refresh rebuilds the ephemeral catalog; selection is immediately revalidated by runtime/structural identity before background clicking.

## 7. Chat-context change during preparation

For an application/build where a safe non-content structural anchor is available:

1. Start opening/preparing a send.
2. Change the selected conversation before the guarded target is committed.
3. Complete the send attempt.

Expected: the transaction is blocked or reported uncertain rather than silently sending into a changed target.

## 8. Telegram-specific background send

1. Open a Telegram chat with a useful, non-generic title when supported by the current build.
2. Focus a different application before opening Floating Bar.
3. Open the Telegram picker, select a chat, type, and press Enter.
4. Repeat multiple times.

Expected: the selected Telegram window/chat remains the guarded target; no foreground switch is required for the normal path; uncertain results are never automatically retried.

## 9. Telegram restart / stale target

1. Prepare a Telegram send.
2. Restart Telegram before the submission stage completes.
3. Attempt to complete the send.

Expected: the original HWND/PID scope is rejected; the application must not continue against the replacement window. Retry only after a fresh user action.

## 10. Minimized targets

1. Minimize the target application.
2. Open Floating Bar and attempt a send/type operation.
3. Restore the application and retry explicitly.

Expected: unsupported minimized operations are rejected honestly. The app must not report success merely because a post operation was attempted.

## 11. Structural input protection

For chat and generic applications:

1. Leave a search/navigation field populated where possible.
2. Keep the intended composer/input field available at the same time.
3. Open Floating Bar while a non-composer field is focused.

Expected: the structurally preferred composer wins; an ambiguous control is rejected rather than receiving text by accident.

## 12. Submission evidence and duplicate protection

1. Exercise normal responsive sends.
2. Exercise delayed UI-clear behavior when it occurs.
3. Exercise a temporarily unavailable verification path where safe.

Expected: delayed clearing does not create a duplicate send; an unverified-but-submitted result is surfaced as uncertain and is not automatically retried.

## 13. Failed-send retry UX

1. Force a genuine failed send condition without changing the original target.
2. Confirm the draft is retained only for the current process session.
3. Use `Retry failed draft`.
4. Confirm the original target context is restored/validated.
5. Verify that the retry does not submit until Enter is pressed.
6. Start typing a replacement instead.

Expected: failed text is recoverable, retry is explicit, no automatic duplicate is created, and replacement input clears the old retry context.

## 14. Terminal / CMD / PowerShell

1. Open a console application with an interactive prompt.
2. Focus another application.
3. Select the terminal through Floating Bar.
4. Type and submit a harmless command.
5. Repeat with focus in a different terminal control where the UI exposes more than one candidate.

Expected: the structurally discovered console input is selected and exact HWND/PID binding is preserved. The new terminal `terminal-input-clear` contract can verify the exact pinned input control only when its value is observed to grow after injection and clear after Enter; it does not read or log the command text. When that evidence is unavailable or the field does not clear, the result remains conservative and is never treated as a retryable failure.

## 15. Generic unknown application

Use an installed application not represented by the named adapter registry.

1. Open a text-capable input control.
2. Confirm the picker exposes the generic Type action.
3. Confirm structural discovery is required before the active bar appears.
4. Test an application with no safe editable control.

Expected: a safe structural target enables typing; an app without a safe target is blocked without injection.

## 16. Focus-steal recovery (only when explicitly enabled)

Run once with `ALLOW_FOCUS_STEAL=False` and once in a controlled test build with it enabled.

Expected with the default disabled setting: a failed invisible send does not steal foreground focus.

Expected when enabled: each recovery action revalidates the original target scope before interacting with the application, and the original foreground application is restored afterward.

## 17. Clipboard recovery (only when explicitly enabled)

Use a controlled failure that reaches the clipboard fallback.

1. Confirm the existing clipboard content is disposable.
2. Trigger recovery.
3. Test a successful clipboard write.
4. Test a clipboard write failure where possible.

Expected: paste is attempted only after a confirmed clipboard write; unrelated clipboard contents are never pasted as a fallback.

## 18. DPI and multi-monitor geometry

Run on:

- One monitor at 100% scaling.
- Mixed scaling such as 100% + 125% or 150%.
- The monitor containing the target application different from the monitor containing the orb.
- A display-layout change followed by another send.

Expected: orb position, compose click geometry, and target coordinates remain aligned; no systematic offset appears after moving between monitors.

## 19. Repeated-send / lifecycle stress

Perform a burst of 20–50 short sends with normal pauses and repeated open/collapse cycles.

Expected: no stale worker result overwrites a newer attempt, no target lease remains stuck after completion/failure, no retry draft from an older attempt leaks into a new compose, and memory/CPU behavior remains stable.

## 20. Diagnostic privacy check

Run:

```powershell
python tools/diagnose.py --preflight --json
python tools/validate_windows.py --json
```

Inspect the output and generated trace files.

Expected: identifiers, geometry, states, evidence scores, and booleans may be present, but raw window titles, message text, conversation names, input values, and clipboard contents must not be emitted.

## 21. Release-candidate gate

Before a milestone release, the applicable cases in the smoke report must all be PASS or explicitly BLOCKED with a documented reason. Any FAIL remains release-blocking until addressed.

The release source must include the completed `smoke-report.json`; the release workflow validates it with `python tools/smoke_report.py --validate smoke-report.json --require-complete` before installing release dependencies or building the executable. The report's environment snapshot must identify Windows, include the core runtime fields, and record the Git commit used for the test. The release workflow also verifies that this recorded commit is an ancestor of the tagged release source.

The repository's automated Windows CI must also be green: source compilation, the full unittest suite, and the PyInstaller executable build must all pass before tagging a release.
