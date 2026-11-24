import glob
import os
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

import _paths  # noqa: E402


# The v1.x contract of the blueprints (#45): input keys in this order, with these defaults (None = no default).
# Changing this table is a breaking change for everyone's automations: only add optional inputs, never rename,
# remove or reorder before 2.0 (homeassistant/blueprints/README.md).
FROZEN = {
    "camalert_doorbell.yaml": [("doorbell", None), ("players", None), ("camera", None), ("mode", "photo"),
                               ("seconds", 30), ("label", "")],
    "camalert_motion.yaml": [("motion", None), ("players", None), ("cameras", ""), ("mode", "photo"),
                             ("several", "strip"), ("seconds", 30), ("label", ""), ("when", "armed"),
                             ("alarm_panel", ""), ("from_time", "22:00:00"), ("until_time", "07:00:00")],
    "camalert_alarm.yaml": [("alarm_panel", None), ("players", None), ("camera", None), ("mode", "live"),
                            ("seconds", 300), ("label", "Alarm")],
    "camalert_button.yaml": [("button", "green"), ("players", None), ("camera", ""), ("action", None)],
}
# option labels = glossary terms (blueprints cannot be translated)
MODE_OPTIONS = [{"label": "Photo window", "value": "photo"}, {"label": "Live view", "value": "live"},
                {"label": "Notification", "value": "notify"}]
PLAYERS_NAME = "Players (receivers / Kodi)"


@unittest.skipIf(yaml is None, "PyYAML not installed")
class TestBlueprints(unittest.TestCase):
    def load(self, path):
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor("!input", lambda l, n: ("INPUT", l.construct_scalar(n)))
        return yaml.load(open(path, encoding="utf-8"), Loader=Loader)

    def test_inputs_declared_and_used(self):
        files = glob.glob(os.path.join(_paths.BLUEPRINTS, "*.yaml"))
        self.assertEqual(len(files), 4)
        for f in files:
            d = self.load(f)
            used = set()

            def walk(x):
                if isinstance(x, tuple) and x[0] == "INPUT":
                    used.add(x[1])
                elif isinstance(x, dict):
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
            walk({k: v for k, v in d.items() if k != "blueprint"})
            self.assertEqual(used, set(d["blueprint"]["input"]), f)
            self.assertIn("camalert", str(d["actions"]) + str(d["triggers"]), f)
            self.assertTrue(d["blueprint"]["source_url"].endswith(os.path.basename(f)), f)

    def test_inputs_are_frozen(self):
        """#45: names, order and defaults of the inputs are the v1.x contract."""
        files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(_paths.BLUEPRINTS, "*.yaml")))
        self.assertEqual(files, sorted(FROZEN))
        for name, want in FROZEN.items():
            inputs = self.load(os.path.join(_paths.BLUEPRINTS, name))["blueprint"]["input"]
            got = [(k, v.get("default")) for k, v in inputs.items()]
            self.assertEqual(got, want, name)
            self.assertEqual(inputs["players"]["name"], PLAYERS_NAME, name)
            self.assertEqual(inputs["players"]["selector"]["device"], {"integration": "camalert", "multiple": True})
            if "mode" in inputs:
                self.assertEqual(inputs["mode"]["selector"]["select"]["options"], MODE_OPTIONS, name)
            if "seconds" in inputs:
                self.assertEqual(inputs["seconds"]["selector"]["number"],
                                 {"min": 5, "max": 300, "step": 5, "unit_of_measurement": "s"}, name)

    def test_inputs_documented(self):
        readme = open(os.path.join(_paths.BLUEPRINTS, "README.md"), encoding="utf-8").read()
        for keys in FROZEN.values():
            for key, _default in keys:
                self.assertIn("`%s`" % key, readme, key)
