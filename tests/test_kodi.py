"""Kodi add-on (service.camalert): pure helpers, the HTTP API handler, the built zip and its metadata.
Runs without Kodi: tests/kodi_stubs.py stands in for the xbmc modules."""
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ADDON = os.path.join(ROOT, "kodi", "service.camalert")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_kodi  # noqa: E402
import kodi_stubs  # noqa: E402

LANGS = ("en_gb", "nl_nl", "de_de", "fr_fr", "it_it", "pl_pl")


def po_strings(lang):
    with open(os.path.join(ADDON, "resources", "language", "resource.language.%s" % lang, "strings.po"),
              encoding="utf-8") as f:
        text = f.read()
    return {int(m.group(1)): (m.group(2), m.group(3)) for m in
            re.finditer(r'msgctxt "#(\d+)"\nmsgid "((?:[^"\\]|\\.)*)"\nmsgstr "((?:[^"\\]|\\.)*)"', text)}


class Built(object):
    """Builds the zip once and imports the add-on package from it (as Kodi would)."""
    tmp = None

    @classmethod
    def get(cls):
        if cls.tmp is None:
            cls.tmp = tempfile.mkdtemp()
            cls.addon_zip, cls.repo_zip, cls.tree = build_kodi.build(cls.tmp, "https://example.invalid/kodi")
            with zipfile.ZipFile(cls.addon_zip) as z:
                z.extractall(cls.tmp)
            cls.profile = os.path.join(cls.tmp, "profile")
            os.makedirs(cls.profile)
            cls.store = kodi_stubs.install(profile=cls.profile)
            sys.path.insert(0, os.path.join(cls.tmp, "service.camalert", "resources", "lib"))
        return cls

    @classmethod
    def module(cls, name):
        cls.get()
        return importlib.import_module("camalert." + name)


def tearDownModule():
    if Built.tmp:
        shutil.rmtree(Built.tmp, ignore_errors=True)


class TestKodiLogic(unittest.TestCase):
    def setUp(self):
        self.k = Built.module("klogic")

    def test_keys(self):
        k = self.k
        self.assertEqual(k.key_action(7), "live")
        self.assertEqual(k.key_action(1), "prev")
        self.assertEqual(k.key_action(2), "next")
        self.assertEqual(k.key_action(92), "close")
        self.assertEqual(k.key_action(88), "pass")
        self.assertEqual(k.key_action(12), "close_pass")
        self.assertEqual(k.forward_builtin(3), "Action(Up)")
        self.assertIsNone(k.forward_builtin(9999))
        self.assertEqual(k.ptz_action(3), "up")
        self.assertEqual(k.ptz_action(184), "zoom_in")
        self.assertEqual(k.ptz_action(6), "zoom_out")
        self.assertEqual(k.ptz_action(7), "home")
        self.assertEqual(k.ptz_action(92), "leave")
        self.assertIsNone(k.ptz_action(88))

    def test_settings(self):
        k = self.k
        s = k.parse_settings({})
        self.assertEqual(s, k.DEFAULTS)
        s = k.parse_settings({"enabled": "false", "duration": "999", "mode": "1", "position": "nonsense",
                              "http_port": "8100", "mqtt_password": " pw with spaces ", "camera": " front_door ",
                              "live_format": "hls", "tour_interval": "abc"})
        self.assertFalse(s["enabled"])
        self.assertEqual(s["duration"], 30)          # out of range -> default
        self.assertEqual(s["mode"], "live")          # spinner index
        self.assertEqual(s["position"], "top_right")
        self.assertEqual(s["http_port"], 8100)
        self.assertEqual(s["mqtt_password"], " pw with spaces ")
        self.assertEqual(s["camera"], "front_door")
        self.assertEqual(s["live_format"], "hls")
        self.assertEqual(s["tour_interval"], 8)

    def test_playing(self):
        k = self.k
        self.assertEqual(k.playing_kind("", False, False), "none")
        self.assertEqual(k.playing_kind("http://x:1984/api/stream.mp4?src=a&camalert=1", False, True), "camera")
        self.assertEqual(k.playing_kind("pvr://channels/tv/All/1.pvr", False, True), "livetv")
        self.assertEqual(k.playing_kind("/media/film.mkv", False, True), "video")
        self.assertFalse(k.blocked_by_playing("off", "video"))
        self.assertTrue(k.blocked_by_playing("video", "video"))
        self.assertFalse(k.blocked_by_playing("video", "livetv"))
        self.assertTrue(k.blocked_by_playing("all", "livetv"))
        self.assertEqual(k.resume_plan("/f.mkv", 100, "video"), {"file": "/f.mkv", "seek": 98.0, "paused": False})
        self.assertEqual(k.resume_plan("pvr://channels/tv/1.pvr", 50, "livetv", True)["seek"], 0.0)
        self.assertIsNone(k.resume_plan("", 0, "video"))
        self.assertIsNone(k.resume_plan("x", 0, "camera"))

    def test_urls(self):
        k = self.k
        self.assertEqual(k.live_url("http://h:1984/", "voor deur"), "http://h:1984/api/stream.mp4?src=voor%20deur&camalert=1")
        self.assertEqual(k.live_url("http://h:1984", "a", "hls"), "http://h:1984/api/stream.m3u8?src=a&camalert=1")
        self.assertEqual(k.live_url("http://h:1984", "a", "rtsp", 8554), "rtsp://h:8554/a")
        self.assertIsNone(k.live_url("", "a"))
        self.assertEqual(k.live_mime("http://h/api/stream.mp4?src=a"), "video/mp4")
        self.assertEqual(k.live_mime("http://h/api/stream.m3u8?src=a"), "application/vnd.apple.mpegurl")
        self.assertEqual(k.live_mime("rtsp://h/a"), "")

    def test_misc(self):
        k = self.k
        self.assertEqual(k.kodi_volume(80, 50), 40)
        self.assertEqual(k.kodi_volume(80, 100), 80)
        self.assertEqual(k.kodi_volume(80, 250), 80)
        self.assertEqual(k.node_from_mac("AA:BB:CC:00:11:22", "x"), "aabbcc001122")
        self.assertTrue(k.node_from_mac("", "Kodi Living"))
        self.assertEqual(k.frame_name("/t/f", 5), ("/t/f_5.jpg", "/t/f_2.jpg"))
        d = k.with_default_login({"a": {"user": "", "password": ""}, "b": {"user": "u", "password": "p"}}, "x", "y")
        self.assertEqual((d["a"]["user"], d["a"]["password"]), ("x", "y"))
        self.assertEqual((d["b"]["user"], d["b"]["password"]), ("u", "p"))


class FakeController(object):
    def __init__(self):
        self.calls = []
        self.names, self.names_at = [], 0

    def show(self, *a):
        self.calls.append(("show",) + a)
        return "show"

    def hide(self):
        self.calls.append(("hide",))

    def mosaic(self, cam, sec):
        self.calls.append(("mosaic", cam, sec))
        return "show"

    def tour(self, cam, interval):
        self.calls.append(("tour", cam, interval))
        return "error"

    def status(self):
        return {"window": None, "live": None, "paused": False, "dnd": False}

    def set_dnd(self, on):
        self.calls.append(("dnd", on))


class TestKodiApi(unittest.TestCase):
    """Same answers as the Enigma2 plugin's server.py."""

    def setUp(self):
        self.server = Built.module("server")
        self.s = Built.module("klogic").parse_settings({"camera": "front_door"})

    def handle(self, path, args=None, ip="192.168.1.5", header=None, **settings):
        s = dict(self.s, **settings)
        ctl = FakeController()
        code, out = self.server.handle(ctl, path, args or {}, ip, header, s)
        return code, out, ctl

    def test_access(self):
        self.assertEqual(self.handle("/camalert/hide", ip="8.8.8.8")[:2], (403, {"result": False, "error": "forbidden"}))
        self.assertEqual(self.handle("/camalert/hide", ip="8.8.8.8", allow="any")[0], 200)
        self.assertEqual(self.handle("/camalert/hide", header="bad", token="secret")[0], 403)
        self.assertEqual(self.handle("/camalert/hide", {"token": "secret"}, token="secret")[0], 200)
        self.assertEqual(self.handle("/camalert/hide", header="secret", token="secret")[0], 200)
        self.assertEqual(self.handle("/camalert/hide", enabled=False)[1], {"result": False, "error": "disabled"})

    def test_actions(self):
        code, out, ctl = self.handle("/camalert/show", {"cam": "garden", "sec": "20", "mode": "live", "priority": "alarm"})
        self.assertEqual(out, {"result": True, "action": "show", "cam": "garden"})
        self.assertEqual(ctl.calls, [("show", "garden", 20, "live", "alarm")])
        self.assertEqual(self.handle("/camalert/show")[1]["cam"], "front_door")
        self.assertEqual(self.handle("/camalert/camalert")[1]["action"], "show")
        self.assertEqual(self.handle("/camalert/hide")[1], {"result": True, "action": "hide"})
        code, out, ctl = self.handle("/camalert/mosaic", {"cam": "a,b"})
        self.assertEqual((out, ctl.calls), ({"result": True, "action": "show"}, [("mosaic", "a,b", 60)]))
        code, out, ctl = self.handle("/camalert/tour", {"interval": "99"})
        self.assertEqual((out["result"], ctl.calls), (False, [("tour", None, 60)]))
        code, out, ctl = self.handle("/camalert/dnd", {"on": "1"})
        self.assertEqual(ctl.calls, [("dnd", True)])
        self.assertEqual(self.handle("/camalert/nonsense")[:2], (404, {"result": False, "error": "unknown action"}))
        out = self.handle("/camalert/status")[1]
        self.assertTrue(out["result"])
        for key in ("version", "id", "name", "window", "live", "dnd"):
            self.assertIn(key, out)

    def test_internal_error(self):
        class Broken(FakeController):
            def hide(self):
                raise ValueError("boom")
        code, out = self.server.handle(Broken(), "/camalert/hide", {}, "127.0.0.1", None, self.s)
        self.assertEqual((code, out), (500, {"result": False, "error": "internal error"}))


class TestKodiModules(unittest.TestCase):
    def test_all_modules_import(self):
        for name in ("kodiapi", "sources", "display", "controller", "server", "mqtt", "ptz", "service", "script"):
            Built.module(name)

    def test_discovery_and_frigate(self):
        mqtt = Built.module("mqtt")
        msgs = mqtt.kodi_discovery("abc", "CamAlert Kodi", [("front_door", "Front door")])
        self.assertTrue(msgs)
        for topic, payload in msgs:
            self.assertEqual(json.loads(payload)["device"]["model"], "Kodi")
        self.assertTrue(any(t.endswith("/dnd/config") for t, _p in msgs))
        self.assertEqual(mqtt.frigate_topic(""), "frigate/events")
        self.assertEqual(mqtt.frigate_topic("frigate2/"), "frigate2/events")

    def test_settings_restart(self):
        service = Built.module("service")
        self.assertEqual(service.changed_parts({"http_port": 1}, {"http_port": 2}), {"server"})
        self.assertEqual(service.changed_parts({"mqtt_host": "a"}, {"mqtt_host": "b"}), {"mqtt"})
        self.assertEqual(service.changed_parts({"duration": 1}, {"duration": 2}), set())

    def test_live_item_skips_probe(self):
        ctl = Built.module("controller")
        li = ctl.live_item("http://h:1984/api/stream.mp4?src=a&camalert=1", "A")
        self.assertEqual(li.props, {"mime": "video/mp4", "lookup": False})

    def test_english_fallback(self):
        kodiapi = Built.module("kodiapi")
        kodiapi.addon_path = lambda *p: os.path.join(Built.tmp, "service.camalert", *p)
        kodiapi._english = None
        self.assertEqual(kodiapi.tr(30192), "Cameras")
        self.assertEqual(kodiapi.tr(30181), "Could not reach the camera source:\n%s")


class TestKodiImports(unittest.TestCase):
    def test_used_shared_names_are_imported(self):
        """Every name from the shared logic.py / klogic.py that a Kodi module uses must be imported."""
        import ast
        lib = os.path.join(ADDON, "resources", "lib", "camalert")
        exported = set()
        for path in (os.path.join(ROOT, "src", "CamAlert", "logic.py"), os.path.join(lib, "klogic.py")):
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            exported |= {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        for f in os.listdir(lib):
            if not f.endswith(".py") or f in ("logic.py", "klogic.py", "devices.py"):
                continue
            with open(os.path.join(lib, f), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
            defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            missing = (used & exported) - imported - defined
            self.assertFalse(missing, "%s uses %s without importing it" % (f, sorted(missing)))


class TestKodiPackage(unittest.TestCase):
    def test_zip(self):
        b = Built.get()
        self.assertEqual(os.path.basename(b.addon_zip), "service.camalert-%s.zip" % build_kodi.version())
        names = zipfile.ZipFile(b.addon_zip).namelist()
        self.assertTrue(all(n.startswith("service.camalert/") for n in names))
        for f in ("addon.xml", "service.py", "default.py", "LICENSE.txt", "resources/settings.xml", "resources/icon.png",
                  "resources/fanart.jpg", "resources/lib/camalert/logic.py", "resources/lib/camalert/devices.py",
                  "resources/lib/camalert/controller.py"):
            self.assertIn("service.camalert/" + f, names)
        for lang in LANGS:
            self.assertIn("service.camalert/resources/language/resource.language.%s/strings.po" % lang, names)
        self.assertFalse([n for n in names if n.endswith(".pyc") or "__pycache__" in n])
        # shared logic is the current one
        shared = zipfile.ZipFile(b.addon_zip).read("service.camalert/resources/lib/camalert/logic.py")
        self.assertEqual(shared, open(os.path.join(ROOT, "src", "CamAlert", "logic.py"), "rb").read())

    def test_addon_xml(self):
        b = Built.get()
        root = ET.fromstring(zipfile.ZipFile(b.addon_zip).read("service.camalert/addon.xml"))
        self.assertEqual(root.get("id"), "service.camalert")
        self.assertEqual(root.get("version"), build_kodi.version())
        self.assertEqual(root.find("requires/import").get("addon"), "xbmc.python")
        points = {e.get("point") for e in root.findall("extension")}
        self.assertTrue({"xbmc.service", "xbmc.python.script", "xbmc.addon.metadata"} <= points)
        meta = [e for e in root.findall("extension") if e.get("point") == "xbmc.addon.metadata"][0]
        self.assertEqual(meta.find("license").text, "GPL-2.0-only")
        for asset in meta.find("assets"):
            self.assertTrue(os.path.exists(os.path.join(ADDON, asset.text)), asset.text)

    def test_repository(self):
        b = Built.get()
        addons = open(os.path.join(b.tree, "addons.xml"), "rb").read()
        self.assertEqual(open(os.path.join(b.tree, "addons.xml.md5")).read(), hashlib.md5(addons).hexdigest())
        ids = {a.get("id"): a.get("version") for a in ET.fromstring(addons)}
        self.assertEqual(ids["service.camalert"], build_kodi.version())
        self.assertIn("repository.camalert", ids)
        self.assertTrue(os.path.exists(os.path.join(b.tree, "service.camalert",
                                                    "service.camalert-%s.zip" % build_kodi.version())))
        repo = ET.fromstring(zipfile.ZipFile(b.repo_zip).read("repository.camalert/addon.xml"))
        self.assertEqual(repo.find(".//info").text, "https://example.invalid/kodi/addons.xml")
        self.assertNotIn(b"@REPO_URL@", addons)

    def test_reproducible(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = build_kodi.build(d1)[0]
            b = build_kodi.build(d2)[0]
            self.assertEqual(open(a, "rb").read(), open(b, "rb").read())


class TestKodiSettingsAndStrings(unittest.TestCase):
    def setUp(self):
        self.k = Built.module("klogic")
        self.tree = ET.parse(os.path.join(ADDON, "resources", "settings.xml"))
        self.en = po_strings("en_gb")

    def test_settings_match_defaults(self):
        ids = {s.get("id"): s for s in self.tree.iter("setting")}
        for key, default in self.k.DEFAULTS.items():
            self.assertIn(key, ids)
            d = ids[key].find("default")
            if isinstance(default, bool):
                self.assertEqual(d.text, str(default).lower(), key)
            else:
                self.assertEqual(d.text or "", str(default), key)
            options = [o.text for o in ids[key].iter("option")]
            if key in self.k.CHOICES:
                self.assertEqual(tuple(options), self.k.CHOICES[key], key)
        for key in ("mqtt_password", "ptz_password", "token"):
            self.assertEqual(ids[key].find("control/hidden").text, "true")

    def test_labels_exist(self):
        used = set()
        for el in self.tree.iter():
            for attr in ("label", "help"):
                if el.get(attr):
                    used.add(int(el.get(attr)))
            if el.tag == "heading" and el.text and el.text.isdigit():
                used.add(int(el.text))
        for f in os.listdir(os.path.join(ADDON, "resources", "lib", "camalert")):
            if f.endswith(".py"):
                with open(os.path.join(ADDON, "resources", "lib", "camalert", f), encoding="utf-8") as fh:
                    used |= {int(x) for x in re.findall(r"tr\((30\d\d\d)\)", fh.read())}
        missing = used - set(self.en)
        self.assertFalse(missing, missing)

    def test_translations(self):
        for lang in LANGS[1:]:
            po = po_strings(lang)
            self.assertEqual(set(po), set(self.en), lang)
            for i, (msgid, msgstr) in po.items():
                self.assertEqual(msgid, self.en[i][0], (lang, i))
                self.assertTrue(msgstr, (lang, i))
                self.assertEqual(msgid.count("%s"), msgstr.count("%s"), (lang, i))


if __name__ == "__main__":
    unittest.main()
