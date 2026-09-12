import unittest

from floatingbar.overlay import _classify_send_result


class OverlayStateTests(unittest.TestCase):
    def test_error_is_failed(self):
        self.assertEqual(_classify_send_result(None, "Telegram unavailable"), "failed")

    def test_unverified_strategy_is_unverified(self):
        self.assertEqual(
            _classify_send_result("posted-click (verification-unavailable)", None),
            "unverified",
        )
        self.assertEqual(
            _classify_send_result("posted-click (unverified)", None),
            "unverified",
        )

    def test_verified_strategy_is_verified(self):
        self.assertEqual(
            _classify_send_result("posted-click (VERIFIED)", None),
            "verified",
        )
        self.assertEqual(
            _classify_send_result("posted-enter (VERIFIED)", None),
            "verified",
        )

    def test_unknown_result_is_unknown(self):
        self.assertEqual(_classify_send_result(None, None), "unknown")

    def test_error_takes_precedence_over_strategy(self):
        self.assertEqual(
            _classify_send_result("posted-click (VERIFIED)", "failed after send"),
            "failed",
        )


if __name__ == "__main__":
    unittest.main()
