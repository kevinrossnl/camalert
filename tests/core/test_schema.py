"""camalert_core.schema: the shared settings schema (#38, #7)."""
import unittest

import _paths

_paths.core()
from camalert_core import schema  # noqa: E402

# UI guideline (#2): the basic level
BASIC = {"enabled", "source", "server", "camera", "mode", "duration", "position", "size", "dnd", "limit_hours",
         "from_time", "until_time"}


class TestSchema(unittest.TestCase):
    def test_entries_are_well_formed(self):
        ids = [s.id for s in schema.SETTINGS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsInstance(schema.SCHEMA_VERSION, int)
        for s in schema.SETTINGS:
            with self.subTest(setting=s.id):
                self.assertIn(s.section, schema.SECTIONS)
                self.assertIn(s.level, schema.LEVELS)
                self.assertIn(s.type, schema.TYPES)
                self.assertTrue(s.platforms and set(s.platforms) <= set(schema.PLATFORMS))
                self.assertTrue(set(s.keys) <= set(s.platforms))
                self.assertEqual(schema.coerce(s, s.default), s.default, "default must be valid")
                if s.type == "choice":
                    self.assertIn(s.default, s.choices)
                if s.type == "int" and s.min is not None:
                    self.assertLessEqual(s.min, s.default)
                    self.assertLessEqual(s.default, s.max)
                    if s.step:
                        self.assertEqual((s.default - s.min) % s.step, 0)
                if s.level != "internal":
                    self.assertTrue(s.label, "needs a label")

    def test_sections_follow_the_guideline_order(self):
        order = [schema.SECTIONS.index(s.section) for s in schema.SETTINGS]
        self.assertEqual(order, sorted(order))

    def test_basic_level(self):
        self.assertEqual({s.id for s in schema.SETTINGS if s.level == "basic"}, BASIC)

    def test_defaults_and_keys(self):
        e2, kodi = schema.defaults("enigma2"), schema.defaults("kodi")
        self.assertEqual(e2["duration"], 30)
        self.assertIn("foscam_enabled", e2)    # Enigma2 key since #39
        self.assertIn("refresh", kodi)         # Kodi key since #39 (was refresh_map)
        self.assertNotIn("bouquet_name", kodi)
        self.assertEqual(schema.BY_ID["foscam_enabled"].key("kodi"), "foscam_enabled")

    def test_validate(self):
        clean, problems = schema.validate({"enabled": "false", "duration": "45", "mode": "nonsense", "from_time": "7:5",
                                           "until_time": "25:00", "token": " abc ", "mqtt_password": " pw ",
                                           "chime": "high", "unknown": 1, "rtsp_port": "x"})
        self.assertEqual((clean["enabled"], clean["duration"], clean["mode"]), (False, 45, "photo"))
        self.assertEqual((clean["from_time"], clean["until_time"]), ("07:05", "23:00"))
        self.assertEqual((clean["token"], clean["mqtt_password"], clean["chime"]), ("abc", " pw ", "high"))
        self.assertNotIn("unknown", clean)
        self.assertEqual(sorted(problems), ["mode", "rtsp_port", "until_time"])
        self.assertEqual(schema.validate({"duration": 301})[1], ["duration"])
        self.assertEqual(schema.validate({"enabled": "maybe"})[1], ["enabled"])
        self.assertEqual(schema.validate({"enabled": True, "http_port": 80})[1], ["http_port"])
        self.assertEqual(schema.validate({"from_time": "ab:cd"})[1], ["from_time"])

    def test_target_semantics(self):
        """#39: the same meaning, default, range and step on every player."""
        b = schema.BY_ID
        self.assertEqual(schema.SCHEMA_VERSION, 2)
        self.assertEqual((b["chime"].choices, b["chime"].default), (("off", "high", "all"), "off"))
        self.assertEqual((b["skip_playing"].choices, b["skip_playing"].platforms), (("off", "video", "all"), schema.PLATFORMS))
        self.assertNotIn("skip_media", b)
        for sid in ("frigate_priority", "foscam_priority"):
            self.assertEqual(b[sid].choices, ("normal", "high", "alarm"))
        self.assertFalse(b["foscam_enabled"].default)
        self.assertTrue(b["verify_ssl"].default)
        for sid in ("duration", "frigate_seconds", "foscam_seconds"):
            self.assertEqual((b[sid].min, b[sid].max, b[sid].step), (5, 300, 5), sid)
        self.assertEqual(b["live_volume"].step, 10)
        self.assertEqual((b["http_port"].min, b["http_port"].max), (1024, 65535))
        for sid in ("frigate_mode", "frigate_seconds"):
            self.assertEqual(b[sid].platforms, schema.PLATFORMS, sid)
        for sid in ("foscam_interval", "foscam_mode", "foscam_seconds"):
            self.assertEqual(b[sid].platforms, ("enigma2", "kodi"), sid)
        e2_kodi = set(schema.for_platform("enigma2")) | set(schema.for_platform("kodi"))
        platform_only = sorted(s.id for s in e2_kodi if not {"enigma2", "kodi"} <= set(s.platforms))
        self.assertEqual(platform_only, ["auto_bouquet", "bouquet_name", "bouquet_position", "camera_file",
                                         "event_folder", "live_format", "picons", "ptz_password", "ptz_user",
                                         "skip_recording", "update_check", "update_checked", "update_seen"])

    def test_android_tv_platform(self):
        """#67: Android TV is a platform of the schema; every Kodi setting it lacks has a reason in MISSING, its own
        defaults are in Setting.defaults (with a reason) and are used by defaults() and validate()."""
        self.assertIn("androidtv", schema.PLATFORMS)
        kodi = {s.id for s in schema.for_platform("kodi")}
        atv = {s.id for s in schema.for_platform("androidtv")}
        self.assertTrue(atv <= kodi | {s.id for s in schema.SETTINGS if s.platforms == ("androidtv",)})
        self.assertEqual(set(schema.MISSING["androidtv"]), kodi - atv)
        self.assertEqual(set(schema.MISSING), {"androidtv"})
        own = {(p, s.id) for s in schema.SETTINGS for p in s.defaults}
        self.assertEqual(own, {(p, sid) for p, d in schema.DEFAULT_REASONS.items() for sid in d})
        for p, sid in own:
            self.assertIn(p, schema.BY_ID[sid].platforms, sid)
            s = schema.BY_ID[sid]
            self.assertEqual(schema.coerce(s, s.default_for(p)), s.default_for(p))
        lv = schema.BY_ID["live_volume"]
        self.assertEqual((lv.default, lv.default_for("androidtv"), lv.default_for("kodi"), lv.default_for()),
                         (100, 0, 100, 100))
        self.assertEqual(schema.defaults("androidtv")["live_volume"], 0)
        self.assertEqual(schema.defaults("kodi")["live_volume"], 100)
        self.assertEqual(schema.validate({}, "androidtv")[0]["live_volume"], 0)
        self.assertEqual(schema.validate({"live_volume": "x"}, "androidtv")[0]["live_volume"], 0)
        self.assertEqual(schema.validate({})[0]["live_volume"], 100)

    def test_migrate(self):
        e2 = schema.migrate({"foscam_poll": "True", "device_priority": "high", "chime": True, "skip_media": "True",
                             "duration": "30"}, "enigma2")
        self.assertEqual(e2, {"foscam_enabled": "True", "foscam_priority": "high", "chime": "high",
                              "skip_playing": "video", "duration": "30"})
        clean, problems = schema.validate(e2)
        self.assertEqual((clean["foscam_enabled"], clean["chime"], clean["skip_playing"], problems),
                         (True, "high", "video", []))
        self.assertEqual(schema.migrate({"chime": "false", "skip_media": False}, "enigma2"),
                         {"chime": "off", "skip_playing": "off"})
        self.assertEqual(schema.migrate({"skip_media": True, "skip_playing": "all"}, "enigma2"), {"skip_playing": "all"})
        kodi = schema.migrate({"live_resume": "false", "refresh_map": "a=5", "refresh": "b=9", "chime": "all"}, "kodi")
        self.assertEqual(kodi, {"live_return": "false", "refresh": "b=9", "chime": "all"})
        self.assertEqual(schema.migrate({"x": 1}, "other"), {"x": 1})

    def test_every_id_appears_once_per_platform(self):
        for p in schema.PLATFORMS:
            keys = [s.key(p) for s in schema.for_platform(p)]
            self.assertEqual(len(keys), len(set(keys)), p)
            self.assertIn("Setting('enabled')", repr(schema.for_platform(p)))


if __name__ == "__main__":
    unittest.main()
