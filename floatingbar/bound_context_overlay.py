"""Production entry point with the background-app hover picker.

Target binding and the Telegram transaction lifecycle remain owned by the
context-aware parent. This subclass only adds process-level discovery UI and
passes an exact HWND through to the existing safe Telegram path.
"""

from .context_overlay import OrbRelayWindow as _ContextOrbRelayWindow
from .background_picker import BackgroundAppPicker, PickerItem
from .background_windows import enumerate_background_windows


class OrbRelayWindow(_ContextOrbRelayWindow):
    """Production overlay with title-free background-app discovery."""

    def __init__(self):
        super().__init__()
        self._background_picker = BackgroundAppPicker(
            self,
            refresh=lambda: enumerate_background_windows(
                exclude_hwnds={self.winfo_id()},
            ),
            on_select=self._select_background_window,
        )
        self._background_picker.bind(self.orb)

    def _select_background_window(self, item: PickerItem) -> None:
        """Adopt only an actionable picker selection; never foreground it."""
        if not item.actionable or not item.hwnd or not item.pid:
            return
        self._work_hwnd = item.hwnd
        self._update_status()
        if self._state != "bar" and not self._sending:
            self._show_bar()


__all__ = ["OrbRelayWindow"]
