import unittest
from unittest.mock import mock_open, patch

from floatingbar import trace


class TracePrivacyTests(unittest.TestCase):
    def test_exception_trace_records_type_but_not_message(self):
        handle = mock_open()
        with patch("floatingbar.trace.open", handle):
            trace.trace_exception(
                "diagnostic failure",
                RuntimeError("private window title or message text"),
            )

        written = "".join(call.args[0] for call in handle().write.call_args_list)
        self.assertIn("diagnostic failure", written)
        self.assertIn("exception=RuntimeError", written)
        self.assertNotIn("private window title or message text", written)

    def test_exception_name_falls_back_for_non_identifier_type_names(self):
        class WeirdType(BaseException):
            pass

        self.assertEqual(trace.exception_name(WeirdType("secret")), "WeirdType")


if __name__ == "__main__":
    unittest.main()
