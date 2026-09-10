# Floating Bar — all tunable constants in one place.
# Edit these, restart the app. No settings UI by design (v1).

import re

# --- Target discovery ------------------------------------------------------
# The Telegram Desktop window is located by PROCESS IMAGE NAME, not title:
# Telegram's title becomes the open chat's name (often containing no
# "Telegram" at all), so a title regex misses it constantly.
PROCESS_NAME_RE = re.compile(r"telegram(\.exe)?$", re.IGNORECASE)
# Fallback match on window title if the process name lookup fails for an
# exotic install (portable builds renam the exe):
TITLE_FALLBACK_RE = re.compile(r"^\s*Telegram\s*(Desktop)?\s*$", re.IGNORECASE)

# --- Geometry -------------------------------------------------------------
ORB_DIAMETER = 32          # px, idle dot
BAR_WIDTH = 340            # px, expanded input
BAR_HEIGHT = 40            # px, expanded input (10px grip band top+bottom)
DEFAULT_X = 120            # first-run position
DEFAULT_Y = 120

DRAG_THRESHOLD_PX = 5      # press must move at least this far to count as drag

# --- Transparency ---------------------------------------------------------
TRANSPARENT_KEY_COLOR = "#0a0a0a"   # must never appear as a real UI color
ORB_ALPHA = 0.45           # idle dot translucency
BAR_ALPHA = 0.80           # input translucency while typing
# If your Tk build mishandles -alpha combined with -transparentcolor (you
# would see a solid dark box instead of transparency), set this to False —
# the app then relies on the color key alone and still works.
USE_WINDOW_ALPHA = True

# --- Colors (drawn on the colorkey canvas; pick vivid, non-#0a0a0a) --------
ORB_COLOR_READY = "#4a90e2"       # blue — Telegram located
ORB_COLOR_NOT_FOUND = "#9a9a9a"   # gray — Telegram not found yet
ORB_COLOR_SENDING = "#e8b547"     # amber — injection in flight
ORB_COLOR_OK = "#22c55e"          # green flash — sent
ORB_COLOR_ERROR = "#ef4444"       # red flash — failed
TEXT_COLOR = "#f0f0f0"
CURSOR_COLOR = "#f0f0f0"
ERROR_COLOR = "#ff6b6b"

# --- Timing ---------------------------------------------------------------
IDLE_COLLAPSE_MS = 4000        # collapse the bar after this much idle
FOCUS_LOST_COLLAPSE_MS = 250   # collapse soon after the bar loses focus
POSTED_ENTER_WAIT_MS = 180     # wait after a posted Enter before verifying
POSTED_ENTER_RETRIES = 1       # re-post the Enter once if it didn't take
FOREGROUND_SETTLE_MS = 120     # focus-steal path: settle after raise
PASTE_SETTLE_MS = 60           # focus-steal path: settle after paste
FOREGROUND_RESTORE_MS = 80     # focus-steal path: delay before restore

# --- Injection ------------------------------------------------------------
# Telegram has a setting: "Send on Enter" vs "Send on Ctrl+Enter".
# Set to "ctrl+enter" if you use the Ctrl+Enter variant.
ENTER_SEND_MODE = "enter"

# --- Misc -----------------------------------------------------------------
SINGLE_INSTANCE_MUTEX = "FloatingBar::AzamanLTD::single-instance"
CLIPBOARD_RETRIES = 3         # open/restore attempts (clipboard can be busy)
CLIPBOARD_RETRY_DELAY_S = 0.05
