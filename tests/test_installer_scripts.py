import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class InstallerScriptTests(unittest.TestCase):
    def test_uninstaller_uses_the_same_start_menu_shortcut_location_as_installer(self) -> None:
        installer = (
            REPO_ROOT / "installer" / "Install-FloatingBar.ps1"
        ).read_text(encoding="utf-8")
        uninstaller = (
            REPO_ROOT / "installer" / "Uninstall-FloatingBar.ps1"
        ).read_text(encoding="utf-8")

        expected = 'Microsoft\\Windows\\Start Menu\\Programs\\Floating Bar.lnk'
        self.assertIn(expected, installer)
        self.assertIn(expected, uninstaller)

    def test_uninstaller_shortcut_path_is_not_a_concatenated_literal(self) -> None:
        uninstaller = (
            REPO_ROOT / "installer" / "Uninstall-FloatingBar.ps1"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            '"MicrosoftWindowsStart MenuProgramsFloating Bar.lnk"',
            uninstaller,
        )

    def test_installer_preserves_the_user_data_location(self) -> None:
        installer = (
            REPO_ROOT / "installer" / "Install-FloatingBar.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn('%APPDATA%\\FloatingBar', installer)
        self.assertIn('preserved', installer.casefold())


if __name__ == "__main__":
    unittest.main()
