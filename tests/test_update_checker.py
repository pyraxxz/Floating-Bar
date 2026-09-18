import io
import json
import unittest
from unittest.mock import patch

from floatingbar.update_checker import ReleaseInfo, fetch_latest_release, is_newer_version, parse_version


class UpdateCheckerTests(unittest.TestCase):
    def test_version_parser_accepts_normal_and_prefixed_versions(self):
        self.assertEqual(parse_version("0.2.0"), (0, 2, 0))
        self.assertEqual(parse_version("v1.3.7"), (1, 3, 7))

    def test_invalid_version_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_version("nightly")

    def test_newer_release_detection(self):
        self.assertTrue(is_newer_version("0.1.20", "0.2.0"))
        self.assertFalse(is_newer_version("0.2.0", "0.2.0"))
        self.assertFalse(is_newer_version("0.3.0", "0.2.9"))

    def test_release_metadata_is_normalized(self):
        payload = json.dumps({
            "tag_name": "v0.3.0",
            "html_url": "https://github.com/pyraxxz/Floating-Bar/releases/tag/v0.3.0",
        }).encode("utf-8")

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return payload

        info = fetch_latest_release(opener=lambda _request, timeout: Response())
        self.assertEqual(info, ReleaseInfo("0.3.0", "https://github.com/pyraxxz/Floating-Bar/releases/tag/v0.3.0"))

    def test_untrusted_release_url_is_rejected(self):
        payload = json.dumps({
            "tag_name": "v0.3.0",
            "html_url": "https://example.com/release",
        }).encode("utf-8")

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return payload

        with self.assertRaises(ValueError):
            fetch_latest_release(opener=lambda _request, timeout: Response())


if __name__ == "__main__":
    unittest.main()
