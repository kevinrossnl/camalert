"""e2e runner against a fake Android TV / Fire TV player (#68, #77): adb for the device state, the fake go2rtc on
the device, /camalert/setup to point the app at it and back, screencap for the geometry checks."""
import json
import unittest

from e2e_fakes import FakeAndroid
from test_e2e_runner import Base

from camalert_e2e import profiles
from camalert_e2e.adapters.androidtv import AndroidTv, parse_awake, parse_front, parse_playing, parse_volume
from camalert_e2e.profiles import ProfileError


class TestAndroidTv(Base):
    def tv(self, **kw):
        t = FakeAndroid(self.clock, **kw)
        self.devs.append(t)
        return t

    def factory_for(self, dev):
        clock = self.clock

        def factory(profile, environ=None):
            return AndroidTv(profile, environ, adb=dev.adb, sleep=clock.sleep)
        return factory

    def test_fake_cameras_and_restore(self):
        t = self.tv()
        res, _ = self.run_on(t, name="firetv", cameras="fake",
                             scenarios=["show", "strip", "mosaic", "tour", "dnd", "ptz", "chime_muted", "settings"])
        by = {s["name"]: s["status"] for s in res["scenarios"]}
        self.assertEqual(by, dict(show="passed", strip="passed", mosaic="passed", tour="passed", dnd="passed",
                                  ptz="skipped", chime_muted="passed", settings="passed"), json.dumps(res, indent=1))
        self.assertEqual(res["restore"], [])
        self.assertEqual(t.saved["server"], "http://192.168.1.5:1984")  # back to restore_server
        self.assertFalse(t.fake_running)
        self.assertTrue(t.pushed)
        self.assertEqual(t.vol, 9)
        self.assertNotIn("mute", " ".join(t.commands))  # never mute (#102)

    def test_real_cameras(self):
        t = self.tv()
        res, _ = self.run_on(t, name="firetv", scenarios=["show", "dnd"])
        self.assertEqual({s["name"]: s["status"] for s in res["scenarios"]}, {"show": "passed", "dnd": "passed"})
        self.assertFalse(t.pushed)  # no fake go2rtc
        self.assertEqual(t.saved["server"], "http://192.168.1.5:1984")

    def test_something_playing_is_skipped(self):
        t = self.tv(playing=1)
        res, _ = self.run_on(t, name="firetv", scenarios=["show"])
        self.assertEqual(res["status"], "skipped")
        self.assertIn("nothing playing", res["reason"])

    def test_screen_off_needs_wake_and_goes_back_to_sleep(self):
        t = self.tv(awake=False)
        res, _ = self.run_on(t, name="firetv", options={"nobody_watching": ["firetv"], "wake": True},
                             scenarios=["show"])
        self.assertEqual(res["status"], "passed", res)
        self.assertFalse(t.awake)

    def test_profile(self):
        p = profiles.device("tv", {"type": "androidtv", "host": "192.168.1.30"})
        self.assertEqual((p["adb_port"], p["adb"], p["cameras"]), (5555, "adb", "real"))
        with self.assertRaises(ProfileError):
            profiles.device("tv", {"type": "androidtv", "host": "192.168.1.30", "cameras": "fake"})

    def test_parsers(self):
        self.assertEqual(parse_volume("[v] stream=3\n[v] volume is 7 in range [0..15]"), 7)
        self.assertIsNone(parse_volume(""))
        self.assertTrue(parse_awake("  mWakefulness=Awake"))
        self.assertFalse(parse_awake("  mWakefulness=Asleep"))
        self.assertEqual(parse_playing("state=PlaybackState {state=3, position=1}\nstate=PlaybackState {state=2,"), 1)
        self.assertEqual(parse_front("  mResumedActivity: ActivityRecord{4b0e1e3 u0 com.amazon.tv.launcher/"
                                     ".ui.HomeActivity_vNext t1354}"), "com.amazon.tv.launcher")


if __name__ == "__main__":
    unittest.main()
