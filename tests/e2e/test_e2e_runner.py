"""The e2e runner (#35) against fake devices: safety (mute toggle, fallback, preconditions), snapshot + restore in
finally and --restore last, scenarios with OSD geometry checks. No real device is touched."""
import json
import os
import shutil
import tempfile
import unittest

from e2e_fakes import REAL_DEVICES, Clock, FakeKodi, Receiver

from camalert_e2e import geometry, profiles
from camalert_e2e import scenarios as sc
from camalert_e2e.adapters.enigma2 import Enigma2
from camalert_e2e.adapters.kodi import Kodi
from camalert_e2e.errors import Skip
from camalert_e2e.runner import Runner, Timeout, restore_last
from camalert_e2e.state import Store

SAVED = {"server": "http://192.168.1.9:1984", "chime": "high", "ha_webhook": "http://192.168.1.5:8123/api/webhook/x",
         "position": "bottom_left", "camera": "porch", "foscam_enabled": "True"}
ALL = ["show", "strip", "mosaic", "tour", "dnd", "ptz", "ha"]


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.tmp = tempfile.mkdtemp()
        self.devs = []

    def tearDown(self):
        for d in self.devs:
            d.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def receiver(self, **kw):
        rx = Receiver(self.clock, saved=dict(SAVED), **kw)
        self.devs.append(rx)
        return rx

    def factory_for(self, dev):
        clock = self.clock

        def factory(profile, environ=None):
            if profile["type"] == "kodi":
                return Kodi(profile, environ, sleep=clock.sleep)
            return Enigma2(profile, environ, box=dev.box, sleep=clock.sleep)
        return factory

    def run_on(self, dev, name="boven", options=None, scenarios=ALL, hour=14, **profile_kw):
        prof = profiles.device(name, dev.profile(**profile_kw))
        options = {"nobody_watching": [name]} if options is None else options
        self.runner = Runner({name: prof}, {}, dict(options), self.tmp, environ={},
                             factory=self.factory_for(dev), ha=False, now=lambda: _at(hour), sleep=self.clock.sleep,
                             clock=self.clock, log=lambda *a: None, use_alarm=False)
        self.runner.ha = None
        data = self.runner.run([name], scenarios)
        return data["devices"][0], data


def _at(hour, minute=0):
    import datetime
    return datetime.datetime(2026, 11, 24, hour, minute)


class TestEnigma2Run(Base):
    def assert_restored(self, rx, volume=30, muted=False, standby=False):
        self.assertEqual((rx.volume, rx.muted, rx.standby), (volume, muted, standby))
        self.assertEqual(rx.saved, SAVED)
        self.assertEqual(rx.box.devices, REAL_DEVICES)
        self.assertIsNone(rx.box.backup)
        self.assertEqual(rx.box.procs, {})
        self.assertEqual(rx.box.files, {})
        self.assertIsNone(rx.ctl.screen)
        self.assertFalse(rx.ctl.dnd)
        self.assertNotIn("REAL CAMERA MOVED", [c[0] for c in rx.ctl.calls])

    def test_full_run_with_fake_cameras(self):
        rx = self.receiver()
        res, data = self.run_on(rx)
        by = {s["name"]: s for s in res["scenarios"]}
        self.assertEqual({n: s["status"] for n, s in by.items()},
                         dict(show="passed", strip="passed", mosaic="passed", tour="passed", dnd="passed",
                              ptz="passed", ha="skipped"), json.dumps(res["scenarios"], indent=1))
        self.assertEqual((res["status"], res["mute"], res["restore"]), ("passed", "muted", []))
        self.assertIn("ptzMoveLeft", rx.box.ptz)
        self.assert_restored(rx)
        # the receiver was muted and quiet settings were set before the first show
        first_show = next(i for i, c in enumerate(rx.ctl.calls) if c[0] == "show")
        self.assertGreater(first_show, -1)
        self.assertIn(("chime", "off"), rx.saveconfig_calls)
        self.assertIn(("ha_webhook", ""), rx.saveconfig_calls)
        # report: files, screenshots, no address, state marked restored
        folder = os.path.join(self.tmp, data["run"])
        for f in ("report.json", "junit.xml", "report.html"):
            self.assertTrue(os.path.exists(os.path.join(folder, f)), f)
        text = open(os.path.join(folder, "report.json")).read()
        self.assertNotIn("127.0.0.1", text)
        self.assertEqual(data["privacy_findings"], 0)
        self.assertTrue(by["show"]["screenshots"])
        self.assertTrue(os.path.exists(os.path.join(folder, by["show"]["screenshots"][0])))
        store = Store.load(self.tmp)
        self.assertEqual(store.pending(), [])

    def test_geometry_failure_is_reported(self):
        rx = self.receiver()
        orig = rx.settings_for_geometry
        rx.settings_for_geometry = lambda: dict(orig(), position="top_left")  # drawn elsewhere than configured
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["status"], "failed")
        failed = [c["detail"] for c in res["scenarios"][0]["checks"] if c["ok"] is False]
        self.assertEqual(len(failed), 1, failed)
        self.assertIn("box", failed[0])
        self.assert_restored(rx)

    def test_photo_loaded_late_is_waited_for(self):
        rx = self.receiver()
        rx.blank_grabs = 3  # the first grab is the "no menu on screen" precondition
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["scenarios"][0]["status"], "passed", res["scenarios"][0]["checks"])
        self.assertEqual(len(res["scenarios"][0]["screenshots"]), 3)  # same file name, three attempts

    def test_strip_loaded_late_is_waited_for(self):
        rx = self.receiver()
        rx.blank_grabs = 3
        res, _ = self.run_on(rx, scenarios=["strip"])
        self.assertEqual(res["scenarios"][0]["status"], "passed", res["scenarios"][0]["checks"])

    def test_boolean_settings_come_back_true(self):
        """/api/settings shows 'True'; saveconfig needs 'true' (real receiver): foscam_enabled must stay on."""
        rx = self.receiver()
        self.run_on(rx, scenarios=["dnd"])
        self.assertEqual(rx.saved["foscam_enabled"], "True")
        self.assertIn(("foscam_enabled", "true"), rx.saveconfig_calls)

    def test_hide_that_keeps_the_tour_open_fails_and_is_cleaned_up(self):
        """A player older than 1.0 (no status "screen"): only the OSD shows the leftover; counted as a failure."""
        rx = self.receiver()
        rx.ctl.keeps, rx.ctl.reports_screen = ("tour", "mosaic"), False
        res, _ = self.run_on(rx, scenarios=["tour", "show"])
        by = {s["name"]: s for s in res["scenarios"]}
        self.assertEqual(by["tour"]["status"], "failed")
        self.assertIn("#63", by["tour"]["checks"][-1]["detail"])
        self.assertEqual(by["show"]["status"], "passed")
        self.assertEqual(rx.keys, [174])
        self.assert_restored(rx)

    def test_status_screen_is_checked(self):
        """#63: the scenarios check status "screen" while open and "none" after hide."""
        rx = self.receiver()
        res, _ = self.run_on(rx, scenarios=["show", "strip", "mosaic", "tour"])
        for sc in res["scenarios"]:
            self.assertEqual(sc["status"], "passed", sc["checks"])
            details = [c["detail"] for c in sc["checks"]]
            self.assertTrue(any(d.startswith("status screen = none") for d in details), details)
        self.assertEqual(rx.keys, [])

    def test_screen_left_open_fails_in_the_scenario_not_in_the_cleanup(self):
        """A player that reports "screen" but keeps the tour open fails on its own status; the EXIT cleanup that
        follows is only a note."""
        rx = self.receiver()
        rx.ctl.keeps = ("tour",)
        res, _ = self.run_on(rx, scenarios=["tour"])
        sc = res["scenarios"][0]
        self.assertEqual(sc["status"], "failed")
        failed = [c["detail"] for c in sc["checks"] if c["ok"] is False]
        self.assertEqual(failed, ["status screen = tour (hide closed the tour)"])
        self.assertIn("cleanup: 1 EXIT press(es)", sc["checks"][-1]["detail"])
        self.assertEqual(rx.keys, [174])
        self.assert_restored(rx)

    def test_menu_on_screen_skips(self):
        rx = self.receiver()
        rx.ctl.screen = ("mosaic", ["porch"], 0)  # something is drawn on the OSD
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["status"], "skipped")
        self.assertIn("no menu or dialog", res["reason"])
        self.assertEqual((rx.saveconfig_calls, rx.keys), ([], []))

    def test_already_muted_is_not_toggled(self):
        rx = self.receiver(muted=True)
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["mute"], "already muted")
        self.assert_restored(rx, muted=True)

    def test_mute_toggle_not_confirmed_falls_back_to_volume_0(self):
        rx = self.receiver(mute_works=False)
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual((res["status"], res["mute"]), ("passed", "volume 0 (mute not confirmed)"))
        self.assert_restored(rx)

    def test_late_mute_state_is_read_again_not_toggled_again(self):
        rx = self.receiver()
        real = rx.route
        state = {"n": 0}

        def route(path, q):
            if path == "/api/vol" and not q.get("set") and rx.muted and state["n"] < 1:
                state["n"] += 1  # the first read after the toggle still says "not muted"
                return ({"result": True, "current": rx.volume, "ismute": False},)
            return real(path, q)
        rx.route = route
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["mute"], "muted")
        self.assert_restored(rx)

    def test_no_scenario_when_it_cannot_be_made_quiet(self):
        rx = self.receiver(mute_works=False, set0_works=False)
        res, _ = self.run_on(rx)
        self.assertEqual(res["status"], "error")
        self.assertIn("mute", res["reason"])
        self.assertEqual([c for c in rx.ctl.calls if c[0] != "hide"], [])
        self.assertEqual(rx.saveconfig_calls, [])
        self.assert_restored(rx)

    def test_scenario_crash_still_restores(self):
        rx = self.receiver()
        real = geometry.check_tiles
        geometry.check_tiles = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            res, _ = self.run_on(rx, scenarios=["strip", "show"])
        finally:
            geometry.check_tiles = real
        self.assertEqual([s["status"] for s in res["scenarios"]], ["failed", "passed"])
        self.assert_restored(rx)

    def test_interrupt_and_timeout_still_restore(self):
        for exc in (KeyboardInterrupt, Timeout):
            rx = self.receiver()
            real = sc.show

            def boom(ctx, r):
                raise exc("stop")
            sc.SCENARIOS["show"] = boom
            try:
                if exc is KeyboardInterrupt:
                    with self.assertRaises(KeyboardInterrupt):
                        self.run_on(rx, scenarios=["show"])
                else:
                    res, _ = self.run_on(rx, scenarios=["show"])
                    self.assertEqual(res["scenarios"][0]["status"], "failed")
            finally:
                sc.SCENARIOS["show"] = real
            self.assert_restored(rx)

    def test_restore_last_after_a_crash(self):
        rx = self.receiver()
        prof = profiles.device("boven", rx.profile())
        dev = self.factory_for(rx)(prof)
        store = Store(self.tmp)
        st = store.device("boven", "enigma2")
        st["before"] = dev.snapshot()
        store.save()
        dev.mute(st, store.save)
        dev.prepare(st, store.save, True)
        dev.camalert.action("show", cam="garden")
        # the process dies here: nothing restored
        self.assertTrue(rx.muted)
        self.assertEqual(rx.saved["chime"] if "chime" in rx.saved else "off", "off")
        problems = restore_last({"boven": prof}, self.tmp, factory=self.factory_for(rx), log=lambda *a: None)
        self.assertEqual(problems, [])
        self.assert_restored(rx)
        self.assertEqual(Store.load(self.tmp).pending(), [])
        self.assertEqual(restore_last({"boven": prof}, self.tmp, factory=self.factory_for(rx), log=lambda *a: None),
                         [])

    def test_standby_needs_wake_and_is_restored(self):
        rx = self.receiver(standby=True)
        res, _ = self.run_on(rx, scenarios=["show"])
        self.assertEqual(res["status"], "skipped")
        self.assertIn("--wake", res["reason"])
        self.assertEqual(rx.saveconfig_calls, [])
        res, _ = self.run_on(rx, options={"wake": True}, scenarios=["show"])
        self.assertEqual(res["status"], "passed")
        self.assert_restored(rx, standby=True)

    def test_preconditions_skip_without_changes(self):
        cases = [
            (dict(), dict(hour=23), "allowed hours"),
            (dict(recording=True), dict(), "not recording"),
            (dict(timers=[{"begin": 10 ** 12, "end": 10 ** 12 + 60, "disabled": 0}]), dict(), None),
            (dict(), dict(quiet=True, sleep_hours="22:00-08:00"), "quiet device allowed"),
            (dict(), dict(hour=7, quiet=True, sleep_hours="22:00-08:00", options={"allow_quiet": True}),
             "not in sleep hours"),
            (dict(), dict(options={}), "nobody watching"),
        ]
        import time
        cases[2] = (dict(timers=[{"begin": int(time.time()) + 600, "end": int(time.time()) + 3600, "disabled": 0}]),
                    dict(), "no timer within 30 min")
        for rx_kw, run_kw, failed in cases:
            rx = self.receiver(**rx_kw)
            hour = run_kw.pop("hour", 14)
            options = run_kw.pop("options", {"nobody_watching": ["boven"]})
            run_kw.setdefault("allowed_hours", "09:00-22:00")
            if run_kw.get("quiet"):
                run_kw["allowed_hours"] = "00:00-23:59"
            res, _ = self.run_on(rx, options=options, scenarios=["show"], hour=hour, **run_kw)
            self.assertEqual(res["status"], "skipped", (rx_kw, run_kw))
            self.assertIn(failed, res["reason"])
            self.assertEqual((rx.saveconfig_calls, rx.volume, rx.muted, rx.ctl.calls), ([], 30, False, []))

    def test_dry_run_changes_nothing(self):
        rx = self.receiver()
        res, _ = self.run_on(rx, options={"dry_run": True, "nobody_watching": ["boven"]})
        self.assertEqual(res["status"], "dry-run")
        self.assertEqual(res["plan"]["volume"], 30)
        self.assertEqual((rx.saveconfig_calls, rx.volume, rx.muted, rx.ctl.calls), ([], 30, False, []))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "state")))

    def test_old_devices_backup_blocks_and_settings_come_back(self):
        rx = self.receiver()
        rx.box.backup = "old"
        res, _ = self.run_on(rx, options={"nobody_watching": ["boven"]}, scenarios=["show"])
        self.assertEqual(res["status"], "skipped")
        self.assertIn("restore last", res["reason"])
        self.assertEqual(rx.saved, SAVED)
        self.assertEqual(rx.box.devices, REAL_DEVICES)

    def test_fake_go2rtc_not_starting_is_an_error(self):
        rx = self.receiver()
        rx.box.fail_go2rtc = True
        res, _ = self.run_on(rx, options={"nobody_watching": ["boven"]}, scenarios=["show"])
        self.assertEqual(res["status"], "error")
        self.assertEqual(rx.box.procs, {})
        self.assertEqual(rx.saved, SAVED)
        self.assertEqual(rx.box.devices, REAL_DEVICES)

    def test_real_cameras_no_screenshots_no_ptz(self):
        rx = self.receiver()
        res, data = self.run_on(rx, options={"nobody_watching": ["boven"]}, cameras="real", ssh="")
        by = {s["name"]: s for s in res["scenarios"]}
        self.assertEqual(by["ptz"]["status"], "skipped")
        self.assertEqual((by["show"]["status"], by["mosaic"]["status"]), ("passed", "passed"))
        # OSD grabs only to see whether something is drawn (never stored); no screenshot files
        self.assertFalse(os.path.exists(os.path.join(self.tmp, data["run"], "screenshots")))
        self.assertTrue(all(not s["screenshots"] for s in res["scenarios"]))
        self.assertNotIn("ptz", [c[0] for c in rx.ctl.calls])
        text = open(os.path.join(self.tmp, data["run"], "report.json")).read()
        self.assertNotIn("porch", text)  # real camera names are cam1, cam2 in the report
        self.assertEqual(rx.saved, SAVED)


class TestKodiRun(Base):
    def kodi(self, **kw):
        k = FakeKodi(self.clock, **kw)
        self.devs.append(k)
        return k

    def test_run_and_restore(self):
        k = self.kodi()
        res, _ = self.run_on(k, name="kodi")
        by = {s["name"]: s["status"] for s in res["scenarios"]}
        self.assertEqual(by, dict(show="passed", strip="passed", mosaic="passed", tour="passed", dnd="passed",
                                  ptz="skipped", ha="skipped"), res)
        self.assertEqual((k.volume, k.muted, k.win), (60, False, 10000))
        self.assertIn("Application.SetMute", k.requests)

    def test_nothing_may_play(self):
        k = self.kodi(playing=1)
        res, _ = self.run_on(k, name="kodi")
        self.assertEqual(res["status"], "skipped")
        self.assertIn("nothing playing", res["reason"])
        self.assertNotIn("Application.SetMute", k.requests)

    def test_late_mute_state(self):
        k = self.kodi()
        real = k.answer
        seen = {"n": 0}

        def answer(req):
            if req["method"] == "Application.GetProperties" and k.muted and seen["n"] < 1:
                seen["n"] += 1
                return {"jsonrpc": "2.0", "id": req["id"], "result": {"volume": k.volume, "muted": False}}
            return real(req)
        k.answer = answer
        res, _ = self.run_on(k, name="kodi", scenarios=["show"])
        self.assertEqual(res["mute"], "muted")

    def test_mute_fallback(self):
        k = self.kodi(mute_works=False)
        res, _ = self.run_on(k, name="kodi", scenarios=["show"])
        self.assertEqual(res["mute"], "volume 0 (mute not confirmed)")
        self.assertEqual((k.volume, k.muted), (60, False))

    def test_chime_all_is_skipped(self):
        k = self.kodi()

        class Shell(object):
            def run(self, cmd, stdin=None, check=True):
                return '<settings version="2"><setting id="chime">all</setting></settings>'
        prof = profiles.device("kodi", k.profile())
        dev = Kodi(prof, {}, shell=Shell(), sleep=self.clock.sleep)
        st = {"before": dev.snapshot(), "changes": {}, "notes": []}
        with self.assertRaises(Skip):
            dev.prepare(st, lambda: None, False)
        self.assertEqual(dev.restore(st), [])


if __name__ == "__main__":
    unittest.main()
