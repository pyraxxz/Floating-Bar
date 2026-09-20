import unittest

from main import fatal_crash_message


class MainPrivacyTests(unittest.TestCase):
    def test_fatal_crash_message_is_content_free(self):
        message = fatal_crash_message()
        self.assertIn("unrecoverable error", message.lower())
        self.assertIn("content-free", message.lower())
        self.assertNotIn("traceback", message.lower())
        self.assertNotIn("exception=", message.lower())


if __name__ == "__main__":
    unittest.main()
