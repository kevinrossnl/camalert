"""Settings screens (#130): first screen = basic settings, one screen per section, settings that only matter
while another one is on are hidden otherwise (DEPENDS), expert settings only after "More settings"."""
import unittest

import _paths

_paths.core()
from camalert_core import schema, settingsui as ui  # noqa: E402


class TestSettingsUi(unittest.TestCase):
    def test_depends_points_at_real_settings_without_cycles(self):
        for child, (parent, allowed) in ui.DEPENDS.items():
            self.assertIn(child, schema.BY_ID, child)
            self.assertIn(parent, schema.BY_ID, parent)
            self.assertTrue(allowed, child)
            p = schema.BY_ID[parent]
            for v in allowed:
                if p.type == "bool":
                    self.assertIsInstance(v, bool, child)
                elif p.choices:
                    self.assertIn(v, p.choices, child)
            seen, x = set(), child
            while x in ui.DEPENDS:
                self.assertNotIn(x, seen, "cycle at %s" % child)
                seen.add(x)
                x = ui.DEPENDS[x][0]

    def test_every_setting_is_on_a_screen(self):
        for platform in schema.PLATFORMS:
            everything = {}
            for s in schema.for_platform(platform):  # parents on: every dependent shows
                if s.type == "bool":
                    everything[s.id] = True
            everything.update(source="go2rtc", mode="photo", server="https://192.168.1.10:1984")
            shown = {s.id for s in ui.main_settings(platform, everything)}
            for sec in ui.sections(platform):
                shown |= {s.id for s in ui.section_settings(sec, platform, everything, expert=True)}
            for mode in ("live", "notify"):
                shown |= {s.id for sec in ui.sections(platform)
                          for s in ui.section_settings(sec, platform, dict(everything, mode=mode), True)}
            shown |= {s.id for s in ui.main_settings(platform, dict(everything, source="direct"))}
            shown |= {s.id for sec in ui.sections(platform)
                      for s in ui.section_settings(sec, platform, dict(everything, source="direct"), True)}
            missing = [s.id for s in schema.for_platform(platform) if s.level != "internal" and s.id not in shown]
            self.assertEqual(missing, [], platform)

    def test_first_screen_is_short(self):
        for platform in schema.PLATFORMS:
            self.assertLessEqual(len(ui.main_settings(platform, {})) + len(ui.sections(platform)), 22, platform)

    def test_applies(self):
        v = {}
        self.assertTrue(ui.applies("server", v))
        self.assertFalse(ui.applies("server", {"source": "direct"}))
        self.assertFalse(ui.applies("frigate_labels", {"frigate_enabled": True}))  # needs MQTT too
        self.assertTrue(ui.applies("frigate_labels", {"frigate_enabled": True, "mqtt_enabled": True}))
        self.assertFalse(ui.applies("from_time", v))
        self.assertTrue(ui.applies("from_time", {"limit_hours": True}))
        self.assertTrue(ui.applies("pause_tv", {"mode": "notify"}))
        self.assertFalse(ui.applies("verify_ssl", {"server": "http://192.168.1.10:1984"}))
        self.assertTrue(ui.applies("verify_ssl", {"server": "https://192.168.1.10:1984"}))
        self.assertTrue(ui.applies("verify_ssl", {"source": "direct"}))
        self.assertTrue(ui.applies("unknown_setting", v))

    def test_expert_only_with_more_settings(self):
        plain = {s.id for s in ui.section_settings("log", "enigma2", {})}
        more = {s.id for s in ui.section_settings("log", "enigma2", {}, expert=True)}
        self.assertNotIn("log_syslog", plain)
        self.assertIn("log_syslog", more)
        self.assertEqual(ui.hidden_expert("log", "enigma2", {}), len(more - plain))
        self.assertFalse([s for s in ui.section_settings("display", "enigma2", {}) if s.level == "basic"])

    def test_summary(self):
        self.assertEqual(ui.section_summary("triggers", "enigma2", {}), ([], 0))
        on, changed = ui.section_summary("triggers", "enigma2", {"unifi_enabled": True, "unifi_seconds": 60})
        self.assertEqual((on, changed), (["UniFi Protect events"], 1))
        self.assertEqual(ui.section_summary("display", "enigma2", {"tour_interval": 12})[1], 1)


if __name__ == "__main__":
    unittest.main()
