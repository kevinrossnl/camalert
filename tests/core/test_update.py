"""camalert_core.update: update check against GitHub releases."""
import unittest

import _paths

_paths.core()
from camalert_core import update  # noqa: E402


class TestUpdate(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(update.newer_version("1.0.0", "v1.1.0"), "1.1.0")
        self.assertIsNone(update.newer_version("1.0.0", "v1.0.0"))
        self.assertEqual(update.newer_version("1.2.0", "1.10.0"), "1.10.0")
        self.assertIsNone(update.newer_version("1.0.0", None))
        self.assertEqual(update.version_tuple("v2.1"), (2, 1))
        self.assertEqual(update.version_tuple(""), (0,))

    def test_latest_tag(self):
        self.assertEqual(update.latest_tag('{"tag_name": "v1.1.0", "draft": false}'), "v1.1.0")
        self.assertIsNone(update.latest_tag('{"tag_name": "v2.0.0-rc1", "prerelease": true}'))
        self.assertIsNone(update.latest_tag("not json"))
        self.assertIsNone(update.latest_tag("[1]"))


if __name__ == "__main__":
    unittest.main()
