import unittest
from unittest.mock import patch

from floatingbar import startup


class _Key:
    def __init__(self, values):
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _FakeWinreg:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def CreateKey(self, _root, _path):
        return _Key(self.values)

    def OpenKey(self, _root, _path, _reserved, _access):
        if "FloatingBar" not in self.values:
            raise FileNotFoundError
        return _Key(self.values)

    def QueryValueEx(self, _key, _name):
        if "FloatingBar" not in self.values:
            raise FileNotFoundError
        return self.values["FloatingBar"], self.REG_SZ

    def SetValueEx(self, _key, name, _reserved, _kind, value):
        self.values[name] = value

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


class StartupTests(unittest.TestCase):
    def test_frozen_command_targets_executable_only(self):
        command = startup.startup_command(
            executable=r"C:\Program Files\Floating Bar\FloatingBar.exe",
            script=r"C:\src\main.py",
            frozen=True,
        )
        self.assertIn("FloatingBar.exe", command)
        self.assertNotIn("main.py", command)

    def test_source_command_targets_interpreter_and_script(self):
        command = startup.startup_command(
            executable=r"C:\Python\python.exe",
            script=r"C:\src\main.py",
            frozen=False,
        )
        self.assertIn("python.exe", command)
        self.assertIn("main.py", command)

    def test_startup_registration_is_user_scoped_and_reversible(self):
        fake = _FakeWinreg()
        with patch.object(startup.sys, "platform", "win32"), patch.object(startup, "winreg", fake),              patch.object(startup, "startup_command", return_value='"FloatingBar.exe"'):
            self.assertFalse(startup.is_startup_enabled())
            self.assertTrue(startup.set_startup_enabled(True))
            self.assertTrue(startup.is_startup_enabled())
            self.assertTrue(startup.set_startup_enabled(False))
            self.assertFalse(startup.is_startup_enabled())


if __name__ == "__main__":
    unittest.main()
