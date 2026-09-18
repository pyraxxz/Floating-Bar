# Real Windows Smoke-Test Checklist

This checklist is the human execution companion for the declarative smoke matrix in
`floatingbar/smoke_matrix.py`. It is intentionally content-free: testers must never
record message bodies, conversation previews, raw window titles, clipboard contents,
or command text in the report.

## 1. Test prerequisites

Run the checklist on the Windows machine that will produce the smoke report.

Record the environment through the existing tooling before testing:

```powershell
python tools/smoke_report.py --init smoke-report.json
```

Use a clean desktop session where possible. Install the supported desktop applications
for the cases being executed. For the release gate, the report must be generated from
the same source revision being validated.

Before beginning destructive/restart cases, make sure the operator can safely restart
the target applications and can recover the desktop if a test app becomes unresponsive.

## 2. Execution rules

For each case, record only:

- `PASS` when the documented behavior is observed.
- `FAIL` when the behavior is expected to work but does not.
- `BLOCKED` when the environment cannot exercise the case (for example, an application
  or required Windows configuration is unavailable).

Notes should describe observable structural behavior only: application, control type,
selection state, process/window replacement, verification state, or safe reason code.
Do not paste message text or raw window titles into notes.

A case is not PASS merely because the orb opened or an action returned without raising.
For send cases, verify the matrix's stated evidence behavior.

## 3. Environment and desktop safety

### env.launch — Launch, idle, collapse, and clean shutdown
Open Floating Bar, leave it idle, expand/collapse it, then shut it down normally.
Confirm there are no stuck always-on-top windows or background worker processes after exit.

### env.focus — Foreground application remains protected
Open a normal work application in the foreground. Use the orb and background picker.
Confirm the foreground application's focus/input remains unchanged during ordinary
background targeting and sending.

### env.dpi — Mixed-DPI and multi-monitor geometry
Use a setup with at least two monitors with different scaling where available. Move the
orb between monitors and exercise the background picker. Confirm picker geometry,
click targeting, and popup placement remain usable.

### env.minimized — Minimized background target is rejected or safely handled
Select an application that is minimized. Confirm it may appear as an open application,
but the target does not silently claim readiness or deliver input when the application
cannot expose a safe background input path.

### env.restart — Target process restart cannot reuse stale HWND/PID
Select a supported background target, restart the target process, then continue the
pending interaction. Confirm the old window/process identity is rejected.

### env.repeated — Repeated sends do not leak attempts, leases, or drafts
Perform several independent sends and at least one failed send followed by deliberate
retry. Confirm stale results do not overwrite newer attempts and old retry state does
not appear after a new target is selected.

## 4. Message fidelity

### text.unicode — Unicode, emoji, and surrogate-pair delivery
Use representative Unicode and emoji input. Confirm delivery is not corrupted and
the application remains responsive. Do not record the actual text in the report.

### text.whitespace — Intentional leading/trailing whitespace is preserved
Exercise text with intentional leading/trailing whitespace. Confirm it is delivered
unchanged while whitespace-only input is still ignored.

## 5. Picker and generic targeting

### picker.multiple — Multiple windows remain distinguishable without titles
Open multiple windows for supported applications where practical. Use the picker and
confirm selection stays tied to the chosen window without exposing raw window titles.

### picker.refresh — Conversation refresh/pagination preserves safe identity
Use WhatsApp, Discord, Slack, and Teams. Open a sufficiently large conversation list,
refresh/paginate, and confirm selected rows remain structurally stable rather than
being identified solely by visual position.

### generic.discovery — Generic structural input discovery gates readiness
Use an unknown text-capable application. Confirm the generic Type action appears and
the target becomes ready only when a structurally discovered editable control exists.

### generic.blocked — Generic app with no safe input is blocked without injection
Use an application that exposes no safe editable control. Confirm the UI explains that
no safe typing control is available and no input is injected.

## 6. Telegram

### telegram.send — Background send through selected Telegram chat
Select a Telegram chat from the background picker and send a message without deliberately
foregrounding Telegram. Confirm the transaction reaches the selected chat and the
verification state is reported honestly.

### telegram.multiwindow — Exact Telegram window selection is preserved
Open multiple Telegram windows if the desktop build permits it. Select one and confirm
the send remains bound to that exact top-level window.

### telegram.restart — Telegram restart blocks stale transaction
Start a target/send transaction, restart Telegram, and continue the transaction.
The stale HWND/PID must be rejected rather than retargeting another Telegram window.

### telegram.context — Chat-context drift is blocked when a non-content anchor changes
Change the selected Telegram UI state between preflight/selection and the send attempt
without relying on message contents. Confirm the transaction blocks when the available
non-content context anchor changes.

### telegram.unverified — Uncertain submission is surfaced without automatic retry
Exercise a case where send completion cannot be reliably confirmed. Confirm the UI
reports an uncertain/submitted-but-unverified result and does not automatically resend.

### telegram.retry — Genuine failure preserves an explicit, non-automatic retry
Cause a genuine failed send, verify the draft is preserved for deliberate retry, and
confirm retry is user-initiated rather than automatic.

## 7. Chat applications

### chat.whatsapp — WhatsApp conversation selection, compose, send, and clear verification
Select a conversation, target the structurally discovered composer, send, and confirm
the compose-clear verification behavior where supported by the build.

### chat.discord — Discord conversation targeting, compose, send, and clear verification
Exercise the same flow. Confirm the selected structural conversation remains the
target and the composer verification does not read message content.

### chat.slack — Slack conversation targeting, compose, send, and clear verification
Exercise the same flow. Pay particular attention to search/navigation controls versus
the actual composer.

### chat.teams — Teams conversation targeting, compose, send, and clear verification
Exercise the same flow and confirm the correct composer is selected when multiple
editable controls exist.

### chat.restart — Chat-app process replacement invalidates the active target
Restart the selected chat application during targeting or sending. Confirm the old
process/window/control identity is not reused.

## 8. Terminal

### terminal.discovery — Terminal structural target discovery when focus is elsewhere
Use Windows Terminal, Command Prompt, and PowerShell. Keep focus in another application
and confirm the structural terminal input can still be discovered before sending.

### terminal.submit — Terminal Enter submission reaches the pinned control
Send a benign terminal input through the pinned structural control and confirm Enter
is posted to the exact control/process scope.

### terminal.acceptance.wt — Windows Terminal stable input-clear verification
Verify the pinned input's value length grows after injection and returns to zero after
submission. Do not inspect or record the command content.

### terminal.acceptance.preview — Windows Terminal Preview input-clear verification
Repeat the same acceptance check on Windows Terminal Preview.

### terminal.acceptance.conhost — conhost/CMD input-clear verification
Repeat on classic console-host/CMD.

### terminal.acceptance.pwsh — PowerShell Core input-clear verification
Repeat on PowerShell Core.

### terminal.uncertain — Terminal outcome remains submitted-but-unverified when acceptance is unproven
Exercise a build/control where acceptance cannot be proven. Confirm the result remains
submitted-but-unverified rather than being upgraded to VERIFIED or retried automatically.

### terminal.restart — Terminal process replacement blocks the stale target
Restart the terminal/console process after targeting and confirm the stale control is
rejected.

## 9. Privacy and diagnostics

### privacy.trace — Diagnostics and traces contain no message or conversation content
Run the relevant diagnostic/send paths and inspect trace/log output. Confirm logs contain
only structural/boolean evidence such as lengths, geometry, runtime IDs, stages, process
identity, and safe reason codes.

### privacy.retry — Retry state remains session-only and content-free outside the active draft
Confirm retry metadata stores only the minimum session identity needed to rebind safely.
Do not place the draft text or conversation content into smoke notes or persistent files.

## 10. Final report validation

After all applicable cases are exercised:

```powershell
python tools/smoke_report.py --validate smoke-report.json --require-complete
```

The validation must reject missing cases, stale matrix fingerprints, malformed schema,
duplicate/unknown IDs, and invalid result values.

For release use, also confirm that the report's recorded source commit is an ancestor
of the exact release tag commit. The release workflow performs that ancestry check before
publication.

## 11. Minimum release-quality execution set

At minimum, a release candidate should have PASS evidence for all critical cases,
including:

`env.launch`, `env.focus`, `env.dpi`, `env.restart`, `telegram.send`,
`telegram.multiwindow`, `telegram.restart`, `telegram.context`,
`telegram.unverified`, `terminal.submit`, all four `terminal.acceptance.*` cases,
`terminal.uncertain`, and `privacy.trace`.

BLOCKED cases must identify the environmental reason. A BLOCKED result is not equivalent
to a PASS result.

## 12. Evidence discipline

The smoke report is an execution record, not a transcript. Notes should stay concise and
content-free. Examples of acceptable evidence include:

- "Selected row remained selected after refresh."
- "Old HWND/PID rejected after process restart."
- "Composer value length increased, then returned to zero."
- "Result surfaced as submitted-but-unverified."
- "Diagnostic output contained no message-content fields."

Do not write the actual message, command, conversation preview, raw title, or clipboard
contents into the report.
