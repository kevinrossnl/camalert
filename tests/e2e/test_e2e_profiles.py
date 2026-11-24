"""Device profiles of the e2e runner (#35): validation, no literal secrets, and the local file never in git."""
import os
import subprocess
import unittest

import _paths

_paths.e2e()
_paths.core()
from camalert_core import schema  # noqa: E402
from camalert_e2e import profiles  # noqa: E402
from camalert_e2e.adapters.enigma2 import SAFE_SETTINGS  # noqa: E402

BASE = {"type": "enigma2", "host": "192.168.1.20", "allowed_hours": "10:00-22:00"}


def dev(**kw):
    return profiles.device("x", dict(BASE, **kw))


class TestProfiles(unittest.TestCase):
    def test_example_file_is_valid(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("PyYAML not installed")
        devices, ha = profiles.load(profiles.EXAMPLE_FILE)
        self.assertEqual(sorted(devices), ["bedroom", "kodi_living_room", "living_room"])
        self.assertTrue(devices["bedroom"]["quiet"])
        self.assertEqual(ha["token_env"], "HA_TOKEN")

    def test_refused(self):
        bad = [
            dict(token="abc"), dict(password="x"), dict(ha_token="x"), dict(colour=1), dict(type="tv"),
            dict(host=""), dict(cameras="fake"), dict(type="kodi", cameras="fake", ssh="k"),
            dict(quiet=True), dict(allowed_hours="10-22"), dict(allowed_hours="10:00-10:00"),
            dict(watching="ha"), dict(type="kodi", jsonrpc="ssh"), dict(type="kodi", jsonrpc="udp"),
            dict(real_cameras="a,b"),
        ]
        for kw in bad:
            with self.assertRaises(profiles.ProfileError, msg=kw):
                dev(**kw)
        with self.assertRaisesRegex(profiles.ProfileError, "token_env"):
            dev(token="abc")
        for data in (None, {}, {"devices": {}}, {"devices": {"a": BASE}, "other": 1},
                     {"devices": {"a": BASE}, "ha": {"token": "x"}}, {"devices": {"a": "x"}}):
            with self.assertRaises(profiles.ProfileError, msg=data):
                profiles.parse(data)

    def test_defaults_and_env(self):
        d = dev(token_env="MY_TOKEN")
        self.assertEqual((d["camalert_port"], d["openwebif_port"], d["cameras"]), (8099, 80, "real"))
        self.assertEqual(profiles.secret("MY_TOKEN", {"MY_TOKEN": "s3"}), "s3")
        self.assertEqual(profiles.secret("", {"": "x"}), "")
        k = profiles.device("k", dict(BASE, type="kodi"))
        self.assertEqual((k["jsonrpc"], k["jsonrpc_port"]), ("tcp", 9090))

    def test_load_json_and_missing(self):
        import json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"devices": {"a": BASE}}, f)
        try:
            devices, ha = profiles.load(f.name)
            self.assertEqual(list(devices), ["a"])
        finally:
            os.remove(f.name)
        with self.assertRaisesRegex(profiles.ProfileError, "devices.example.yaml"):
            profiles.load(f.name + ".missing")

    def test_windows(self):
        w = profiles.parse_window("22:00-08:00")
        self.assertTrue(profiles.in_window(w, 23 * 60))
        self.assertTrue(profiles.in_window(w, 7 * 60 + 59))
        self.assertFalse(profiles.in_window(w, 8 * 60))
        d = profiles.parse_window("09:30-21:00")
        self.assertTrue(profiles.in_window(d, 9 * 60 + 30))
        self.assertFalse(profiles.in_window(d, 21 * 60))
        self.assertFalse(profiles.in_window(None, 0))
        self.assertIsNone(profiles.parse_window(""))

    def test_safe_settings_exist_on_enigma2(self):
        known = schema.defaults("enigma2")
        self.assertEqual([k for k in SAFE_SETTINGS if k not in known], [])
        self.assertEqual(SAFE_SETTINGS["chime"], "off")


class TestPrivacy(unittest.TestCase):
    """The local profile file and the reports never reach git (or the public mirror)."""

    def ignored(self, path):
        try:
            return subprocess.call(["git", "check-ignore", "-q", os.path.relpath(path, _paths.ROOT)],
                                   cwd=_paths.ROOT) == 0
        except OSError:
            self.skipTest("git not available")

    def test_local_files_are_ignored(self):
        if not os.path.isdir(os.path.join(_paths.ROOT, ".git")):
            self.skipTest("not a git checkout")
        self.assertTrue(self.ignored(_paths.E2E_LOCAL_PROFILES))
        self.assertTrue(self.ignored(os.path.join(_paths.REPORTS, "20260101-000000", "report.json")))
        self.assertTrue(self.ignored(os.path.join(_paths.REPORTS, "state", "last.json")))
        self.assertFalse(self.ignored(os.path.join(_paths.E2E, "devices.example.yaml")))
        self.assertEqual(profiles.LOCAL_FILE, _paths.E2E_LOCAL_PROFILES)

    def test_not_tracked(self):
        if not os.path.isdir(os.path.join(_paths.ROOT, ".git")):
            self.skipTest("not a git checkout")
        out = subprocess.check_output(["git", "ls-files", "tools/e2e", "reports"], cwd=_paths.ROOT).decode()
        self.assertNotIn("devices.local", out)
        self.assertNotIn("reports/", out)


if __name__ == "__main__":
    unittest.main()
