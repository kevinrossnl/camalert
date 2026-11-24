import os
import subprocess
import tarfile
import tempfile
import unittest

import _paths  # noqa: E402

_paths.tools()
import build_ipk  # noqa: E402


class TestBuild(unittest.TestCase):
    def test_ipk_contents(self):
        with tempfile.TemporaryDirectory() as d:
            path = build_ipk.build(d, "someone")
            subprocess.check_call(["ar", "x", path], cwd=d)
            self.assertEqual(open(os.path.join(d, "debian-binary")).read(), "2.0\n")
            names = tarfile.open(os.path.join(d, "data.tar.gz")).getnames()
            base = "./usr/lib/enigma2/python/Plugins/Extensions/CamAlert/"
            for f in ("plugin.py", "__init__.py", "camalert_core/rules.py", "display.py", "server.py", "setup.py", "camalert.png",
                      "locale/nl/LC_MESSAGES/CamAlert.mo", "locale/de/LC_MESSAGES/CamAlert.mo"):
                self.assertIn(base + f, names)
            control = tarfile.open(os.path.join(d, "control.tar.gz")).extractfile("./control").read().decode()
            self.assertIn("Version: " + build_ipk.version(), control)
            self.assertIn("github.com/someone/", control)

    def test_feed(self):
        import gzip
        import build_feed
        with tempfile.TemporaryDirectory() as d:
            build_ipk.build(d, "someone")
            text = build_feed.build(d)
            self.assertIn("Package: enigma2-plugin-extensions-camalert", text)
            self.assertIn("Filename: enigma2-plugin-extensions-camalert_%s_all.ipk" % build_ipk.version(), text)
            self.assertRegex(text, r"SHA256sum: [0-9a-f]{64}")
            self.assertEqual(gzip.open(os.path.join(d, "Packages.gz")).read().decode(), text)

    def test_sources_compile(self):
        src = _paths.ENIGMA2
        for f in os.listdir(src):
            if f.endswith(".py"):
                compile(open(os.path.join(src, f), encoding="utf-8").read(), f, "exec")


if __name__ == "__main__":
    unittest.main()
