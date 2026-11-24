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
        self.assertIn("foscam_poll", e2)       # Enigma2 key until #39
        self.assertIn("refresh_map", kodi)     # Kodi key until #39
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

    def test_every_id_appears_once_per_platform(self):
        for p in schema.PLATFORMS:
            keys = [s.key(p) for s in schema.for_platform(p)]
            self.assertEqual(len(keys), len(set(keys)), p)
            self.assertIn("Setting('enabled')", repr(schema.for_platform(p)))


if __name__ == "__main__":
    unittest.main()
