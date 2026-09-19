import unittest

from floatingbar.overlay import OrbRelayWindow
from floatingbar import ui_theme


class _FakeCanvas:
    def __init__(self):
        self.calls = []

    def itemconfig(self, item, **kwargs):
        self.calls.append((item, kwargs))


class OrbVisualTests(unittest.TestCase):
    def _window(self):
        window = object.__new__(OrbRelayWindow)
        window.orb = _FakeCanvas()
        window.orb_ring = "ring"
        window.orb_dot = "dot"
        window._orb_hovered = False
        window._orb_pressed = False
        return window

    def test_ring_is_hidden_when_not_hovered(self):
        window = self._window()
        window._set_orb_ring()
        self.assertEqual(window.orb.calls[-1], ("ring", {"state": "hidden"}))

    def test_hover_shows_accent_ring_without_changing_dot(self):
        window = self._window()
        window._on_orb_enter()
        self.assertEqual(window.orb.calls[-1][0], "ring")
        self.assertEqual(window.orb.calls[-1][1]["state"], "normal")

    def test_press_uses_stronger_ring_then_release_restores_hover_state(self):
        window = self._window()
        window._on_orb_enter()
        window._on_orb_press()
        self.assertEqual(window.orb.calls[-1][1]["outline"], "#ffffff")

        window._on_orb_release()
        self.assertEqual(window.orb.calls[-1][1]["outline"], "#93c5fd")

    def test_leave_hides_ring(self):
        window = self._window()
        window._on_orb_enter()
        window._on_orb_leave()
        self.assertEqual(window.orb.calls[-1], ("ring", {"state": "hidden"}))


if __name__ == "__main__":
    unittest.main()
