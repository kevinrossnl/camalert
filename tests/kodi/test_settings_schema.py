"""The Kodi settings (resources/settings.xml and klogic.DEFAULTS/CHOICES/RANGES) against the settings schema (#38).

Differences that the Kodi round of #39 removes are listed in KNOWN (a fixed one makes its entry stale)."""
import os
import re
import unittest
import xml.etree.ElementTree as ET

import _paths
import schemacheck

ACTIONS = {"choose_camera", "devices", "diagnostics", "events", "show_mosaic", "show_tour", "test"}  # buttons
HIDDEN = {"mqtt_password", "ptz_password", "token"}
# schema level -> Kodi <level> (0 basic, 1 standard = Kodi's default view, 2 advanced, 4 internal/hidden), #46
KODI_LEVELS = {"basic": 0, "advanced": 1, "expert": 2, "internal": 4}
ACTION_LEVELS = {"choose_camera": 0, "test": 0, "diagnostics": 0, "events": 0, "show_mosaic": 1, "show_tour": 1,
                 "devices": 1}
# (schema id, field) -> issue. Empty since the Kodi round of #39 (settings.xml = schema version 2); a new
# difference must be fixed or listed here with its issue.
KNOWN = {}


def kodi_settings():
    tree = ET.parse(os.path.join(_paths.KODI_ADDON, "resources", "settings.xml"))
    out = {}
    for s in tree.iter("setting"):
        sid, kind = s.get("id"), s.get("type")
        if kind == "action":
            continue
        d = s.find("default")
        text = (d.text or "") if d is not None else ""
        con = s.find("constraints")
        opts = tuple(o.text for o in con.iter("option")) if con is not None else ()
        if kind == "boolean":
            f = {"type": "bool", "default": text == "true"}
        elif kind == "integer":
            f = {"type": "int", "default": int(text)}
            for tag, key in (("minimum", "min"), ("maximum", "max"), ("step", "step")):
                if con is not None and con.find(tag) is not None:
                    f[key] = int(con.find(tag).text)
        elif kind == "time":
            f = {"type": "time", "default": text}
        elif opts:
            f = {"type": "choice", "default": text, "choices": opts}
        else:
            hidden = s.find("control/hidden")
            f = {"type": "password" if hidden is not None and hidden.text == "true" and sid != "token" else "text",
                 "default": text}
        f["kodi_label"] = int(s.get("label"))
        out[sid] = f
    return out


def english():
    path = os.path.join(_paths.KODI_ADDON, "resources", "language", "resource.language.en_gb", "strings.po")
    with open(path, encoding="utf-8") as f:
        return {int(m.group(1)): m.group(2) for m in re.finditer(r'msgctxt "#(\d+)"\nmsgid "((?:[^"\\]|\\.)*)"', f.read())}


class TestKodiSettingsSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xml = kodi_settings()
        cls.en = english()

    def actual(self):
        out = {}
        for k, f in self.xml.items():
            out[k] = {x: v for x, v in f.items() if x != "kodi_label"}
            out[k]["label"] = self.en.get(f["kodi_label"])
        return out

    def test_settings_xml_matches_the_schema(self):
        schemacheck.check(self, "kodi", self.actual(), KNOWN)

    def test_levels_follow_the_schema(self):
        """#46: Kodi's settings level button (basic / standard / advanced / expert) works; 4 = never shown."""
        tree = ET.parse(os.path.join(_paths.KODI_ADDON, "resources", "settings.xml"))
        got = {s.get("id"): int(s.find("level").text) for s in tree.iter("setting")}
        for s in schemacheck.schema.for_platform("kodi"):
            self.assertEqual(got[s.key("kodi")], KODI_LEVELS[s.level], s.id)
        self.assertEqual({k: got[k] for k in ACTION_LEVELS}, ACTION_LEVELS)
        self.assertEqual(set(got), set(self.xml) | set(ACTION_LEVELS))

    def test_label_ids(self):
        for s in schemacheck.schema.for_platform("kodi"):
            k = s.key("kodi")
            self.assertEqual(self.xml[k]["kodi_label"], s.kodi_label, s.id)

    def test_klogic_defaults_match_settings_xml(self):
        from kodi import stubs
        stubs.install()
        _paths.kodi_package()
        k = _paths.kodi_module("klogic")
        self.assertEqual(set(k.DEFAULTS), set(self.xml))
        for key, value in k.DEFAULTS.items():
            want = self.xml[key]["default"]
            self.assertEqual(value, want, key)
            if key in k.CHOICES:
                self.assertEqual(k.CHOICES[key], self.xml[key]["choices"], key)
            if key in k.RANGES:
                self.assertEqual(k.RANGES[key], (self.xml[key]["min"], self.xml[key]["max"]), key)

    def test_validate_works_with_kodi_keys(self):
        clean, problems = schemacheck.schema.validate({"duration": "999", "refresh": "a=1", "mode": "live"}, "kodi")
        self.assertEqual((clean["duration"], clean["refresh"], clean["mode"]), (30, "a=1", "live"))
        self.assertEqual(problems, ["duration"])


if __name__ == "__main__":
    unittest.main()
