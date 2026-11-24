"""The packages contain exactly the files of the golden listings (#28). A move of source files (#1) must not
change what is installed on a receiver or a Kodi box unless intended: then run
`python3 -m tests.build.update_golden` and review the diff."""
import hashlib
import os
import tempfile
import unittest

import _paths

_paths.tools()
import build_ipk  # noqa: E402
import build_kodi  # noqa: E402
from build.listing import build_all  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")


class TestGoldenListings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.listings = build_all(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_listings_match(self):
        for name, text in sorted(self.listings.items()):
            with self.subTest(package=name):
                with open(os.path.join(GOLDEN, name), encoding="utf-8") as f:
                    golden = f.read()
                self.maxDiff = None
                self.assertEqual(text, golden, "package content changed: if intended, run "
                                               "python3 -m tests.build.update_golden and review the diff")

    def test_ipk_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a, b = build_ipk.build(d1, "someone"), build_ipk.build(d2, "someone")
            self.assertEqual(hashlib.sha256(open(a, "rb").read()).hexdigest(),
                             hashlib.sha256(open(b, "rb").read()).hexdigest())

    def test_kodi_zips_are_reproducible(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            for a, b in zip(build_kodi.build(d1)[:2], build_kodi.build(d2)[:2]):
                self.assertEqual(open(a, "rb").read(), open(b, "rb").read())

    def test_listing_sees_a_missing_file(self):
        """Self test: a package without display.py gives a different listing."""
        golden = open(os.path.join(GOLDEN, "ipk.txt"), encoding="utf-8").read()
        self.assertIn("CamAlert/display.py", golden)
        self.assertNotEqual(golden.replace("CamAlert/display.py\n", ""), golden)


if __name__ == "__main__":
    unittest.main()
