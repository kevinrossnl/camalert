"""The Enigma2 settings (`_add()` in __init__.py and the setup screen) against the settings schema (#38).

Differences that the Enigma2 round of #39 removes are listed in KNOWN (a fixed one makes its entry stale)."""
import os
import unittest

import _paths
import schemacheck
from enigma2.harness import e2fake

_paths.tools()
from strings import strings  # noqa: E402

TYPES = {"ConfigYesNo": "bool", "ConfigSelection": "choice", "ConfigSelectionNumber": "int", "ConfigNumber": "int",
         "ConfigText": "text", "ConfigPassword": "password", "ConfigClock": "time"}
# (schema id, field) -> issue. What the Enigma2 player still has to change for schema version 2 (#39):
KNOWN = {
    ("chime", "type"): "#39",            # Enigma2: on/off (high + alarm); schema: off / high / all (schema.migrate)
    ("chime", "default"): "#39",
    ("foscam_enabled", "key"): "#39",    # Enigma2 key foscam_poll
    ("foscam_enabled", "default"): "#39",  # Enigma2 polls by default; schema: off until devices are configured
    ("foscam_priority", "key"): "#39",   # Enigma2 key device_priority
    ("foscam_priority", "choices"): "#39",  # Enigma2 has no 'alarm' for Foscam
    ("frigate_priority", "choices"): "#39",  # Enigma2 has no 'alarm' for Frigate
    ("skip_playing", "missing"): "#39",  # off / video / all replaces the yes/no skip_media
    ("skip_media", "extra"): "#39",
    ("frigate_mode", "missing"): "#39",  # triggers get their own display mode, duration and Foscam interval
    ("frigate_seconds", "missing"): "#39",
    ("foscam_interval", "missing"): "#39",
    ("foscam_mode", "missing"): "#39",
    ("foscam_seconds", "missing"): "#39",
}
# shown through a picker entry (own name / per camera), not as the setting itself
PICKERS = {"titles", "orientation", "refresh"}


def enigma2_settings():
    """{key: fields} from the plugin's config plus the labels of the setup screen (all dependencies on)."""
    env = e2fake.install("openatv")
    try:
        c = env.config.plugins.camalert
        out = {}
        for name, el in c.content.items.items():
            kind = type(el).__name__
            d = {"type": TYPES[kind]}
            if kind == "ConfigClock":
                d["default"] = "%02d:%02d" % tuple(el.default if isinstance(el.default, list) else el._value)
            else:
                d["default"] = el.default
            if kind == "ConfigSelection":
                d["choices"] = tuple(el.choices)
            if kind == "ConfigSelectionNumber":
                d["min"], d["max"], d["step"] = el.choices[0], el.choices[-1], el.choices[1] - el.choices[0]
            out[name] = d
        ids = {id(el): name for name, el in c.content.items.items()}
        session = env.Session()
        env.InfoBar(session)
        env.camalert.plugin.sessionstart(0, session=session)
        shown = set()
        for source in ("go2rtc", "direct"):
            for mode in ("photo", "live", "notify"):
                c.source.value, c.mode.value, c.server.value = source, mode, "https://192.168.1.10:1984"
                c.mqtt_enabled.value = c.frigate_enabled.value = c.limit_hours.value = True
                env.camalert.plugin.main(session)
                for label, el in session.opened[-1]["config"].list:
                    name = ids.get(id(el))
                    if name:
                        out[name]["label"] = label
                        shown.add(name)
        return out, shown
    finally:
        e2fake.uninstall()


class TestEnigma2SettingsSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings, cls.shown = enigma2_settings()

    def test_settings_match_the_schema(self):
        schemacheck.check(self, "enigma2", self.settings, KNOWN)

    def test_every_visible_setting_is_on_the_setup_screen(self):
        missing = [s.id for s in schemacheck.schema.for_platform("enigma2")
                   if s.level != "internal" and s.id not in PICKERS and s.key("enigma2") not in self.shown
                   and (s.id, "missing") not in KNOWN]
        self.assertEqual(missing, [])

    def test_labels_and_help_are_translatable(self):
        msgids = set(strings())
        missing = [(s.id, text) for s in schemacheck.schema.for_platform("enigma2") if s.level != "internal"
                   for text in (s.label, s.help) if text and text not in msgids]
        self.assertEqual(missing, [], "schema label/help that the plugin does not have as msgid")

    def test_known_entries_are_real(self):
        ids = {s.id for s in schemacheck.schema.SETTINGS}
        for (sid, field), issue in KNOWN.items():
            if field != "extra":
                self.assertIn(sid, ids)
            self.assertRegex(issue, r"^#\d+$")
        self.assertTrue(os.path.exists(os.path.join(_paths.ENIGMA2, "__init__.py")))


if __name__ == "__main__":
    unittest.main()
