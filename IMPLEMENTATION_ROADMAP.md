# Floating Bar — master implementation roadmap

This is the project-level roadmap. `IMPLEMENTATION_NOTES.md` remains the detailed engineering record; this file answers “what exists, what is in progress, and what is next.”

## Product goal

Turn the Windows floating orb into a background-input layer:

`orb → background apps → app capability → target/control → type → submit → verify`

The app should let the user work in the foreground while sending/replying through selected background applications without stealing focus.

## Current state

### Completed foundation

- [x] Always-on-top orb/bar UI
- [x] Telegram Desktop background sending without normal foreground restoration
- [x] Exact Telegram HWND/PID leases and stale-target guards
- [x] UTF-16 `WM_CHAR` text delivery
- [x] Nested compose and Send-button evidence handling
- [x] Typed submission evidence and transaction lifecycle
- [x] Failed-send retry draft and explicit retry UX
- [x] Content-free background-window discovery
- [x] Hover application picker
- [x] Second-level app action popup
- [x] Telegram chat picker foundation
- [x] Generic background typing target with exact HWND/PID validation
- [x] Generic target structural probe and editable-control discovery
- [x] Generic retry preserves original HWND/PID scope and adapter identity
- [x] Structural candidate scoring without reading text/value content
- [x] Exact input-control pinning and revalidation for generic background sends
- [x] Bounded post-send scope/control liveness checks without message-content reads
- [x] Generic post-send target loss is surfaced as `verification-unavailable`, never as a retryable failure
- [x] Generic submit exceptions after text injection are also surfaced as `verification-unavailable`, never as automatic retries
- [x] Windows CI compile + regression suite + PyInstaller build
- [x] Release workflow separated from ordinary development pushes
- [x] Background picker can include minimized application windows
- [x] Minimized targets are allowed into structural probing; input discovery remains the safety gate
- [x] Content-free readiness reasons distinguish unavailable, no-input, and inspection-error states
- [x] User-facing background-target feedback maps readiness failures without exposing UI content
- [x] Telegram chat selection is protected by runtime/structural row identity, not only geometry/name
- [x] Telegram sends revalidate the selected chat before preflight when the user stays in the same window
- [x] Unknown background executables can enter the same generic Type pipeline; structural input discovery remains the final readiness gate
- [x] Global Ctrl+Alt+Space summon hotkey with silent conflict fallback and clean shutdown
- [x] Content-free Windows environment validation snapshot
- [x] Declarative real-Windows smoke matrix covering supported app families and reliability cases
- [x] Smoke report validation, result summaries, and reproducible desktop-test report generation
- [x] Session-only recent application targets with exact HWND/PID revalidation
- [x] Session-only recent conversation targets with runtime/structural row revalidation
- [x] Persistent pinned application/conversation targets with content-free stored identity and live-scope validation
- [x] Persistent user-authored quick replies with bounded CRUD storage and draft-only insertion

### Completed grouped milestone — Adapter Architecture

- [x] Central `app_adapters.py` registry for supported executables
- [x] Picker derives labels, capabilities, and actions from the registry
- [x] Production routing derives adapter identity from the registry
- [x] Adapter metadata defines target mode, submit mode, and verification mode
- [x] Adapter metadata explicitly declares conversation-attention capability
- [x] Tests cover aliases, capabilities, and adapter metadata
- [x] Adapter target factory separates per-app implementations from UI routing
- [x] Dedicated Terminal target rejects focused controls that are not structurally discovered as editable
- [x] Dedicated chat composer target rejects controls outside the structural Edit/Document inventory
- [x] Adapter evidence policy prevents unverified adapters from claiming `VERIFIED`
- [x] Telegram verification contract is explicitly bound to the Telegram adapter
- [x] Adapter-bound submission policy separates typing from submission semantics
- [x] Production generic targets bind the explicit adapter policy before sending
- [x] Generic adapter factory provides safe fallback Type capabilities for unknown executable names
- [x] Generic adapter verification hooks preserve the fail-closed evidence contract
- [x] WhatsApp has an explicit adapter-bound `compose-clear` verification contract
- [x] Discord has an explicit adapter-bound `compose-clear` verification contract
- [x] Slack has an explicit adapter-bound `compose-clear` verification contract
- [x] Teams has an explicit adapter-bound `compose-clear` verification contract
- [x] Terminal/CMD/PowerShell share an explicit terminal input-clear verification contract without reading command content
- [x] Verification evidence authorization recognizes only declared concrete adapter contracts
- [x] Verification registry rejects a concrete app from borrowing another app's verification contract
- [ ] Add app-specific verification implementations for terminal and app-specific chat semantics where shared contracts are insufficient

## Phase 2 — Finish the current UX and reliability layer

- [x] Make hover movement between orb → app list → action menu more forgiving
- [x] Show safe picker availability/action affordances instead of silent unsupported selection
- [x] Keep selected app identity visible in the active bar without exposing window titles
- [x] Add deterministic tests for picker hover state transitions where practical
- [x] Complete generic-app retry/recovery coverage for structurally pinned input controls
- [x] Guard delayed picker callbacks against stale app/chat selections
- [x] Keep minimized background applications eligible for selection while retaining structural target safety checks
- [x] Allow unknown background apps to expose a generic Type action before structural target probing
- [x] Add global keyboard summon without changing foreground-target safety
- [x] First-run mini-tutorial and clearer no-target/background-target feedback
- [x] Conversation-picker refresh and pagination for larger chat lists
- [x] Session recent targets and persistent pinning for common applications/conversations
- [x] Saved quick replies that insert drafts without automatically sending
- [x] Strong conversation identity is content-free when runtime/structural UI identity exists; visible names remain display-only labels

## Phase 3 — Real application adapters

### Telegram

- [x] Window discovery
- [x] Chat picker
- [x] Background selection
- [x] Safe send transaction
- [x] Retry and evidence lifecycle
- [x] Same-window chat-switch detection without message-content reads
- [x] UIA unread-badge attention detector with fail-closed contract
- [x] Unread chats surfaced ahead of current/ordinary chats in the short picker
- [ ] Validate against traces from multiple Telegram Desktop builds
- [ ] Build real desktop smoke validation

### Terminal

- [x] Discovery and adapter capability contract
- [x] Dedicated structural target adapter
- [x] Exact-scope binding
- [x] Exact-control revalidation for pinned sends
- [x] Prefer a discovered console control when focus is elsewhere
- [x] Explicit submission mode contract
- [x] Explicit console-control process coverage across Windows Terminal, Terminal Preview, conhost, and PowerShell Core aliases
- [x] Fail-closed post-send liveness handling and no automatic retry for unverified outcomes
- [x] Bounded input-control acceptance verification through value-length growth followed by clear, without command-content reads
- [ ] Real Windows validation across Windows Terminal/CMD/PowerShell versions and console-host variants
- [ ] App/version-specific retry behavior after a genuinely failed terminal send
- [ ] Semantic command-execution verification that does not depend on terminal content

### WhatsApp

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [x] Explicit Enter submission contract
- [x] Content-free `compose-clear` verification hook with pre-injection baseline
- [ ] Real Windows smoke validation across WhatsApp Desktop builds

### Discord

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [x] Explicit Enter submission contract
- [x] Content-free `compose-clear` verification hook with pre-injection baseline
- [ ] Server/channel/DM targeting model
- [ ] Real Windows smoke validation across Discord Desktop builds

### Slack

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [x] Explicit Enter submission contract
- [x] Content-free `compose-clear` verification hook with pre-injection baseline
- [ ] Conversation targeting refinements
- [ ] Real Windows smoke validation across Slack Desktop builds

### Microsoft Teams

- [x] Discovery and generic typing foundation
- [x] Adapter capability contract
- [x] Dedicated structural composer target
- [x] Generic conversation picker and background row selection
- [x] Explicit Enter submission contract
- [x] Content-free `compose-clear` verification hook with pre-injection baseline
- [ ] Conversation targeting refinements
- [ ] Real Windows smoke validation across Teams Desktop builds

### Generic background app

- [x] Process-level fallback adapter for unknown `.exe` names
- [x] Generic Type action in the hover picker
- [x] Exact HWND/PID scope binding
- [x] Structural editable-control discovery and scoring
- [x] Safe readiness feedback when no input control is available
- [ ] App-specific submit semantics when Enter is not sufficient
- [ ] App-specific verification

## Phase 4 — Target/control intelligence

The key transition is from “whatever control currently has focus” to “the correct input control for this application.”

- [x] Inspect UI Automation structure without reading message content
- [x] Identify editable controls by role/class/capability
- [x] Prefer composer-shaped controls over focused search/navigation controls where a composer is available
- [x] Support multiple candidate controls with deterministic structural scoring
- [x] Pin the selected control for the duration of a send
- [x] Abort safely when the control or process changes
- [x] Revalidate pinned control identity against HWND reuse
- [x] Allow responsive geometry changes without invalidating an otherwise stable control identity

## Phase 5 — Conversation intelligence

- [x] Identify useful/reply-needed chats without scraping message content when an explicit accessibility signal exists
- [x] Implement app-specific unread/reply-needed structural signals where an application exposes them safely
- [x] Keep chat selection content-free where possible
- [x] Refresh/revalidate rows immediately before background selection
- [x] Confirm the clicked conversation becomes selected before binding it for send-time use
- [x] Prefer UI Automation runtime identity when available; use structural control identity as a guarded fallback
- [x] Keep the currently selected conversation visible in the short picker window
- [x] Avoid treating visual ordering as conversation identity
- [x] Add explicit attention states (`unknown`, `selected`, `unread`, `relevant`) with fail-closed detector contracts
- [x] Surface proven attention states in the conversation picker without exposing message content
- [x] Explicitly report unsupported attention detection rather than implying unread state

## Phase 6 — Verification and reliability

Every adapter should eventually produce one of:

`verified | submitted-but-unverified | failed | blocked`

- [x] Central typed evidence model
- [x] Explicit `blocked` evidence and transaction lifecycle state for deliberate safety stops
- [x] Adapter-specific verification contract in the registry
- [x] Conservative evidence normalization that cannot upgrade unsupported adapters
- [x] Explicit submission policy for generic adapters
- [x] App-specific verification hook architecture for chat targets
- [x] WhatsApp content-free `compose-clear` verification with pre-injection baseline
- [x] Shared content-free `compose-clear` verification for Discord/Slack/Teams through the structural chat target
- [x] Explicit fail-closed handling for terminal submission outcomes without claiming command verification
- [x] Bounded terminal input-control acceptance verification without reading command content
- [x] Concrete per-adapter verification contract binding for Telegram, WhatsApp, Discord, Slack, Teams, Terminal, CMD, and PowerShell
- [ ] App-specific semantic verification for terminal and chat adapters where shared contracts are insufficient
- [x] Bounded post-send checks
- [x] Final content-free revalidation before `VERIFIED`: terminal control identity must remain stable after clear observation; chat verification also requires the selected conversation to remain unchanged
- [x] Verification evidence records an explicit proof scope so input acceptance is not confused with future semantic delivery/execution verification
- [x] Generic post-send target loss cannot become an automatic retry
- [x] Generic submit exceptions after text injection cannot become an automatic retry
- [x] Clear user feedback for blocked targets
- [x] Trace adapter, target, and verification stages without message content

## Phase 7 — Real Windows validation

- [x] Content-free Windows environment snapshot tooling, including per-monitor geometry/effective-DPI evidence
- [x] Declarative smoke matrix covering environment, fidelity, picker, Telegram, chat, terminal, and privacy cases
- [x] Machine-readable smoke report generation, validation, and critical-case environment evidence checks
- [x] Practical operator checklist for executing the real Windows smoke matrix
- [ ] Windows 10 real desktop smoke tests
- [ ] Windows 11 real desktop smoke tests
- [ ] Mixed-DPI/multi-monitor tests
- [ ] Minimized/background window tests
- [ ] Multiple-window tests per supported app
- [ ] App restart/process replacement tests
- [ ] Unicode/emoji/long-text tests
- [ ] Repeated-send tests
- [ ] App-version trace collection from real builds

## Phase 8 — Product release

- [ ] Final supported-application matrix after real desktop validation
- [x] Per-user Windows startup behavior
- [x] Packaging and clean upgrade path
- [x] Core user documentation and troubleshooting guidance
- [ ] Signed executable and installer packaging
- [x] On-demand release update notification using public release metadata
- [x] Lightweight settings UI for safe application preferences, including configurable summon hotkey
- [ ] Meaningful milestone release after real desktop validation

## Adoption/product track

These are productization items that should proceed alongside the reliability work rather than replacing it:

- [x] Global keyboard summon (`Ctrl+Alt+Space`) implemented
- [x] First-run mini-tutorial and clearer no-target/background-target feedback
- [x] Saved snippets / quick replies
- [x] Multiple pinned conversation/application targets

## Working rule

Implementation should proceed in grouped milestones, not isolated micro-commits. Each batch should move a user-visible capability or a major architectural boundary forward, add regression coverage, and finish with Windows CI validation before the next large feature batch.
