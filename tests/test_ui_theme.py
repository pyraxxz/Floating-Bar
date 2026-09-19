import unittest

from floatingbar import ui_theme


class ThemeTests(unittest.TestCase):
    def test_palette_is_explicit_and_stable(self):
        self.assertEqual(ui_theme.SURFACE, "#18181b")
        self.assertEqual(ui_theme.ACCENT, "#60a5fa")
        self.assertNotEqual(ui_theme.TEXT, ui_theme.TEXT_DIM)

    def test_place_popup_near_prefers_left_when_right_side_is_offscreen(self):
        class FakeOwner:
            def winfo_rootx(self): return 900
            def winfo_rooty(self): return 40
            def winfo_width(self): return 100
            def winfo_height(self): return 40
            def winfo_screenwidth(self): return 1000
            def winfo_screenheight(self): return 700

        class FakePopup:
            def update_idletasks(self): pass

        x, y = ui_theme.place_popup_near(FakeOwner(), FakePopup(), 180, 120, gap=8)
        self.assertLessEqual(x + 180, 900)
        self.assertEqual(y, 40)

    def test_place_popup_near_clamps_bottom_edge(self):
        class FakeOwner:
            def winfo_rootx(self): return 100
            def winfo_rooty(self): return 650
            def winfo_width(self): return 32
            def winfo_height(self): return 32
            def winfo_screenwidth(self): return 1280
            def winfo_screenheight(self): return 720

        class FakePopup:
            def update_idletasks(self): pass

        x, y = ui_theme.place_popup_near(FakeOwner(), FakePopup(), 180, 120)
        self.assertEqual(x, 140)
        self.assertEqual(y, 592)


if __name__ == "__main__":
    unittest.main()

    def test_place_popup_near_uses_negative_virtual_desktop_origin(self):
        class FakeOwner:
            def winfo_rootx(self): return -600
            def winfo_rooty(self): return 80
            def winfo_width(self): return 40
            def winfo_height(self): return 40
            def winfo_vrootx(self): return -1280
            def winfo_vrooty(self): return 0
            def winfo_vrootwidth(self): return 2560
            def winfo_vrootheight(self): return 1440

        class FakePopup:
            def update_idletasks(self): pass

        x, y = ui_theme.place_popup_near(FakeOwner(), FakePopup(), 220, 120, gap=8)
        self.assertEqual(x, -852)
        self.assertEqual(y, 80)
