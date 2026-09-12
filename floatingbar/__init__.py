"""Floating Bar — a translucent always-on-top orb that relays typed text
into the currently open Telegram Desktop chat.

Package layout:
    winapi          raw Win32 ctypes layer (window discovery, message posting)
    clipboard_guard full-fidelity clipboard save/restore
    target          Telegram window + compose-box discovery (UI Automation)
    injector        established cascading send strategy
    hardening       v0.1.8 safety layer over the established injector
    overlay         the Tk orb/bar UI
"""

__version__ = "0.1.8"
