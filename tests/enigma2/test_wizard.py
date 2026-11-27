"""#120: the first-start wizard on Enigma2: opens instead of the settings on a new receiver, walks through go2rtc,
camera (with a preview), test (without chime) and the Home Assistant hint; network calls only in threads."""
import time
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestEnigma2Wizard(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openpli")
        self.p = self.env.camalert
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.p.plugin.sessionstart(0, session=self.session)
        self.ctl = self.p.display.Controller.instance
        self.calls = []
        orig = self.session.openWithCallback

        def owc(callback, screen, *a, **kw):
            s = orig(callback, screen, *a, **kw)
            self.calls.append((callback, type(s).__name__, a, kw, s))
            return s
        self.session.openWithCallback = owc
        self.shown = []
        self.ctl.show = lambda *a, **kw: self.shown.append((a, kw)) or "show"
        self.ctl.hide = lambda *a, **kw: None
        self.c = self.env.config.plugins.camalert
        core = self.p.wizard.core
        self._own_ip, core.own_ip = core.own_ip, lambda *a: "192.168.1.40"  # no real network (#73)

    def tearDown(self):
        self.p.wizard.core.own_ip = self._own_ip
        e2fake.uninstall()

    def last(self):
        return self.calls[-1]

    def threads(self, fn_name):
        out = [d for d in self.env.reactor.deferred if getattr(d.fn, "__name__", "") == fn_name]
        for d in out:
            self.env.reactor.deferred.remove(d)
        return out

    def test_opens_on_a_new_receiver_and_walks_through(self):
        self.assertTrue(self.p.wizard.should_start())
        self.p.plugin.main(self.session)
        self.assertEqual(self.last()[1], "MessageBox")  # searching...
        search, = self.threads("search")  # the search runs in a thread
        search.fire([("http://192.168.1.10:1984", ["front_door", "garden"])])
        cb, kind, a, kw, box = self.last()
        self.assertEqual(kind, "ChoiceBox")
        labels = [x[0] for x in kw["list"]]
        self.assertIn("http://192.168.1.10:1984 (2 cameras)", labels[0])
        self.assertEqual(len(labels), 3)  # found, enter yourself, without go2rtc
        cb(kw["list"][0])
        self.assertEqual(self.c.server.value, "http://192.168.1.10:1984")
        cb, kind, a, kw, box = self.last()
        self.assertEqual([x[1] for x in kw["list"]], ["front_door", "garden"])
        cb(kw["list"][1])
        (args, kwargs), = self.shown  # preview, as a test (no chime, tagged test)
        self.assertEqual(args[:4], ("garden", 15, "photo", "high"))
        self.assertEqual(kwargs["source"], "test")
        cb, kind, a, kw, box = self.last()
        self.assertEqual(kind, "MessageBox")
        cb(True)  # the right camera
        self.assertEqual(self.c.camera.value, "garden")
        cb, kind, a, kw, box = self.last()
        cb(True)  # test notification
        self.assertEqual(self.shown[-1][0][:3], ("garden", 10, "notify"))
        self.assertEqual(self.shown[-1][1]["source"], "test")
        self.assertTrue(self.c.wizard_done.value)
        self.assertFalse(self.p.wizard.should_start())
        opened = [type(s).__name__ for s in self.session.opened]
        self.assertIn("CamAlertSetup", opened)  # the settings follow

    def test_typed_address_is_checked_in_a_thread(self):
        w = self.p.wizard.Wizard(self.session)
        w.start()
        self.threads("search")[0].fire([])
        cb, kind, a, kw, box = self.last()
        self.assertIn("No go2rtc found", kw["title"])
        cb(kw["list"][0])  # enter the address yourself
        cb, kind, a, kw, box = self.last()
        self.assertEqual(kind, "VirtualKeyBoard")
        cb("192.168.1.20")
        check, = self.threads("fetch_streams")
        self.assertEqual(check.args[0], "http://192.168.1.20:1984")
        for ok, err in check.callbacks:
            err(type("F", (), {"getErrorMessage": lambda self: "refused"})())
        cb, kind, a, kw, box = self.last()
        self.assertEqual(kind, "MessageBox")  # does not answer: back to the list
        cb()
        self.assertEqual(self.last()[1], "ChoiceBox")
        self.assertEqual(self.c.server.value, "")

    def test_leaving_early_marks_it_done(self):
        w = self.p.wizard.Wizard(self.session)
        w.start()
        self.threads("search")[0].fire([])
        cb = self.last()[0]
        cb(None)  # EXIT
        self.assertTrue(self.c.wizard_done.value)
        self.assertEqual(self.c.server.value, "")

    def test_without_go2rtc(self):
        w = self.p.wizard.Wizard(self.session)
        w.start()
        self.threads("search")[0].fire([])
        cb, kind, a, kw, box = self.last()
        cb(kw["list"][-1])
        self.assertEqual(self.c.source.value, "direct")
        self.assertTrue(self.c.wizard_done.value)

    def test_existing_installation_opens_the_settings(self):
        self.c.server.value = "http://192.168.1.10:1984"
        self.p.plugin.main(self.session)
        self.assertEqual(type(self.session.opened[-1]).__name__, "CamAlertSetup")
        self.assertEqual(self.calls, [])

    def test_go2rtc_without_cameras(self):
        w = self.p.wizard.Wizard(self.session)
        w.start()
        self.threads("search")[0].fire([("http://192.168.1.10:1984", [])])
        cb, kind, a, kw, box = self.last()
        cb(kw["list"][0])
        self.assertTrue(self.c.wizard_done.value)
        self.assertEqual(self.c.server.value, "http://192.168.1.10:1984")


if __name__ == "__main__":
    unittest.main()
