"""Enigma2 settings saved by version 1 load as settings schema version 2 (#39), and the version-2 rules work."""
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestMigration(unittest.TestCase):
    def tearDown(self):
        e2fake.uninstall()

    def load(self, stored):
        env = e2fake.install("openatv", stored)
        return env, env.config.plugins.camalert

    def test_version1_settings_move_to_the_new_keys(self):
        env, c = self.load({"device_priority": "high", "chime": "true", "skip_media": "true", "dnd": "true"})
        self.assertTrue(c.foscam_enabled.value)  # version 1 polled by default: an existing install keeps it
        self.assertEqual(c.foscam_priority.value, "high")
        self.assertEqual(c.chime.value, "high")
        self.assertEqual(c.skip_playing.value, "video")
        self.assertTrue(c.dnd.value)
        for old in ("foscam_poll", "device_priority", "skip_media"):
            self.assertNotIn(old, env.stored)  # Enigma2 writes every stored value back
        self.assertEqual(env.stored["foscam_enabled"], "true")

    def test_version1_foscam_off_stays_off(self):
        _env, c = self.load({"foscam_poll": "false", "server": "http://192.168.1.10:1984"})
        self.assertFalse(c.foscam_enabled.value)

    def test_new_install_has_the_version2_defaults(self):
        env, c = self.load({})
        self.assertFalse(c.foscam_enabled.value)
        self.assertEqual((c.chime.value, c.skip_playing.value, c.foscam_interval.value), ("off", "off", 2))
        self.assertTrue(c.foscam_enabled.save_forced)  # the marker is always written
        self.assertEqual(env.stored, {})

    def test_no_default_go2rtc_address(self):
        """#73: a new install has no go2rtc address (nothing is contacted); a saved one is kept as it is."""
        env, c = self.load({})
        self.assertEqual(c.server.value, "")
        self.assertNotIn("server", env.stored)
        _env, c = self.load({"server": "http://192.168.1.10:1984"})
        self.assertEqual(c.server.value, "http://192.168.1.10:1984")

    def test_version2_settings_are_not_migrated_again(self):
        _env, c = self.load({"foscam_enabled": "false", "chime": "all", "skip_playing": "all"})
        self.assertFalse(c.foscam_enabled.value)
        self.assertEqual((c.chime.value, c.skip_playing.value), ("all", "all"))

    def test_broken_values_fall_back_to_the_default(self):
        _env, c = self.load({"foscam_enabled": "false", "chime": "loud", "frigate_seconds": "7"})
        self.assertEqual((c.chime.value, c.frigate_seconds.value), ("off", 30))


class TestVersion2Rules(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.c = self.env.config.plugins.camalert
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.ctl = self.env.camalert.display.Controller(self.session)

    def tearDown(self):
        e2fake.uninstall()

    def test_chime(self):
        wanted = self.env.camalert.display.chime_wanted
        self.assertEqual([wanted("off", p) for p in ("normal", "high", "alarm")], [False, False, False])
        self.assertEqual([wanted("high", p) for p in ("normal", "high", "alarm")], [False, True, True])
        self.assertEqual([wanted("all", p) for p in ("normal", "high", "alarm")], [True, True, True])

    def play(self, ref):
        self.session.current_ref = self.env.camalert.display.eServiceReference(ref) if ref else None

    def test_not_while_playing(self):
        tv = "1:0:19:283D:3FB:1:C00000:0:0:0:"
        video = "4097:0:0:0:0:0:0:0:0:0:/media/hdd/movie/film.ts"
        camera = self.env.camalert.services.service_ref("rtsp://192.168.1.10:8554/front_door", "Front door")
        cases = {("off", tv): False, ("video", tv): False, ("video", video): True, ("all", tv): True,
                 ("all", video): True, ("all", camera): False, ("all", None): False}
        for (setting, ref), want in cases.items():
            self.play(ref)
            self.assertEqual(self.ctl.playing(setting), want, (setting, ref))
            self.c.skip_playing.value = setting
            self.assertEqual(self.ctl.blocked("normal", "front_door"), want, (setting, ref))
            self.assertFalse(self.ctl.blocked("high", "front_door"))

    def test_trigger_settings(self):
        self.c.frigate_mode.value, self.c.frigate_seconds.value = "notify", 60
        self.c.foscam_enabled.value, self.c.foscam_priority.value = True, "alarm"
        s = self.env.camalert.display.trigger_settings()
        self.assertEqual((s["frigate_mode"], s["frigate_seconds"]), ("notify", 60))
        self.assertEqual((s["foscam_enabled"], s["foscam_priority"], s["foscam_seconds"]), (True, "alarm", 30))

    def test_foscam_interval(self):
        self.assertEqual(self.ctl.poll_interval(), 2)
        self.c.foscam_interval.value = 10
        self.assertEqual(self.ctl.poll_interval(), 10)
        self.ctl.poll_timer.fire()
        self.assertEqual(self.ctl.poll_timer.interval, 10000)


if __name__ == "__main__":
    unittest.main()
