# Floating Bar desktop smoke test

This checklist is for real Windows validation of the background-input workflow. It does not require sending private message content into logs; use harmless test text only when a live send is explicitly required.

## Before starting

- Windows 10 or 11.
- Floating Bar launched normally, not elevated.
- For chat adapters, launch the desktop application normally, not elevated.
- For mixed-DPI testing, use the real monitor/scaling configuration where the problem occurs.

## 1. Read-only preflight — Telegram baseline

With Telegram open to a chat, run from the repository root:

```bat
python tools/diagnose.py --preflight
```

For machine-readable support output, use:

```bat
python tools/diagnose.py --preflight --json
```

The JSON form is content-free and carries a stable `schema_version` plus readiness state. The key safety fields are `status`, `context_protection`, target HWND/PID, focus ownership, compose geometry, submission path, Send evidence score, context-guard state, and safe diagnostic reasons. It never includes Telegram's raw title, message text, or clipboard contents.

`context_protection` has three meanings:

- `guarded`: a non-content context anchor was captured and remained stable through preflight.
- `degraded`: no useful non-content context anchor was exposed, so the transaction relies on HWND/PID protection rather than claiming exact chat protection.
- `blocked`: a safety-critical inspection failed or another hard prerequisite was not met.

Expected hard prerequisites:

- `ready=True`.
- A non-zero Telegram HWND/PID.
- `minimized=False`.
- `scope_stable=True`.
- A usable compose click point.
- Either a safe Send candidate or an explicit Enter-fallback note.

The reported status should normally be `ready`. `ready-with-degraded-context` is acceptable only when Telegram exposes no useful content-free context anchor. When a non-generic title is available, the title is fingerprinted. When the title is generic, an available compose-control runtime ID can still provide structural context protection without reading message content.

A safety-critical failure while re-inspecting an anchor is **not** treated as degraded; it must produce `status=blocked` so the send path fails closed instead of guessing that the context is still safe.

The command must not change foreground focus, type, click, or touch the clipboard.

## 2. Basic invisible send — Telegram

Open Telegram to a harmless test chat. Click the Floating Bar orb, enter a short test message, and press Enter.

Expected:

- Telegram does not need to be raised to the foreground.
- The text lands in the intended chat.
- The orb reports green only when submission is actually verified.
- An unverified result is amber and does not become an automatic retry.

## 3. Telegram multiple-window target binding

Open two Telegram windows with different chats. Put window A in the foreground, open the orb, then send.

Expected: window A receives the message.

Repeat with window B.

Expected: window B receives the message.

Then start with window A selected and, before pressing Enter, make window B the better/default Telegram discovery candidate.

Expected: the send remains bound to the preflight-selected window A or is refused safely; it must not silently retarget B.

## 4. Telegram restart protection

Open the orb, then restart Telegram before pressing Enter.

Expected: the send is refused safely rather than targeting the new Telegram window accidentally. The failed text should be recoverable through the retry flow.

## 5. Telegram chat-switch protection

Open the orb while Telegram chat A is active. Switch Telegram to chat B before pressing Enter.

Expected when Telegram exposes a useful changing title: the send is refused safely because the title fingerprint changes.

When Telegram exposes only a generic title, the test should check whether a compose-control runtime ID is available. If it is available, replacing that structural compose control should also cause a safe refusal. If neither title nor compose runtime ID is available, the system must explicitly report degraded context protection and rely only on the HWND/PID transaction guard rather than claiming exact chat protection.

## 6. Shared chat-app smoke matrix — WhatsApp, Discord, Slack, Teams

For each supported chat application:

1. Open one conversation with a composer visible.
2. Open Floating Bar without bringing the chat application to the foreground.
3. Select the application from the background picker and choose **Chats**.
4. Select the intended conversation from the short structural picker.
5. Send a harmless short message.
6. Repeat while a search/navigation field is focused in the target application.

Expected:

- The picker identifies the application without exposing window titles.
- The conversation picker operates from structural UI Automation identity rather than message bodies/previews.
- The composer target prefers an actual Edit/Document composer over an unrelated search/navigation field.
- Enter is used according to the adapter submission policy.
- A `compose-clear` verification path becomes green only when the composer is observed non-empty after injection and then empty after submission.
- An unreadable baseline, target replacement, or missing composer evidence fails closed and never becomes a false verified result.
- A verified result does not expose message content in trace output.

Real Windows validation is still required per application because UI Automation trees and composer behavior can differ between desktop builds.

## 7. Terminal / console smoke matrix

Run the same background-input workflow against Windows Terminal, Terminal Preview, conhost/Command Prompt, PowerShell, and PowerShell Core where available.

Expected:

- The picker recognizes the configured executable aliases.
- The target chooses a structurally discovered editable console control even when another control owns focus.
- The send remains bound to the exact console window/process and pinned control.
- Enter submission follows the explicit terminal adapter policy.
- A successful post-send liveness check does **not** claim that the command was executed; terminal outcomes remain submitted-but-unverified unless a future non-content acceptance signal is implemented.
- Window/process replacement during or immediately after submission produces `verification-unavailable` and never automatic retry.
- A genuinely failed send remains eligible for deliberate retry only when the failure evidence is explicit and the original target is still safely rebindable.

Real terminal validation must include both ordinary foreground use and background use behind another application.

## 8. Failed-send retry

Cause a harmless failed send in a supported target, then use the orb's right-click menu and choose **Retry failed draft**.

Expected:

- The draft is restored and selected.
- Nothing is sent automatically.
- Pressing Enter performs the deliberate retry.
- If the original target context changed, the retry is blocked until the intended context is restored.
- If the original window/process no longer exists, the replacement window must not be used automatically.
- An uncertain/unverified outcome is not offered as an automatic retry because the message may already exist in the target application.

## 9. Send-button safety — Telegram

Use the diagnostic against a chat where the compose row exposes multiple buttons.

Expected:

- A button named or identified as Send can be selected.
- Voice/record/microphone/audio controls are never selected as Send.
- A named unrelated control such as Attach/Emoji is rejected even when its geometry looks plausible.
- A weak unnamed icon falls through to Enter rather than being clicked.
- The reported Send evidence score reflects the selected candidate's semantic and geometric evidence.

## 10. Unverified result

Test a target state where the injector can submit but cannot read back enough evidence to confirm the result.

Expected: amber/unverified feedback, no automatic retry, and no false green success.

## 11. Mixed DPI / multiple monitors

Repeat the Telegram and at least one non-Telegram background send with Floating Bar on a monitor whose scaling differs from the target application's monitor.

Expected: the selected input lands correctly and no obvious coordinate drift occurs.

## 12. Emoji, long text, and whitespace

Use harmless test text containing:

- an emoji such as `🙂`;
- intentional leading/trailing spaces;
- a longer message that exercises the full injection path.

Expected: the emoji remains intact, intentional whitespace is preserved, and the send lifecycle remains stable.

## 13. Minimized/background windows

For each supported app that is expected to tolerate a minimized or covered window, repeat structural discovery and selection with the app behind another window and then with it minimized.

Expected:

- Covered/background windows remain eligible where their structural controls can be discovered safely.
- A target that cannot be safely interacted with is reported as unavailable/no-input rather than guessed.
- Telegram remains subject to its specific non-minimized requirement.

## 14. App restart / process replacement

Start a send, then restart or replace the target application before submission completes.

Expected: the transaction aborts or becomes verification-unavailable without silently switching to a replacement HWND/PID.

## 15. Opt-in recovery safety

Only when `ALLOW_FOCUS_STEAL` is explicitly enabled, exercise a harmless failure that enters the recovery path.

Expected:

- Scope is checked before each critical foreground/focus/keypress action.
- If the target is replaced during recovery, the recovery stops rather than continuing against the replacement window.
- Clipboard recovery refuses to paste when the clipboard write itself fails.
- The user's prior foreground window is restored after a recovery attempt.

## 16. Trace collection

After any failure, open the trace folder from the orb's right-click menu. Share `trace.log` only after confirming it contains no message content; the application is designed to log lengths, geometry, identifiers, stage names, scores, and booleans rather than message text.

## Milestone acceptance

Do not create a new public release solely because one test passes. A release milestone should require the accumulated automated suite to remain green, the Windows executable to build successfully, and successful real-desktop smoke testing across the scenarios relevant to that milestone.

The next public **v0.2.0 reliability milestone** is intended to require:

1. Windows CI green on the exact release source.
2. Read-only Telegram preflight works without changing focus or touching content.
3. Production sends remain bound to the selected Telegram HWND/PID.
4. Conversation context protection behaves conservatively when Telegram exposes a useful title or compose runtime anchor, and degrades safely when neither is available.
5. Send-button selection rejects voice/mic and unrelated named controls.
6. Shared compose-clear verification is exercised against real Windows builds of WhatsApp, Discord, Slack, and Teams.
7. Terminal background typing is validated across the supported console process aliases without falsely claiming command execution.
8. Restart, retry, and opt-in recovery paths stop safely on target replacement.
9. Mixed-DPI, multiple-window, background/minimized-state, Unicode, and repeated-send cases relevant to the supported matrix are exercised.
