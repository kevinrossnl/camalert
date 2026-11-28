"""#126: a player updates itself from Home Assistant. Only CamAlert's own GitHub release, only a newer version,
only a file whose SHA-256 is in the release's SHA256SUMS."""
import unittest

import _paths

_paths.core()
from camalert_core import selfupdate as su  # noqa: E402


class FakeGitHub(object):
    """Serves the release files of one version; records every URL asked for."""

    def __init__(self, version="1.4.0", files=None, sums=None):
        self.version, self.asked = version, []
        self.files = files if files is not None else {
            su.ASSETS[p] % version: ("%s-%s" % (p, version)).encode() for p in su.ASSETS}
        self.sums = sums if sums is not None else "".join(
            "%s  %s\n" % (su.sha256(d), n) for n, d in self.files.items())

    def __call__(self, url):
        self.asked.append(url)
        base = su.RELEASE_BASE % self.version
        if not url.startswith(base):
            raise IOError("404 %s" % url)
        name = url[len(base):]
        if name == su.SUMS:
            return self.sums.encode()
        if name not in self.files:
            raise IOError("404 %s" % url)
        return self.files[name]


class TestSelfUpdate(unittest.TestCase):
    def test_request_rules(self):
        self.assertEqual(su.check_request("1.3.1", "1.4.0"), "1.4.0")
        self.assertEqual(su.check_request("1.3.1", "v1.3.2"), "1.3.2")
        for current, version, allowed, why in (
                ("1.3.1", "1.4.0", False, "off"), ("1.3.1", "1.3.1", True, "not newer"),
                ("1.3.1", "1.2.0", True, "not newer"), ("1.3.1", "1.4", True, "invalid"),
                ("1.3.1", "1.4.0-beta", True, "invalid"), ("1.3.1", "../1.4.0", True, "invalid"),
                ("1.3.1", "", True, "invalid"), ("1.3.1", None, True, "invalid")):
            with self.assertRaises(su.UpdateError) as e:
                su.check_request(current, version, allowed)
            self.assertIn(why, str(e.exception))

    def test_fixed_urls(self):
        self.assertEqual(su.asset_url("enigma2", "1.4.0"), "https://github.com/kevinrossnl/camalert/releases/download/"
                                                           "v1.4.0/enigma2-plugin-extensions-camalert_1.4.0_all.ipk")
        self.assertEqual(su.asset_url("kodi", "1.4.0").rsplit("/", 1)[1], "service.camalert-1.4.0.zip")
        self.assertEqual(su.asset_url("androidtv", "1.4.0").rsplit("/", 1)[1], "camalert-androidtv-1.4.0.apk")
        self.assertTrue(su.sums_url("1.4.0").endswith("/v1.4.0/SHA256SUMS"))
        with self.assertRaises(su.UpdateError):
            su.asset_name("browser", "1.4.0")

    def test_parse_sums(self):
        h = "a" * 64
        self.assertEqual(su.parse_sums("%s  x.zip\n%s *y.apk\n\nnoise\n%s  z ipk.ipk  \n" % (h, h.upper(), h)),
                         {"x.zip": h, "y.apk": h, "z ipk.ipk": h})
        self.assertEqual(su.parse_sums(None), {})

    def test_fetch_checks_the_sum(self):
        gh = FakeGitHub()
        for p in su.ASSETS:
            name, data = su.fetch(p, "1.4.0", gh)
            self.assertEqual((name, data), (su.ASSETS[p] % "1.4.0", ("%s-1.4.0" % p).encode()))
        self.assertTrue(all(u.startswith("https://github.com/kevinrossnl/camalert/releases/download/v1.4.0/")
                            for u in gh.asked))

    def test_fetch_refuses(self):
        name = su.ASSETS["kodi"] % "1.4.0"
        bad = FakeGitHub(sums="%s  %s\n" % ("0" * 64, name))
        with self.assertRaisesRegex(su.UpdateError, "checksum"):
            su.fetch("kodi", "1.4.0", bad)
        missing = FakeGitHub(sums="")
        with self.assertRaisesRegex(su.UpdateError, "not listed"):
            su.fetch("kodi", "1.4.0", missing)
        empty = FakeGitHub(files={name: b""}, sums="%s  %s\n" % (su.sha256(b""), name))
        with self.assertRaisesRegex(su.UpdateError, "size"):
            su.fetch("kodi", "1.4.0", empty)
        with self.assertRaises(IOError):  # no network: the opener's error goes up to the player
            su.fetch("kodi", "1.4.0", FakeGitHub(version="9.9.9"))

    def test_state(self):
        st = su.UpdateState()
        self.assertEqual(st.as_status(), {"update_state": "idle", "update_version": None, "update_error": None})
        self.assertFalse(st.busy())
        st.set("downloading", "1.4.0")
        self.assertTrue(st.busy())
        st.set("failed", error="checksum does not match")
        self.assertEqual(st.as_status(), {"update_state": "failed", "update_version": "1.4.0",
                                          "update_error": "checksum does not match"})
        st.set("waiting")
        self.assertIsNone(st.error)
        with self.assertRaises(ValueError):
            st.set("done")


if __name__ == "__main__":
    unittest.main()
