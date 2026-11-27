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
                               ("seconds", 30), ("label", ""), ("presence", []), ("phone_notify", ""),
                               ("phone_camera", "")],
    "camalert_motion.yaml": [("motion", None), ("players", None), ("cameras", ""), ("mode", "photo"),
                             ("several", "strip"), ("seconds", 30), ("label", ""), ("when", "armed"),
                             ("alarm_panel", ""), ("from_time", "22:00:00"), ("until_time", "07:00:00"),
                             ("presence", [])],
    "camalert_alarm.yaml": [("alarm_panel", None), ("players", None), ("camera", None), ("mode", "live"),
                            ("seconds", 300), ("label", "Alarm")],
    "camalert_button.yaml": [("button", "green"), ("players", None), ("camera", ""), ("action", None)],
    "camalert_doorbell_webos.yaml": [("doorbell", None), ("players", None), ("camera", None), ("mode", "photo"),
                                     ("seconds", 30), ("label", ""), ("webos_notify", None), ("message", ""),
                                     ("snapshot_camera", ""), ("snapshot_file", "/media/camalert_webos.jpg"),
                                     ("tv", ""), ("snapshot_url", ""), ("presence", []), ("phone_notify", ""),
                                     ("phone_camera", ""), ("webos_live_url", "")],
    "camalert_doorbell_screens.yaml": [("doorbell", None), ("players", None), ("camera", None), ("mode", "photo"),
                                       ("seconds", 30), ("label", ""), ("cast_players", []), ("cast_camera", ""),
                                       ("androidtv_notify", ""), ("androidtv_snapshot_url", ""), ("presence", [])],
}
# option labels = glossary terms (blueprints cannot be translated)
MODE_OPTIONS = [{"label": "Photo window", "value": "photo"}, {"label": "Live view", "value": "live"},
                {"label": "Notification", "value": "notify"}]
PLAYERS_NAME = "Players (receivers / Kodi / Android TV)"  # label only; the key stays frozen (#114)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class TestBlueprints(unittest.TestCase):
    def load(self, path):
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor("!input", lambda l, n: ("INPUT", l.construct_scalar(n)))
        return yaml.load(open(path, encoding="utf-8"), Loader=Loader)

    def test_inputs_declared_and_used(self):
        files = glob.glob(os.path.join(_paths.BLUEPRINTS, "*.yaml"))
        self.assertEqual(len(files), len(FROZEN))
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

    def test_webos_snapshot_not_public(self):
        """#16: the snapshot of the door must not land in www (served without login at /local/)."""
        d = self.load(os.path.join(_paths.BLUEPRINTS, "camalert_doorbell_webos.yaml"))
        default = d["blueprint"]["input"]["snapshot_file"]["default"]
        self.assertNotIn("/www/", default)
        self.assertTrue(default.startswith("/media/"))

    def test_webos_small_snapshot(self):
        """#74: the LG TV refuses pictures over 100 KB; the URL route waits for the Downloader event and falls back
        to text only, and every LG notify step continues on error."""
        path = os.path.join(_paths.BLUEPRINTS, "camalert_doorbell_webos.yaml")
        d = self.load(path)
        inputs = d["blueprint"]["input"]
        self.assertIn("100 KB", inputs["snapshot_url"]["description"])
        self.assertIn("100 KB", inputs["snapshot_camera"]["description"])
        self.assertIn("width=", inputs["snapshot_url"]["description"])
        text = open(path, encoding="utf-8").read()
        for event in ("downloader_download_completed", "downloader_download_failed"):
            self.assertIn("event_type: %s" % event, text)
        self.assertIn("continue_on_timeout: true", text)
        steps = []

        def walk(x):
            if isinstance(x, dict):
                if "action" in x and x["action"] != "camalert.show":
                    steps.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(d["actions"])
        self.assertTrue(steps)
        for step in steps:
            self.assertIs(step.get("continue_on_error"), True, step["action"])

    def test_presence_is_optional_and_never_blocks_by_default(self):
        """#75: 'only when someone is home' is a new optional input at the end; empty (the default) = always."""
        for name in ("camalert_doorbell.yaml", "camalert_doorbell_webos.yaml", "camalert_motion.yaml"):
            d = self.load(os.path.join(_paths.BLUEPRINTS, name))
            inputs = d["blueprint"]["input"]
            self.assertEqual(inputs["presence"]["default"], [], name)
            self.assertEqual(inputs["presence"]["selector"]["entity"]["filter"],
                             [{"domain": ["person", "device_tracker", "group", "zone"]}], name)
            self.assertIn("ents | count == 0", d["variables"]["someone_home"], name)

    def test_phone_is_not_gated_by_presence(self):
        """#14: the phone notification is a separate top-level step, not behind the presence gate and not behind a
        delay (live view, #94), so it also arrives when nobody is home; empty phone_notify (the default) = nothing."""
        for name in ("camalert_doorbell.yaml", "camalert_doorbell_webos.yaml"):
            d = self.load(os.path.join(_paths.BLUEPRINTS, name))
            phone = [i for i, a in enumerate(d["actions"])
                     if a.get("if", [{}])[0].get("value_template") == "{{ phone_notify_in | trim | length > 0 }}"]
            self.assertEqual(len(phone), 1, name)
            last = d["actions"][phone[0]]
            # nothing before it waits (a delay would hold the phone notification back)
            before = str(d["actions"][:phone[0]])
            self.assertNotIn("delay", before, name)
            self.assertNotIn("wait_for_trigger", before, name)
            self.assertNotIn("someone_home", str(last), name)
            self.assertIs(last["then"][0]["continue_on_error"], True, name)
            self.assertEqual(d["blueprint"]["input"]["phone_camera"]["selector"]["entity"]["filter"],
                             [{"domain": "camera"}], name)

    def test_other_screens_end_their_live_view(self):
        """#16/#93/#94: a live view on another screen is ended after the duration (Chromecast: media_stop; LG TV:
        back to its scene), and every step on another screen continues on error."""
        d = self.load(os.path.join(_paths.BLUEPRINTS, "camalert_doorbell_screens.yaml"))
        cast = d["actions"][-1]["then"]
        self.assertEqual([s.get("action") or "delay" for s in cast],
                         ["camera.play_stream", "delay", "media_player.media_stop"])
        w = self.load(os.path.join(_paths.BLUEPRINTS, "camalert_doorbell_webos.yaml"))
        live = w["actions"][-1]["then"]
        self.assertEqual([s.get("action") or "delay" for s in live],
                         ["scene.create", "webostv.command", "delay", "scene.turn_on"])
        for step in cast + live:
            if "action" in step:
                self.assertIs(step.get("continue_on_error"), True, step["action"])

