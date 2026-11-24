"""Kodi add-on (service.camalert): pure helpers, the HTTP API handler, the built zip and its metadata.
Runs without Kodi: tests/kodi/stubs.py makes strict xbmc modules per Kodi version (19-22) from the Kodistubs fixtures."""
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import _paths  # noqa: E402

ROOT = _paths.ROOT
ADDON = _paths.KODI_ADDON
_paths.tools()
import build_kodi  # noqa: E402
from kodi import stubs as kodi_stubs  # noqa: E402

# Problems the strict Kodi stubs find, each with its issue (a fixed one fails its test)
KNOWN_STUB_PROBLEMS = {}
MODULES = ("kodiapi", "sources", "display", "controller", "server", "mqtt", "ptz", "service", "script", "diag", "camlog")
LANGS = ("en_gb", "nl_nl", "de_de", "fr_fr", "it_it", "pl_pl")


def po_strings(lang):
    with open(os.path.join(ADDON, "resources", "language", "resource.language.%s" % lang, "strings.po"),
              encoding="utf-8") as f:
        text = f.read()
    return {int(m.group(1)): (m.group(2), m.group(3)) for m in
            re.finditer(r'msgctxt "#(\d+)"\nmsgid "((?:[^"\\]|\\.)*)"\nmsgstr "((?:[^"\\]|\\.)*)"', text)}


class Built(object):
    """The add-on package imported from the source tree with the strict stubs of one Kodi version, plus the built
    zips (once).

    Importing the sources (not the extracted zip) lets coverage measure the real files (#27); the zip itself is
    checked by TestKodiPackage, including a smoke import of every module from the extracted zip."""
    tmp = None
    store = None
    version = None

    @classmethod
    def get(cls, version=None):
        if cls.tmp is None:
            cls.tmp = tempfile.mkdtemp()
            cls.addon_zip, cls.repo_zip, cls.tree = build_kodi.build(cls.tmp, "https://example.invalid/kodi")
            with zipfile.ZipFile(cls.addon_zip) as z:
                z.extractall(cls.tmp)
            cls.profile = os.path.join(cls.tmp, "profile")
            os.makedirs(cls.profile)
        version = version or cls.version or kodi_stubs.DEFAULT_VERSION
        if version != cls.version or "camalert" not in sys.modules or "xbmc" not in sys.modules \
                or getattr(sys.modules["xbmc"], "KODI_VERSION", None) != version:
            cls.store = kodi_stubs.install(profile=cls.profile, version=version)
            cls.version = version
            _paths.kodi_package()
        return cls

    @classmethod
    def module(cls, name, version=None):
        cls.get(version)
        return importlib.import_module("camalert." + name)


def tearDownModule():
    if Built.tmp:
        shutil.rmtree(Built.tmp, ignore_errors=True)


class _KodiLogic(object):
    kodi = None

    def setUp(self):
        self.k = Built.module("klogic", self.kodi)

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

    def test_keys_chime_title(self):
        k = self.k
        self.assertEqual(k.colour_code(251), 398)
        self.assertEqual(k.colour_code(254), 401)
        self.assertEqual(k.colour_code(0xF071), 399)
        self.assertIsNone(k.colour_code(0))
        self.assertIsNone(k.colour_code(61453))
        self.assertTrue(k.chime_wanted("all", "normal"))
        self.assertTrue(k.chime_wanted("high", "alarm"))
        self.assertFalse(k.chime_wanted("high", "normal"))
        self.assertFalse(k.chime_wanted("off", "alarm"))
        self.assertEqual(k.title_font_name("large"), "font30")
        self.assertEqual(k.title_font_name("?"), "font13")

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
        self.events = [{"time": 1, "camera": "garden", "label": "", "source": "api", "priority": "normal",
                        "action": "show", "reason": "", "snapshot": "/x.jpg", "frigate_id": None}]
        self.last_caller = None

    def has_ptz(self, cam):
        return cam == "garden"

    def ptz_move(self, move, cam):
        self.calls.append(("ptz", move, cam))
        return True

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


class _KodiApi(object):
    """Same answers as the Enigma2 plugin's server.py."""

    def setUp(self):
        self.server = Built.module("server", self.kodi)
        self.server.LIMIT.seen.clear()
        self.s = Built.module("klogic").parse_settings({"camera": "front_door"})

    def handle(self, path, args=None, ip="192.168.1.5", header=None, user_agent="", **settings):
        s = dict(self.s, **settings)
        ctl = FakeController()
        code, out = self.server.handle(ctl, path, args or {}, ip, header, s, user_agent)
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
        self.assertEqual(ctl.calls, [("show", "garden", 20, "live", "alarm", "api", None)])
        code, out, ctl = self.handle("/camalert/show", {"cam": "garden", "label": "Person"}, user_agent="HomeAssistant/2026.11 aiohttp/3.10")
        self.assertEqual(ctl.calls, [("show", "garden", None, None, None, "ha", "Person")])
        self.assertEqual(ctl.last_caller[1:], ("192.168.1.5", "ha"))
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

    def test_new_actions(self):
        code, out, ctl = self.handle("/camalert/ptz", {"cam": "garden", "move": "left"})
        self.assertEqual((code, out, ctl.calls), (200, {"result": True, "cam": "garden", "move": "left"},
                                                  [("ptz", "left", "garden")]))
        self.assertEqual(self.handle("/camalert/ptz", {"cam": "front_door", "move": "left"})[0], 400)
        self.assertEqual(self.handle("/camalert/ptz", {"cam": "garden", "move": "jump"})[0], 400)
        self.assertEqual(self.handle("/camalert/webhook", {"url": "ftp://x"})[0], 400)
        self.assertEqual(self.handle("/camalert/webhook", {"url": "http://ha:8123/api/webhook/abc"})[1],
                         {"result": True, "webhook": True})
        self.assertEqual(Built.store.get("ha_webhook"), "http://ha:8123/api/webhook/abc")
        ev = self.handle("/camalert/events")[1]["events"]
        self.assertEqual(ev[0]["camera"], "garden")
        self.assertNotIn("snapshot", ev[0])
        out = self.handle("/camalert/log", {"lines": "5"})[1]
        self.assertTrue(out["result"])
        self.assertIsInstance(out["lines"], list)

    def test_metrics_and_rate_limit(self):
        code, out, ctl = self.handle("/camalert/metrics", ip="192.168.1.77")
        self.assertEqual(code, 200)
        self.assertIn('camalert_uptime_seconds{platform="kodi"', out)
        codes = [self.handle("/camalert/status", ip="192.168.1.99")[0] for _ in range(35)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 200)

    def test_internal_error(self):
        class Broken(FakeController):
            def hide(self):
                raise ValueError("boom")
        code, out = self.server.handle(Broken(), "/camalert/hide", {}, "127.0.0.1", None, self.s)
        self.assertEqual((code, out), (500, {"result": False, "error": "internal error"}))


class _KodiModules(object):
    def setUp(self):
        Built.get(self.kodi)
        kodi_stubs.JSONRPC_PROBLEMS[:] = []
        kodi_stubs.CALLS[:] = []

    def tearDown(self):
        self.assertEqual(kodi_stubs.JSONRPC_PROBLEMS, [], "JSON-RPC requests this Kodi version refuses")
    def test_all_modules_import(self):
        for name in MODULES:
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

    def test_log_is_redacted_and_rotates(self):
        kodiapi = Built.module("kodiapi")
        log = kodiapi.camlog()
        log.configure("verbose")
        kodiapi.log("connect http://user:" + "secret@cam/x?pwd=hunter2&usr=admin", "verbose")
        text = "\n".join(log.tail(5))
        self.assertIn("connect", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("hunter2", text)
        self.assertTrue(log.path.startswith(Built.profile))

    def test_controller_events_and_buttons(self):
        ctl_mod = Built.module("controller")
        ctl = ctl_mod.Controller()
        ctl.record_event("garden", "Person", "frigate", "high", "ignore", "do not disturb", "123.4-abc")
        self.assertEqual(ctl.events[0]["label"], "Person")
        self.assertEqual(ctl.events[0]["frigate_id"], "123.4-abc")
        sent = []
        ctl.send_button = lambda cam, b, s=None: sent.append((cam, b))
        self.assertEqual(ctl.colour_key("garden", 398), "red")
        self.assertEqual(sent, [("garden", "red")])

    def test_cooldown_and_substreams(self):
        ctl_mod = Built.module("controller")
        sources = Built.module("sources")
        Built.store.update({"cooldown": "*=60", "camera": "garden", "substreams": "garden=garden_sub",
                            "server": "http://192.168.1.10:1984"})
        try:
            ctl = ctl_mod.Controller()
            ctl._show = lambda *a: "show"
            self.assertEqual(ctl.show("garden"), "show")
            self.assertEqual(ctl.show("garden"), "ignore")
            self.assertTrue(ctl.events[0]["reason"].startswith("cooldown"))
            self.assertEqual(ctl.show("garden", priority="alarm"), "show")
            live, snap, _title = sources.camera_urls("garden")
            self.assertIn("src=garden_sub", live)
            self.assertIn("garden", snap)
            self.assertNotIn("garden_sub", snap)
        finally:
            for k in ("cooldown", "camera", "substreams", "server"):
                Built.store.pop(k, None)

    def test_english_fallback(self):
        kodiapi = Built.module("kodiapi")
        kodiapi.addon_path = lambda *p: os.path.join(ADDON, *p)
        kodiapi._english = None
        self.assertEqual(kodiapi.tr(30192), "Cameras")
        self.assertEqual(kodiapi.tr(30181), "Could not reach the camera source:\n%s")

    # --- windows, keys, the service loop and JSON-RPC under the strict stubs of this Kodi version (#29) -------
    CAMS = [("front_door", "Front door", "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640"),
            ("garden", "Garden", "http://192.168.1.10:1984/api/frame.jpeg?src=garden&width=640")]

    class Action(object):
        def __init__(self, aid, button=0):
            self.aid, self.button = aid, button

        def getId(self):
            return self.aid

        def getButtonCode(self):
            return self.button

    def settings(self, **kw):
        return dict(Built.module("klogic").parse_settings({}), **kw)

    def test_photo_window_and_strip(self):
        display = Built.module("display")
        ctl = FakeController()
        for cams in (self.CAMS[:1], self.CAMS):
            w = display.PhotoWindow(ctl, cams, self.settings(), keys=True, label="Person")
            self.assertEqual(len(w.tiles), len(cams))
            w.ptz_label(True)
            w.unreachable(w.tiles[0], True)
            w.unreachable(w.tiles[0], False)
            if w.timer:
                w.timer.cancel()

    def test_photo_window_keys(self):
        display = Built.module("display")
        ctl = FakeController()
        ctl.window_to_live = lambda s: ctl.calls.append(("live", s))
        ctl.other_camera = lambda step: ctl.calls.append(("other", step))
        w = display.PhotoWindow(ctl, self.CAMS[:1], self.settings(), keys=True)
        for aid in (7, 1, 2, 88, 92):  # OK, LEFT, RIGHT, volume up, BACK
            w.onAction(self.Action(aid))
        self.assertEqual(ctl.calls, [("live", "front_door"), ("other", -1), ("other", 1), ("hide",)])

    def test_mosaic_and_tour_windows(self):
        display = Built.module("display")
        ctl = FakeController()
        ctl.fullscreen_closed = lambda f: ctl.calls.append(("closed",))
        tour = display.FullScreen(ctl, self.CAMS, self.settings(), tour=True, interval=8)
        for aid in (2, 7, 7, 92):  # next, hold, hold, BACK
            tour.onAction(self.Action(aid))
        self.assertEqual(tour.index, 1)
        self.assertIn(("closed",), ctl.calls)
        if "mosaic labels" in KNOWN_STUB_PROBLEMS:  # fails like on a real Kodi; a fixed problem fails here too
            with self.assertRaises(TypeError, msg="fixed: remove 'mosaic labels' from KNOWN_STUB_PROBLEMS"):
                display.FullScreen(ctl, self.CAMS, self.settings(), tour=False)
            return
        mosaic = display.FullScreen(ctl, self.CAMS, self.settings(), tour=False)
        self.assertEqual(len(mosaic.tiles), 2)

    def test_live_overlay(self):
        display = Built.module("display")
        ctl = FakeController()
        ctl.live_other = lambda step: ctl.calls.append(("other", step))
        o = display.LiveOverlay(ctl, "garden", "Garden")
        o.set_camera("front_door", "Front door")
        for aid in (1, 92):
            o.onAction(self.Action(aid))
        self.assertEqual(ctl.calls, [("other", -1), ("hide",)])

    def test_live_view_lowers_the_volume_through_jsonrpc(self):
        ctl_mod = Built.module("controller")
        Built.store.update({"live_volume": "50", "server": "http://192.168.1.10:1984"})
        try:
            ctl = ctl_mod.Controller()
            ctl._show_overlay = lambda *a: None
            s = Built.module("kodiapi").settings()
            ctl._live("garden", "http://x/api/stream.mp4?src=garden", "Garden", 10, s, "normal", "none", "", 0, False,
                      "show")
            self.assertEqual(ctl.saved_volume, 80)
            self.assertTrue(kodi_stubs.calls("xbmc.Player.play"))
            ctl.end_live()
            sent = [json.loads(c[1][0]) for c in kodi_stubs.calls("xbmc.executeJSONRPC")]
            self.assertEqual([r["method"] for r in sent], ["Application.GetProperties", "Application.SetVolume",
                                                           "Application.SetVolume"])
            self.assertEqual(sent[1]["params"], {"volume": 40})
        finally:
            for k in ("live_volume", "server"):
                Built.store.pop(k, None)

    def test_jsonrpc_check_sees_wrong_requests(self):
        """Self test of the strict stub: an unknown method and an unknown property are refused."""
        kodiapi = Built.module("kodiapi")
        self.assertIsNone(kodiapi.jsonrpc("Application.Explode"))
        self.assertIsNone(kodiapi.jsonrpc("Application.GetProperties", {"properties": ["colour"]}))
        self.assertEqual(len(kodi_stubs.JSONRPC_PROBLEMS), 2)
        kodi_stubs.JSONRPC_PROBLEMS[:] = []

    def test_strict_stubs_refuse_unknown_arguments(self):
        import xbmcgui
        with self.assertRaises(TypeError):
            xbmcgui.ControlImage(0, 0, 10, 10, "", nonsense=1)
        with self.assertRaises(AttributeError):
            getattr(xbmcgui, "ControlWebBrowser")

    def test_service_loop_runs_until_abort(self):
        service = Built.module("service")
        started = []
        for name in ("server", "mqtt", "ptz"):
            mod = Built.module(name)
            self.addCleanup(setattr, mod, "start", mod.start)
            self.addCleanup(setattr, mod, "stop", mod.stop)
            mod.start = lambda *a, n=name: started.append(n)
            mod.stop = lambda *a, n=name: started.append("stop " + n)
        kodi_stubs.MONITOR["waits"] = 3
        svc = service.Service()
        svc.run()
        self.assertEqual(started[:3], ["server", "mqtt", "ptz"])
        self.assertIn("stop server", started)
        self.assertLess(kodi_stubs.MONITOR["waits"], 1)


class TestKodiImports(unittest.TestCase):
    def test_used_shared_names_are_imported(self):
        """Every name from the shared logic.py / klogic.py that a Kodi module uses must be imported."""
        import ast
        lib = _paths.KODI_LIB
        exported = set()
        for path in (os.path.join(_paths.SHARED, "logic.py"), os.path.join(lib, "klogic.py")):
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
                  "resources/lib/camalert/controller.py", "resources/lib/camalert/camlog.py", "resources/media/chime.wav"):
            self.assertIn("service.camalert/" + f, names)
        for lang in LANGS:
            self.assertIn("service.camalert/resources/language/resource.language.%s/strings.po" % lang, names)
        self.assertFalse([n for n in names if n.endswith(".pyc") or "__pycache__" in n])
        # shared logic is the current one
        shared = zipfile.ZipFile(b.addon_zip).read("service.camalert/resources/lib/camalert/logic.py")
        self.assertEqual(shared, open(os.path.join(_paths.SHARED, "logic.py"), "rb").read())

    def test_every_module_imports_from_the_zip(self):
        """Smoke test of the package as Kodi gets it (separate interpreter, so it does not mix with the sources)."""
        b = Built.get()
        code = ("import sys; sys.path[:0] = [%r, %r]; from kodi import stubs; stubs.install(profile=%r); "
                "import importlib; [importlib.import_module('camalert.' + m) for m in %r]"
                % (_paths.TESTS, os.path.join(b.tmp, "service.camalert", "resources", "lib"), b.profile, MODULES))
        subprocess.check_call([sys.executable, "-c", code])

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


# the functional tests run once per Kodi version, each with the strict stubs of that version (#29)
for _v in kodi_stubs.VERSIONS:
    for _base in (_KodiLogic, _KodiApi, _KodiModules):
        _name = "TestKodi%s_%d" % (_base.__name__[5:], _v)
        globals()[_name] = type(_name, (_base, unittest.TestCase), {"kodi": _v})


if __name__ == "__main__":
    unittest.main()
