# Floating Bar — Windows / Telegram Smoke-Test Protocol

This checklist is the manual validation gate for real Windows desktop behavior. The automated suite covers deterministic logic and mocked Win32/UIA boundaries; this document covers the parts that require a real Telegram Desktop session.

## Test environment record

Record these before a run:

- Windows version/build:
- Telegram Desktop version/build:
- Floating Bar commit SHA:
- Display count:
- Display scaling per monitor:
- `ENTER_SEND_MODE`:
- `ALLOW_FOCUS_STEAL`:
- Result: PASS / FAIL / BLOCKED

Do not record message content, chat names, screenshots containing private conversations, or clipboard contents in the repository.

## 1. Clean launch and idle behavior

1. Start Floating Bar with Telegram already running.
2. Confirm the orb appears, stays always-on-top, and does not steal focus.
3. Open the orb into the bar.
4. Confirm the previously focused application remains the intended restore target.
5. Leave the bar idle long enough for the normal collapse timer to fire.
6. Confirm it returns to the orb without opening another window.

Expected: no visible Telegram activation, no extra window, and no unexpected focus movement.

## 2. Basic invisible send

1. Open a Telegram chat with a clearly identifiable non-generic title.
2. Focus a different application before opening the orb.
3. Open Floating Bar, type a short test message, and press Enter.
4. Confirm the message arrives in the intended Telegram chat.
5. Confirm the previously focused application is restored if Telegram briefly becomes foreground.
6. Repeat at least five times.

Expected: all sends land in the intended chat; no duplicate sends occur; Floating Bar remains usable after each send.

## 3. Unicode and whitespace fidelity

Use separate sends containing:

- BMP Unicode text.
- Emoji and other astral Unicode characters.
- Leading whitespace that is intentionally meaningful.
- Trailing whitespace that is intentionally meaningful.
- A whitespace-only input.

Expected: meaningful whitespace and emoji survive unchanged; whitespace-only input is ignored without starting a send transaction.

## 4. Multiple Telegram windows

1. Open two Telegram windows or otherwise create two distinct top-level Telegram targets if the current Telegram build supports it.
2. Put chat A in one window and chat B in the other.
3. Focus window A before opening Floating Bar and send.
4. Switch to window B and send again.
5. Repeat while Floating Bar is opened from a non-Telegram application.

Expected: the exact foreground Telegram window is preferred when it is a valid target; a later rescan must not silently retarget an active transaction to the other Telegram window.

## 5. Chat-context change during preparation

For a chat whose window title contains useful non-generic context:

1. Start opening/preparing a send.
2. Switch the Telegram conversation while the preflight/UIA discovery window is active.
3. Complete the send attempt.

Expected: when the captured non-content context changes, the transaction is blocked rather than sending into the newly selected conversation.

## 6. Generic Telegram title / degraded context

Use a Telegram state where the top-level title resolves only to a generic title such as `Telegram` or `Telegram Desktop`.

1. Run the normal preflight/diagnostic path.
2. Confirm the structural compose anchor is captured when available.
3. Switch/recreate the compose control and attempt a send.

Expected: the application does not claim exact chat identity when the available non-content anchors cannot establish it. A structural compose change should block the send when it invalidates the captured anchor.

## 7. Telegram restart / stale target

1. Prepare a send with Telegram running.
2. Restart Telegram before the submission stage completes.
3. Attempt to complete the send.

Expected: the original HWND/PID scope is rejected; the application must not continue against the replacement Telegram window. Retry only after a fresh user action.

## 8. Minimized Telegram

1. Minimize Telegram.
2. Open Floating Bar and attempt a send.
3. Restore Telegram and retry explicitly.

Expected: the minimized attempt is rejected honestly. The app must not report success merely because a post operation was attempted.

## 9. Nested compose / search-field protection

1. Leave a searchable Telegram field populated where the UI exposes both search and compose `Edit` controls.
2. Send a message from the chat.
3. Repeat with the search field focused before opening Floating Bar.

Expected: the compose field wins over an unrelated pre-filled search field; an ambiguous field must not cause a click on a voice/mic control.

## 10. Send-button evidence

Test at least these states:

- Explicitly named Send button visible.
- Send button temporarily absent, requiring Enter fallback.
- Voice/record/microphone control visible.
- Unnamed or ambiguous button near the compose area.
- Disabled button candidate.

Expected: safe explicit Send evidence can be clicked; voice/mic controls are never clicked; ambiguous evidence falls back conservatively; disabled controls are not selected.

## 11. Submission verification and duplicate protection

1. Send repeatedly under a normal network/UI responsiveness profile.
2. Observe cases where Telegram clears the compose immediately and where it clears after a noticeable delay.
3. Include one case where UIA read-back becomes temporarily unavailable.

Expected: delayed compose clearing can still be classified as verified; an unverified-but-submitted result is surfaced as uncertain rather than offered for automatic retry; the app never sends a second message solely because verification was slow.

## 12. Failed-send retry UX

1. Force a genuine failed send condition without changing the original Telegram target.
2. Confirm the draft is retained only for the current process session.
3. Open the context menu and choose `Retry failed draft`.
4. Confirm the original target context is restored/validated.
5. Verify that the retry does not submit until Enter is pressed.
6. Start typing a replacement instead.

Expected: failed text is recoverable, retry is explicit, no automatic duplicate is created, and typing a replacement clears the old retry context.

## 13. Focus-steal recovery (only when explicitly enabled)

Run once with `ALLOW_FOCUS_STEAL=False` and once in a controlled test build with it enabled.

Expected with the default disabled setting: a failed invisible send does not steal foreground focus.

Expected when enabled: each recovery action revalidates the original Telegram scope before interacting with Telegram, and the original foreground application is restored afterward.

## 14. Clipboard recovery (only when explicitly enabled)

Use a controlled failure that reaches the clipboard fallback.

1. Confirm the user's existing clipboard content is something disposable.
2. Trigger recovery.
3. Test a successful clipboard write.
4. Test a simulated/observed clipboard write failure where possible.

Expected: paste is attempted only after a confirmed clipboard write; unrelated clipboard contents must never be pasted as a fallback.

## 15. DPI and multi-monitor geometry

Run on:

- One monitor at 100% scaling.
- Mixed scaling such as 100% + 125% or 150%.
- The monitor containing Telegram different from the monitor containing the orb.
- A display-layout change followed by another send.

Expected: the orb position, compose click geometry, and Send-button coordinates remain aligned; no systematic offset appears after moving between monitors.

## 16. Repeated-send / lifecycle stress

Perform a burst of 20–50 short sends with normal pauses and several sends after opening/collapsing the orb repeatedly.

Expected: no stale worker result overwrites a newer attempt, no target lease remains stuck after completion/failure, no retry draft from an older attempt leaks into a new compose, and memory/CPU behavior remains stable.

## 17. Diagnostic privacy check

Run:

```powershell
python tools/diagnose.py --preflight --json
```

Inspect the output and any generated trace files.

Expected: identifiers, geometry, states, evidence scores, and booleans may be present, but raw Telegram titles, message text, and clipboard contents must not be emitted.

## 18. Release-candidate gate

Before a milestone release, all applicable sections above must be PASS on at least one real supported Windows environment. Record any Telegram-build-specific failures as follow-up engineering work rather than silently accepting them.

The repository's automated Windows CI must also be green: source compilation, the full unittest suite, and the PyInstaller executable build must all pass before tagging a release.
