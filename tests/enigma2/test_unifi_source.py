"""#70: the UniFi Protect source on Enigma2: polled in a thread (fake reactor), start/stop with the setting, first
poll only sets the baseline, display mode 'log only', diagnostics lines, consoles never count as PTZ cameras."""
import unittest

import _paths  # noqa: F401
from enigma2.test_ui_findings import Base
from fakes.go2rtc import FakeGo2rtc

CONSOLE = {"type": "unifi", "host": "192.168.1.1", "port": 443, "user": "viewer", "password": "secret"}
CAM_ID = "65a1b2c3d4e5f60718293a4b"


class Failure(object):
    def __init__(self, text):
        self.text = text

    def getErrorMessage(self):
        return self.text


def state(*ids, kind="motion"):
    return {"now": 1, "cams": {CAM_ID: "garden"},
            "events": [{"id": i, "type": kind, "camera": CAM_ID, "smartDetectTypes": []} for i in ids]}


class TestUnifiSource(Base):
    def setUp(self):
        Base.setUp(self)
        self.ctl.load_devices = lambda: {"protect": CONSOLE, "door": {"type": "onvif", "host": "192.168.1.11",
                                                                        "port": 80, "user": "", "password": ""}}
        self.d.UNIFI_STATUS.reset()
        self.shown = []
        self.ctl.show = lambda *a: self.shown.append(a)
        self.c.unifi_kinds.value = "ring,motion"

    def polls(self):
        """The UniFi polls started by the controller (deferToThread calls), removed from the fake reactor."""
        out = [d for d in self.env.reactor.deferred if getattr(d.fn, "__name__", "") == "poll"]
        for d in out:
            self.env.reactor.deferred.remove(d)
        return out

    def test_off_by_default_and_never_on_the_gui_thread(self):
        self.ctl.poll_unifi()
        self.assertEqual(self.polls(), [])
        self.c.unifi_enabled.value = True
        self.ctl.poll_unifi()
        (d,) = self.polls()  # only the console, in a thread
        self.assertEqual(d.args, (CONSOLE,))
        self.assertEqual(self.ctl.unifi_state, {"protect": "busy"})
        self.ctl.poll_unifi()
        self.assertEqual(self.polls(), [])  # still busy: no second poll

    def test_baseline_then_new_event(self):
        self.c.unifi_enabled.value = True
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("1"))
        self.assertEqual(self.shown, [])  # first answer: old events never on screen
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("1", "2"))
        self.assertEqual(self.shown, [("garden", 30, "photo", "normal", "unifi", "Motion", None)])
        self.assertEqual(self.d.UNIFI_STATUS.last_event["camera"], "garden")
        self.assertEqual(self.d.UNIFI_STATUS.consoles, 1)

    def test_per_camera_rule(self):
        """#9: the setting Per camera reaches the source and wins over the general display mode."""
        self.c.unifi_enabled.value = True
        self.c.unifi_mode.value = "log"
        self.c.unifi_camera_rules.value = "Garden=high/photo/45"
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("1"))
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("1", "2"))
        self.assertEqual(self.shown, [("garden", 45, "photo", "high", "unifi", "Motion", None)])

    def test_error_resets_the_baseline_and_is_logged_once(self):
        self.c.unifi_enabled.value = True
        logged = []
        orig = self.d.log
        self.d.log = lambda *a, **kw: logged.append(" ".join(str(x) for x in a))
        try:
            for _i in range(2):
                self.ctl.poll_unifi()
                (d,) = self.polls()
                d.callbacks[0][1](Failure("UniFi Protect login: HTTP 401"))
        finally:
            self.d.log = orig
        self.assertEqual(len([l for l in logged if "HTTP 401" in l]), 1)
        self.assertEqual(self.ctl.unifi_state, {"protect": None})
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("9", kind="ring"))
        self.assertEqual(self.shown, [])  # after an error the next answer is a new baseline

    def test_switching_off_stops_and_drops_late_answers(self):
        self.c.unifi_enabled.value = True
        self.ctl.poll_unifi()
        self.polls()[0].fire(state("1"))
        self.ctl.poll_unifi()
        (late,) = self.polls()
        self.c.unifi_enabled.value = False
        self.ctl.poll_unifi()
        self.assertEqual(self.ctl.unifi_state, {})
        late.fire(state("1", "2"))
        self.assertEqual(self.shown, [])
        self.assertIsNone(self.d.UNIFI_STATUS.last_poll)

    def test_interval_follows_the_setting(self):
        self.c.unifi_interval.value = 12
        self.ctl.poll_unifi()
        self.assertEqual(self.ctl.unifi_seconds, 12)

    def test_consoles_are_no_ptz_cameras(self):
        self.assertFalse(self.ctl.has_ptz("protect"))
        self.assertTrue(self.ctl.has_ptz("door"))


class TestLogOnly(Base):
    def test_log_only_mode_records_but_shows_nothing(self):
        rang = []
        self.ctl.chime = lambda: rang.append(1)
        self.c.chime.value = "all"
        self.assertEqual(self.ctl.show("garden", 10, "log", "alarm", "unifi", "Person"), "ignore")
        self.assertIsNone(self.ctl.window)
        self.assertEqual(rang, [])
        e = self.ctl.events[0]
        self.assertEqual((e["source"], e["action"], e["reason"], e["label"]), ("unifi", "ignore", "log_only", "Person"))


class TestDiagnostics(Base):
    def test_unifi_lines(self):
        diag = self.ca.diagnostics
        fake = FakeGo2rtc().start()  # diagnostics ask go2rtc for its cameras: the fake on 127.0.0.1 (#73)
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        self.c.server.value = fake.url
        self.d.UNIFI_STATUS.reset()
        self.assertFalse([l for l in diag.collect() if "UniFi" in l])  # source off: no lines
        self.c.unifi_enabled.value = True
        self.d.UNIFI_STATUS.consoles = 1
        self.d.UNIFI_STATUS.failed("UniFi Protect events: not reachable (URLError)")
        lines = [l for l in diag.collect() if "UniFi" in l]
        self.assertTrue(lines[0].startswith("[FAIL]"), lines)
        self.assertIn("no event since the start", lines[-1])


if __name__ == "__main__":
    unittest.main()
