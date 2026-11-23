import os
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
import build_ipk  # noqa: E402


class TestBuild(unittest.TestCase):
    def test_ipk_contents(self):
        with tempfile.TemporaryDirectory() as d:
            path = build_ipk.build(d, "someone")
            subprocess.check_call(["ar", "x", path], cwd=d)
            self.assertEqual(open(os.path.join(d, "debian-binary")).read(), "2.0\n")
            names = tarfile.open(os.path.join(d, "data.tar.gz")).getnames()
            base = "./usr/lib/enigma2/python/Plugins/Extensions/CamAlert/"
            for f in ("plugin.py", "__init__.py", "logic.py", "display.py", "server.py", "setup.py", "camalert.png",
                      "locale/nl/LC_MESSAGES/CamAlert.mo", "locale/de/LC_MESSAGES/CamAlert.mo"):
                self.assertIn(base + f, names)
            control = tarfile.open(os.path.join(d, "control.tar.gz")).extractfile("./control").read().decode()
            self.assertIn("Version: " + build_ipk.version(), control)
            self.assertIn("github.com/someone/", control)

    def test_sources_compile(self):
        src = os.path.join(HERE, "..", "src", "CamAlert")
        for f in os.listdir(src):
            if f.endswith(".py"):
                compile(open(os.path.join(src, f), encoding="utf-8").read(), f, "exec")


if __name__ == "__main__":
    unittest.main()
