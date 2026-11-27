"""e2e scenarios of #77 (alarm_wake, chime_muted, mqtt, settings, kodi_resume) against the fake devices: the dry run
of the CI. Never against a real device; the real runs follow docs/dev/e2e.md."""
import json
import os
import sys
import unittest

from test_e2e_runner import SAVED, Base

from camalert_e2e import profiles
from camalert_e2e.adapters.mqtt import Mqtt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fakes"))
import broker as fake_broker  # noqa: E402


def statuses(res):
    return {s["name"]: s["status"] for s in res["scenarios"]}


class TestNewScenarios(Base):
    def test_alarm_wake_settings_chime_and_restore(self):
        rx = self.receiver()
        res, _data = self.run_on(rx, scenarios=["alarm_wake", "chime_muted", "settings"])
        self.assertEqual(statuses(res), {"alarm_wake": "passed", "chime_muted": "passed", "settings": "passed"},
                         json.dumps(res["scenarios"], indent=1))
        self.assertEqual(res["restore"], [])
        self.assertFalse(rx.standby)  # was on before the run: on again
        self.assertEqual(rx.saved, SAVED)  # alarm_wake and position/size put back
        self.assertIn(("show", "front_door", "photo", "alarm", "test"), rx.ctl.calls)

    def test_alarm_wake_from_standby_returns_to_standby(self):
        rx = self.receiver(standby=True)
        res, _data = self.run_on(rx, options={"nobody_watching": ["boven"], "wake": True}, scenarios=["alarm_wake"])
        self.assertEqual(statuses(res), {"alarm_wake": "passed"}, json.dumps(res, indent=1))
        self.assertTrue(rx.standby)
        self.assertEqual(rx.saved, SAVED)

    def test_alarm_wake_never_on_a_quiet_device(self):
        rx = self.receiver()
        res, _data = self.run_on(rx, options={"nobody_watching": ["boven"], "allow_quiet": True},
                                 scenarios=["alarm_wake"], quiet=True, sleep_hours="03:00-04:00")
        self.assertEqual(statuses(res), {"alarm_wake": "skipped"})
        self.assertNotIn("alarm", [c[3] for c in rx.ctl.calls if c[0] == "show"])

    def test_settings_scenario_needs_the_capability(self):
        rx = self.receiver()
        res, _ = self.run_on(rx, scenarios=["settings"])
        self.assertEqual(statuses(res), {"settings": "passed"})

    def test_mqtt_without_broker_is_skipped(self):
        rx = self.receiver()
        res, _ = self.run_on(rx, scenarios=["mqtt"])
        self.assertEqual(statuses(res), {"mqtt": "skipped"})

    def test_kodi_resume(self):
        kodi = __import__("e2e_fakes").FakeKodi(self.clock)
        self.devs.append(kodi)
        res, _ = self.run_on(kodi, name="kodi_boven", scenarios=["kodi_resume", "chime_muted"],
                             resume_file="special://home/test.mp4")
        self.assertEqual(statuses(res), {"kodi_resume": "passed", "chime_muted": "passed"},
                         json.dumps(res["scenarios"], indent=1))
        self.assertEqual(kodi.playing, 0)  # the test film is stopped again
        kodi2 = __import__("e2e_fakes").FakeKodi(self.clock)
        kodi2.pause_on_show = True  # a player that does not resume: the scenario fails
        self.devs.append(kodi2)
        res, _ = self.run_on(kodi2, name="kodi_boven", scenarios=["kodi_resume"], resume_file="x.mp4")
        self.assertEqual(statuses(res), {"kodi_resume": "failed"})
        res, _ = self.run_on(kodi2, name="kodi_boven", scenarios=["kodi_resume"])
        self.assertEqual(statuses(res), {"kodi_resume": "skipped"})


class TestMqttAdapter(unittest.TestCase):
    def test_publish_reaches_the_broker(self):
        with fake_broker.Broker(user="e2e", password="pw") as b:
            Mqtt("127.0.0.1", b.port, "e2e", "pw").show("node1", cam="garden", sec=10)
            m = b.wait_for(lambda m: m.topic == "camalert/node1/show")
            self.assertEqual(json.loads(m.payload), {"cam": "garden", "sec": 10})
        with fake_broker.Broker(user="e2e", password="pw") as b:
            with self.assertRaises(Exception):
                Mqtt("127.0.0.1", b.port, "e2e", "wrong", timeout=2).show("node1", cam="garden")

    def test_profile_file_mqtt_section(self):
        devs, ha = profiles.parse({"devices": {"x": {"type": "kodi", "host": "192.0.2.5"}},
                                   "mqtt": {"host": "192.0.2.6", "user_env": "MQTT_USER"}})
        self.assertEqual(ha["mqtt"]["prefix"], "camalert")
        with self.assertRaises(profiles.ProfileError):
            profiles.parse({"devices": {"x": {"type": "kodi", "host": "h"}}, "mqtt": {"host": "h", "password": "x"}})


if __name__ == "__main__":
    unittest.main()
