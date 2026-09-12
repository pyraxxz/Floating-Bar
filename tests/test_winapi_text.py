import unittest

from floatingbar.winapi import _utf16_code_units


class WinapiTextTests(unittest.TestCase):
    def test_bmp_text_maps_to_one_code_unit_per_character(self):
        self.assertEqual(_utf16_code_units("AbΩ"), [0x41, 0x62, 0x03A9])

    def test_astral_unicode_maps_to_surrogate_pair(self):
        units = _utf16_code_units("A😀B")
        self.assertEqual(units[0], 0x41)
        self.assertEqual(units[1:3], [0xD83D, 0xDE00])
        self.assertEqual(units[3], 0x42)

    def test_empty_text_posts_no_units(self):
        self.assertEqual(_utf16_code_units(""), [])


if __name__ == "__main__":
    unittest.main()
