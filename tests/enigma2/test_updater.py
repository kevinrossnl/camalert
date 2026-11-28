"""#126 on Enigma2: Home Assistant installs a newer release. Downloaded from the fixed GitHub URL and checked
against SHA256SUMS in a thread; installed only in standby without a recording (now or within 10 minutes), then a
quiet GUI restart and back to standby."""
import os
import tempfile
import types
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class FakeGitHub(object):
    def __init__(self, core, version="9.0.0", good=True):
        su = core.selfupdate
        self.name = su.ASSETS["enigma2"] % version
        self.data = b"ipk-" + version.encode()
        digest = su.sha256(self.data) if good else "0" * 64
        self.base = su.RELEASE_BASE % version
        self.files = {self.base + su.SUMS: ("%s  %s\n" % (digest, self.name)).encode(), self.base + self.name: self.data}
        self.asked = []

    def __call__(self, url):
        self.asked.append(url)
        if url not in self.files:
            raise IOError("HTTP Error 404: Not Found")
        return self.files[url]


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.env.camalert.plugin.sessionstart(0, session=self.session)
        import importlib
        self.up = importlib.import_module("CamAlert.updater")
        self.core = types.SimpleNamespace(selfupdate=importlib.import_module("CamAlert.camalert_core.selfupdate"))
        self.tmp = tempfile.mkdtemp()
        self.up.IPK = os.path.join(self.tmp, "u.ipk")
        self.up.BACK_TO_STANDBY = os.path.join(self.tmp, "standby")
        self.up.NO_TV_WAKE = os.path.join(self.tmp, "nowake")
        self.up.STATE.set("idle")
        self.up._pending.update(version=None, timer=None)
        self.standby, self.recording, self.opkg, self.restarted = True, False, [], []
        self.up.in_standby = lambda: self.standby
        self.up.recording_soon = lambda now=None: self.recording
        self.up.run_opkg = lambda path: self.opkg.append(open(path, "rb").read()) or (True, "Configuring")
        self.up.restart_gui = lambda: self.restarted.append(True)
        self.gh = FakeGitHub(self.core)
        self.up.opener = self.gh

    def tearDown(self):
        e2fake.uninstall()

    def threads(self):
        """Runs the work that went to the thread pool, as the reactor would (errors go to the errbacks)."""
        while self.env.reactor.deferred:
            d = self.env.reactor.deferred.pop(0)
            try:
                result = d.fn(*d.args)
            except Exception as e:  # noqa: BLE001
                for _ok, err in d.callbacks:
                    if err:
                        err(types.SimpleNamespace(getErrorMessage=lambda e=e: str(e)))
                continue
            d.fire(result)

    def status(self):
        return self.up.STATE.as_status()

    def test_installs_in_standby_and_restarts_quietly(self):
        self.up.start("9.0.0")
        self.assertEqual(self.status()["update_state"], "downloading")
        self.threads()  # download and check
        self.threads()  # opkg install
        self.assertEqual(self.opkg, [b"ipk-9.0.0"])
        self.assertEqual(self.restarted, [True])
        self.assertEqual(open(self.up.NO_TV_WAKE).read(), "True")
        self.assertEqual(open(self.up.BACK_TO_STANDBY).read(), "9.0.0")
        self.assertFalse(os.path.exists(self.up.IPK))
        self.assertTrue(all(u.startswith("https://github.com/kevinrossnl/camalert/releases/download/v9.0.0/")
                            for u in self.gh.asked))

    def test_waits_for_standby_and_for_recordings(self):
        self.standby = False
        self.up.start("9.0.0")
        self.threads()
        self.assertEqual(self.status(), {"update_state": "waiting", "update_version": "9.0.0", "update_error": None})
        self.assertEqual(self.opkg, [])
        timer = self.up._pending["timer"]
        self.assertTrue(timer.active())
        self.standby, self.recording = True, True  # in standby now, but a recording runs or starts soon
        self.up.try_install()
        self.assertEqual(self.status()["update_state"], "waiting")
        self.recording = False
        self.up.try_install()
        self.assertEqual(self.status()["update_state"], "installing")
        self.threads()
        self.assertEqual(self.restarted, [True])

    def test_wrong_checksum_and_no_network_fail_cleanly(self):
        self.up.opener = FakeGitHub(self.core, good=False)
        self.up.start("9.0.0")
        self.threads()
        st = self.status()
        self.assertEqual((st["update_state"], st["update_error"]), ("failed", "checksum does not match"))
        self.assertEqual((self.opkg, self.restarted), ([], []))
        self.up.opener = FakeGitHub(self.core, version="9.9.9")  # 404 for 9.0.0
        self.up.start("9.0.0")
        self.threads()
        self.assertEqual(self.status()["update_state"], "failed")
        self.assertIn("404", self.status()["update_error"])

    def test_opkg_error_reported(self):
        self.up.run_opkg = lambda path: (False, "Collected errors: * no space left")
        self.up.start("9.0.0")
        self.threads()
        self.threads()
        self.assertEqual(self.status()["update_state"], "failed")
        self.assertIn("no space left", self.status()["update_error"])
        self.assertEqual(self.restarted, [])

    def test_back_to_standby_after_the_restart(self):
        self.assertFalse(self.up.after_restart(self.session))
        with open(self.up.BACK_TO_STANDBY, "w") as f:
            f.write("9.0.0")
        self.standby = False
        opened = []
        self.session.open = lambda screen, *a, **kw: opened.append(screen.__name__)
        self.assertTrue(self.up.after_restart(self.session))
        self.assertEqual(opened, ["Standby"])
        self.assertFalse(os.path.exists(self.up.BACK_TO_STANDBY))

    def test_recording_and_standby_checks(self):
        import importlib
        import sys
        up = importlib.reload(self.up)  # the real checks, not the test doubles from setUp
        rt = types.SimpleNamespace(isRecording=lambda: False, getNextRecordingTime=lambda: -1)
        sys.modules["NavigationInstance"] = types.SimpleNamespace(instance=types.SimpleNamespace(RecordTimer=rt))
        try:
            self.assertFalse(up.recording_soon(now=1000))
            rt.getNextRecordingTime = lambda: 1000 + 300  # starts in 5 minutes
            self.assertTrue(up.recording_soon(now=1000))
            rt.getNextRecordingTime = lambda: 1000 + 3600
            self.assertFalse(up.recording_soon(now=1000))
            rt.isRecording = lambda: True
            self.assertTrue(up.recording_soon(now=1000))
        finally:
            del sys.modules["NavigationInstance"]
        self.assertFalse(up.recording_soon())  # no record timer on this image
        standby = sys.modules["Screens.Standby"]
        standby.inStandby = None
        self.assertFalse(up.in_standby())
        standby.inStandby = object()
        self.assertTrue(up.in_standby())
        standby.inStandby = None

    def test_status_and_route(self):
        server = self.env.camalert.server
        self.assertEqual(server.BACKEND.update_status()["update_state"], "idle")
        server.BACKEND.start_update("9.0.0")
        self.assertEqual(server.BACKEND.update_status()["update_state"], "downloading")


if __name__ == "__main__":
    unittest.main()
