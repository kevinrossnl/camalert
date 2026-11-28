"""#126 on Kodi: Home Assistant installs a newer release. The zip comes from the fixed GitHub URL, is checked
against SHA256SUMS and must hold only service.camalert/ with that version; it waits while Kodi plays something,
then swaps the add-on folder (the old one goes to Kodi's temp folder) and reloads the local add-ons."""
import io
import os
import tempfile
import unittest
import zipfile

import _paths
from kodi import stubs as kodi_stubs

kodi_stubs.install()
_paths.kodi_package()
up = _paths.kodi_module("kupdater")
su = _paths.kodi_module("camalert_core.selfupdate")


def make_zip(version, extra=None, addon_id="service.camalert"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("service.camalert/addon.xml", '<addon id="%s" name="CamAlert" version="%s"></addon>'
                   % (addon_id, version))
        z.writestr("service.camalert/resources/lib/camalert/__init__.py", '__version__ = "%s"\n' % version)
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return buf.getvalue()


class FakeGitHub(object):
    def __init__(self, version, data):
        base = su.RELEASE_BASE % version
        name = su.ASSETS["kodi"] % version
        self.files = {base + su.SUMS: ("%s  %s\n" % (su.sha256(data), name)).encode(), base + name: data}

    def __call__(self, url):
        if url not in self.files:
            raise IOError("HTTP Error 404: Not Found")
        return self.files[url]


class TestKodiUpdater(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addon = os.path.join(self.tmp, "addons", "service.camalert")
        os.makedirs(self.addon)
        with open(os.path.join(self.addon, "addon.xml"), "w") as f:
            f.write("old")
        self.temp = os.path.join(self.tmp, "temp")
        os.makedirs(self.temp)
        self.playing, self.sleeps, self.reloads = [], [], []
        self.saved = {k: getattr(up, k) for k in ("playing", "sleep", "reload_addons", "opener")}
        self.saved_run = up.run
        self.saved_api = (up.kodiapi.addon_path, up.kodiapi.temp_dir)
        up.playing = lambda: bool(self.playing and self.playing.pop(0))
        up.sleep = lambda s: self.sleeps.append(s) or True
        up.reload_addons = lambda: self.reloads.append(True)
        up.kodiapi.addon_path = lambda *p: self.addon
        up.kodiapi.temp_dir = lambda: self.temp
        up.STATE.set("idle")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(up, k, v)
        up.kodiapi.addon_path, up.kodiapi.temp_dir = self.saved_api
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_update(self, version="9.0.0", data=None):
        up.opener = FakeGitHub(version, make_zip(version) if data is None else data)
        up.STATE.set("downloading", version)
        up.run(version)
        return up.STATE.as_status()

    def test_installs_and_keeps_the_old_addon(self):
        st = self.run_update()
        self.assertEqual(st["update_state"], "installing")
        self.assertIn('version="9.0.0"', open(os.path.join(self.addon, "addon.xml")).read())
        old = [d for d in os.listdir(self.temp) if d.startswith("previous-")]
        self.assertEqual(len(old), 1)
        self.assertEqual(open(os.path.join(self.temp, old[0], "addon.xml")).read(), "old")
        self.assertEqual(self.reloads, [True])

    def test_waits_while_something_plays(self):
        self.playing = [True, True, False]
        st = self.run_update()
        self.assertEqual(self.sleeps, [up.WAIT_STEP, up.WAIT_STEP])
        self.assertEqual(st["update_state"], "installing")

    def test_kodi_stops_while_waiting(self):
        self.playing = [True, True]
        up.sleep = lambda s: False  # Kodi shuts down
        st = self.run_update()
        self.assertEqual(st["update_state"], "idle")
        self.assertEqual(open(os.path.join(self.addon, "addon.xml")).read(), "old")

    def test_refuses_bad_zips(self):
        for data, why in ((make_zip("9.0.1"), "another version"),
                          (make_zip("9.0.0", {"../evil.py": "x"}), "unexpected file"),
                          (make_zip("9.0.0", {"other.addon/addon.xml": "x"}), "unexpected file"),
                          (make_zip("9.0.0", addon_id="plugin.evil"), "another version"),
                          (b"not a zip", "zip")):
            st = self.run_update(data=data)
            self.assertEqual(st["update_state"], "failed", why)
            self.assertIn(why.split()[0], st["update_error"].lower() if why == "zip" else st["update_error"])
            self.assertEqual(open(os.path.join(self.addon, "addon.xml")).read(), "old")
        self.assertEqual(self.reloads, [])

    def test_wrong_checksum(self):
        up.opener = FakeGitHub("9.0.0", make_zip("9.0.0"))
        up.opener.files[su.RELEASE_BASE % "9.0.0" + su.ASSETS["kodi"] % "9.0.0"] = make_zip("9.0.0", {
            "service.camalert/x.py": "changed"})
        up.run("9.0.0")
        self.assertEqual(up.STATE.as_status()["update_error"], "checksum does not match")

    def test_start_runs_in_a_thread(self):
        import threading
        done = threading.Event()
        up.run = lambda v: (self.reloads.append(v), done.set())
        try:
            up.start("9.0.0")
            self.assertEqual(up.STATE.state, "downloading")
            self.assertTrue(done.wait(5))
        finally:
            up.run = self.saved_run
        self.assertEqual(self.reloads, ["9.0.0"])

if __name__ == "__main__":
    unittest.main()
