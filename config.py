# Floating Bar — default tunable constants. User-adjustable preferences are persisted by floatingbar.settings.

import re

# --- Target discovery ------------------------------------------------------
# The Telegram Desktop window is located by PROCESS IMAGE NAME, not title:
# Telegram's title becomes the open chat's name (often containing no
# "Telegram" at all), so a title regex misses it constantly.
PROCESS_NAME_RE = re.compile(r"telegram(\.exe)?$", re.IGNORECASE)
# Fallback match on window title if the process name lookup fails for an
# exotic install (portable builds rename the exe):
TITLE_FALLBACK_RE = re.compile(r"^\s*Telegram\s*(Desktop)?\s*$", re.IGNORECASE)

# --- Geometry -------------------------------------------------------------
ORB_DIAMETER = 32
BAR_WIDTH = 340
BAR_HEIGHT = 40
DEFAULT_X = 120
DEFAULT_Y = 120

DRAG_THRESHOLD_PX = 5

# --- Transparency ---------------------------------------------------------
TRANSPARENT_KEY_COLOR = "#0a0a0a"
ORB_ALPHA = 0.45
BAR_ALPHA = 0.80
USE_WINDOW_ALPHA = True

# --- Colors ----------------------------------------------------------------
ORB_COLOR_READY = "#4a90e2"
ORB_COLOR_NOT_FOUND = "#9a9a9a"
ORB_COLOR_SENDING = "#e8b547"
ORB_COLOR_UNVERIFIED = "#f59e0b"   # sent path could not be confirmed
ORB_COLOR_OK = "#22c55e"
ORB_COLOR_ERROR = "#ef4444"
TEXT_COLOR = "#f0f0f0"
CURSOR_COLOR = "#f0f0f0"
ERROR_COLOR = "#ff6b6b"

# --- Hotkey ----------------------------------------------------------------
# Ctrl+Alt+Space summons the bar from any foreground application.
# Registration failure is non-fatal; the orb remains click-accessible.
HOTKEY_MODIFIERS = 0x0002 | 0x0001
HOTKEY_VIRTUAL_KEY = 0x20

# --- Timing ---------------------------------------------------------------
IDLE_COLLAPSE_MS = 4000
FOCUS_LOST_COLLAPSE_MS = 250
POSTED_ENTER_WAIT_MS = 180
POSTED_ENTER_RETRIES = 1
FOREGROUND_SETTLE_MS = 120
PASTE_SETTLE_MS = 60
FOREGROUND_RESTORE_MS = 80
FEEDBACK_TIMEOUT_MS = 5000

# --- Injection ------------------------------------------------------------
COMPOSE_CLICK_SETTLE_MS = 150
AUDIT_SETTLE_MS = 150
ALLOW_FOCUS_STEAL = False
ENTER_SEND_MODE = "enter"

# --- Misc -----------------------------------------------------------------
SINGLE_INSTANCE_MUTEX = "FloatingBar::AzamanLTD::single-instance"
CLIPBOARD_RETRIES = 3
CLIPBOARD_RETRY_DELAY_S = 0.05
