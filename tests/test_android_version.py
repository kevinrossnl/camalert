"""tools/android_version.py (#65): the Android versionCode follows the CamAlert version (MAJOR*10000 + MINOR*100 +
PATCH), so every release is higher than the one before and Android accepts it as an update."""
import os
import subprocess
import sys
import unittest

import _paths

_paths.tools()
import android_version as V  # noqa: E402


class TestAndroidVersion(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(V.version_code("1.2.0"), 10200)
        self.assertEqual(V.version_code("1.10.3"), 11003)
        self.assertEqual(V.version_code("2.0.0"), 20000)

    def test_order(self):
        versions = ["1.1.0", "1.1.9", "1.2.0", "1.10.0", "2.0.0"]
        codes = [V.version_code(v) for v in versions]
        self.assertEqual(codes, sorted(codes))
        self.assertGreater(V.version_code("1.2.0"), 1)  # above the versionCode 1 of the debug builds

    def test_rejects(self):
        for bad in ("1.2", "1.2.0-dev", "v1.2.0", "1.100.0", "1.2.100", "x.y.z", "0.0.0"):
            with self.assertRaises(ValueError, msg=bad):
                V.version_code(bad)

    def test_command_line(self):
        tool = os.path.join(_paths.ROOT, "tools", "android_version.py")
        out = subprocess.run([sys.executable, tool, "1.2.0"], stdout=subprocess.PIPE, check=True).stdout.decode()
        self.assertEqual(out.strip(), "10200")
