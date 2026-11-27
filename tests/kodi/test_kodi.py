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
from fakes.go2rtc import FakeGo2rtc  # noqa: E402

# Problems the strict Kodi stubs find, each with its issue (a fixed one fails its test)
KNOWN_STUB_PROBLEMS = {}
MODULES = ("kodiapi", "sources", "display", "controller", "server", "mqtt", "ptz", "service", "script", "diag",
           "browse", "plugin", "screensaver")
# first fontset of Estuary's Font.xml (Kodi 21), shortened
ESTUARY_FONTS = """<fonts><fontset id="Default"><font><name>font10</name><size>23</size></font>
<font><name>font12</name><size>25</size></font><font><name>font13</name><size>30</size></font>
<font><name>font14</name><size>33</size></font><font><name>font27</name><size>27</size></font>
<font><name>font32</name><size>32</size></font><font><name>font37</name><size>37</size></font>
<font><name>font45</name><size>45</size></font><font><name>font30_title</name><size>30</size></font>
<font><name>font36_title</name><size>36</size></font></fontset>
<fontset id="Arial"><font><name>font13</name><size>27</size></font></fontset></fonts>"""
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
        Built.tmp = None  # a later test module (test_screensaver) builds again


class _KodiLogic(object):
    kodi = None

    def setUp(self):
        self.k = Built.module("klogic", self.kodi)

    # UI guideline (#2, 8a "Key mapping (target)"): every Kodi screen, key -> action. Extra Kodi keys are allowed
    # (STOP, MENU/INFO, PgUp/PgDn, UP in the tour); the guideline keys must all be there.
    GUIDELINE = (
        ("window", "key_action", ((7, "live"), (135, "live"), (1, "prev"), (2, "next"), (92, "close"),
                                  (10, "close"), (88, "pass"), (89, "pass"), (91, "pass"), (3, "close_pass"))),
        ("ptz", "ptz_action", ((3, "up"), (4, "down"), (1, "left"), (2, "right"), (184, "zoom_in"),
                               (185, "zoom_out"), (5, "zoom_in"), (6, "zoom_out"), (7, "home"), (92, "leave"),
                               (117, "leave"), (11, "leave"), (88, None))),
        ("tour", "tour_key", ((1, "prev"), (2, "next"), (7, "hold"), (135, "hold"), ((122, 252), "live"),
                              ((122, 0xF071), "live"), (79, "live"), (92, "close"), (10, "close"),
                              ((122, 251), "none"))),
        ("mosaic", "mosaic_key", ((7, "close"), (135, "close"), (92, "close"), (10, "close"))),
        ("live", "live_key", ((1, "prev"), (2, "next"), (92, "close"), (117, "ptz"), (11, "ptz"), (12, "pause"))),
    )

    def test_keys_follow_the_ui_guideline(self):
        for screen, fn, cases in self.GUIDELINE:
            for key, want in cases:
                args = key if isinstance(key, tuple) else (key,)
                self.assertEqual(getattr(self.k, fn)(*args), want, (screen, key))

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

    def test_settings_migration(self):
        """A settings file of a version-1 add-on (#39): old keys move to the schema-version-2 keys."""
        k = self.k
        v1 = ('<settings version="2"><setting id="live_resume">false</setting><setting id="refresh_map">garden=5'
              '</setting><setting id="duration" default="true">30</setting><setting id="chime">all</setting></settings>')
        saved = k.saved_values(v1)
        self.assertEqual(saved["live_resume"], "false")
        self.assertEqual(k.migrations(saved), {"live_return": "false", "refresh": "garden=5"})
        # the new key is already there (the user changed it later): it wins, nothing to write
        self.assertEqual(k.migrations(dict(saved, live_return="true", refresh="")), {})
        self.assertEqual(k.saved_values('<settings><setting id="refresh_map" value="a=1" /></settings>'),
                         {"refresh_map": "a=1"})  # Kodi 18 format
        self.assertEqual(k.migrations(k.saved_values("<settings><broken")), {})
        self.assertEqual(k.migrations({"duration": "30", "mode": "live"}), {})

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
        self.assertEqual(k.colour_name(251), "red")
        self.assertEqual(k.colour_name(254), "blue")
        self.assertEqual(k.colour_name(0xF071), "green")
        self.assertIsNone(k.colour_name(0))
        self.assertIsNone(k.colour_name(61453))
        for aid in (7, 135, 10, 92, 13):  # OK (SELECT/ENTER), BACK (PREVIOUS_MENU/NAV_BACK), STOP close it (#58)
            self.assertEqual(k.mosaic_key(aid), "close")
        self.assertEqual(k.mosaic_key(1), "none")
        self.assertEqual(k.live_key(117), "ptz")
        self.assertEqual(k.live_key(79), "pause")
        self.assertTrue(k.chime_wanted("all", "normal"))
        self.assertTrue(k.chime_wanted("high", "alarm"))
        self.assertFalse(k.chime_wanted("high", "normal"))
        self.assertFalse(k.chime_wanted("off", "alarm"))
        # #46: only font13 is guaranteed; small/large come from the skin's own fonts
        for size in ("small", "normal", "large", "?"):
            self.assertEqual(k.title_font_name(size), "font13")
        estuary = k.skin_font_sizes(ESTUARY_FONTS)
        self.assertEqual(estuary["font13"], 30)
        self.assertNotIn("font30", estuary)  # what the add-on used for 'large' before
        self.assertEqual([k.title_font_name(x, estuary) for x in ("small", "normal", "large")],
                         ["font12", "font13", "font37"])
        confluence = {"font10": 18, "font12": 20, "font13": 24, "font30": 30, "font35": 36, "font_MainMenu": 40}
        self.assertEqual([k.title_font_name(x, confluence) for x in ("small", "large")], ["font12", "font30"])
        self.assertEqual(k.title_font_name("large", {"font13": 30, "font99_title": 44}), "font13")
        self.assertEqual(k.skin_font_sizes("<broken"), {})
        self.assertEqual(k.skin_font_sizes("<fonts/>"), {})

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

    def test_default_password_line(self):
        """#55: the default camera password is one '*|default|*' line in devices.conf; other lines never change."""
        k = self.k
        cams = "# comment\nfront_door|onvif|192.168.1.10:80|admin|a|b\ngarden|foscam|192.168.1.11:88||\n"
        self.assertEqual(k.stored_default_login(cams), ("", ""))
        self.assertEqual(k.stored_default_login(None), ("", ""))
        once = k.with_default_password(cams, "s|e cret")
        self.assertEqual(once, cams + "*|default|*||s|e cret\n")
        self.assertEqual(k.stored_default_login(once), ("", "s|e cret"))
        self.assertEqual(k.with_default_password(once, "s|e cret"), once)  # idempotent, never a second line
        twice = k.with_default_password(once, "new\r\n")
        self.assertEqual(twice.count("*|default|"), 1)
        self.assertEqual(k.stored_default_login(twice), ("", "new"))
        self.assertTrue(twice.startswith(cams))
        self.assertEqual(k.with_default_password(twice, ""), cams)  # removed
        self.assertEqual(k.with_default_password("", ""), "")
        self.assertEqual(k.with_default_password(None, "x"), "*|default|*||x\n")
        # a user written on the line by hand is kept and read
        hand = " * | DEFAULT |*|viewer|old\n"
        self.assertEqual(k.stored_default_login(hand), ("viewer", "old"))
        self.assertEqual(k.with_default_password(hand, "new"), "*|default|*|viewer|new\n")
        # both players' parser skips the line, so Enigma2 and the device list ignore it
        from camalert_core.devices.config import parse_devices
        self.assertEqual(set(parse_devices(twice)), {"front_door", "garden"})


def types_ns(**kw):
    import types
    return types.SimpleNamespace(**kw)


class FakeController(object):
    def __init__(self):
        self.calls = []
        self.dnd = False
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
    """The Kodi HTTP adapter (server.Handler) over a real socket; the API itself is checked by the contract table
    (tests/contract/test_http_contract.py) against both players."""

    def setUp(self):
        import threading
        from http.server import ThreadingHTTPServer
        self.server = Built.module("server", self.kodi)
        Built.module("camalert_core.api").LIMIT.seen.clear()
        self.ctl = FakeController()
        Built.module("controller").Controller.instance = self.ctl
        Built.store.update({"camera": "front_door", "token": "secret"})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self.server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, args=(0.02,), daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for k in ("camera", "token"):
            Built.store.pop(k, None)

    def request(self, path, method="GET", body=None, token="secret", ctype="application/json"):
        import urllib.error
        import urllib.request
        headers = {"X-CamAlert-Token": token} if token else {}
        if body is not None:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_post_json_with_header_token(self):
        code, headers, body = self.request("/camalert/show", "POST", b'{"cam": "garden", "sec": 20}')
        self.assertEqual((code, json.loads(body)["action"]), (200, "show"))
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(int(headers["Content-Length"]), len(body))
        self.assertNotIn("Deprecation", headers)
        self.assertEqual(self.ctl.calls, [("show", "garden", 20, None, None, "api", None)])

    def test_get_action_is_deprecated_but_works(self):
        code, headers, body = self.request("/camalert/hide")
        self.assertEqual((code, headers.get("Deprecation")), (200, "true"))

    def test_token_errors_and_methods(self):
        self.assertEqual(self.request("/camalert/status", token=None)[0], 403)
        self.assertEqual(self.request("/camalert/status?token=secret", token=None)[0], 200)  # deprecated
        self.assertEqual(self.request("/camalert/hide", "PUT", b"")[0], 405)
        self.assertEqual(self.request("/camalert/show", "POST", b"cam=a/b",
                                      ctype="application/x-www-form-urlencoded")[0], 400)

    def test_metrics_are_text(self):
        code, headers, body = self.request("/camalert/metrics")
        self.assertTrue(headers["Content-Type"].startswith("text/plain"))
        self.assertIn(b'platform="kodi"', body)


class _KodiModules(object):
    go2rtc = None

    @classmethod
    def setUpClass(cls):
        # snapshots and camera lists come from the fake go2rtc on 127.0.0.1, never from the network (#73)
        cls.go2rtc = FakeGo2rtc().start()

    @classmethod
    def tearDownClass(cls):
        cls.go2rtc.shutdown()
        cls.go2rtc.server_close()

    def setUp(self):
        Built.get(self.kodi)
        kodi_stubs.JSONRPC_PROBLEMS[:] = []
        kodi_stubs.CALLS[:] = []
        Built.store["server"] = self.go2rtc.url
        self.addCleanup(Built.store.pop, "server", None)
        sources = Built.module("sources")  # never a real UniFi console from a devices.conf of a test (#109)
        self.addCleanup(setattr, sources.PROTECT, "fetch", sources.PROTECT.fetch)
        sources.PROTECT.fetch = lambda dev, cam, names, width: None

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
        self.assertEqual(mqtt.trigger_settings({"frigate_enabled": True})["frigate_debounce"], 5)

    def test_settings_file_is_migrated_on_start(self):
        kodiapi = Built.module("kodiapi")
        path = os.path.join(Built.profile, "settings.xml")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<settings version="2"><setting id="live_resume">false</setting></settings>')
        try:
            self.assertEqual(kodiapi.migrate_settings(), ["live_return"])
            self.assertEqual(Built.store["live_return"], "false")
            self.assertFalse(kodiapi.settings()["live_return"])
            os.remove(path)
            self.assertEqual(kodiapi.migrate_settings(), [])  # no settings file yet (fresh install)
        finally:
            Built.store.pop("live_return", None)
            if os.path.exists(path):
                os.remove(path)

    def test_skin_fonts_are_read_from_the_skin(self):
        import types
        kodiapi = Built.module("kodiapi")
        skin = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, skin, True)
        os.makedirs(os.path.join(skin, "xml"))
        with open(os.path.join(skin, "xml", "Font.xml"), "w", encoding="utf-8") as f:
            f.write(ESTUARY_FONTS)
        self.addCleanup(setattr, kodiapi, "xbmcvfs", kodiapi.xbmcvfs)
        kodiapi.xbmcvfs = types.SimpleNamespace(translatePath=lambda p: skin if p == "special://skin/" else p)
        self.assertEqual(kodiapi.skin_fonts()["font37"], 37)
        kodiapi.xbmcvfs = types.SimpleNamespace(translatePath=lambda p: os.path.join(skin, "missing"))
        self.assertEqual(kodiapi.skin_fonts(), {})

    def test_settings_restart(self):
        service = Built.module("service")
        self.assertEqual(service.changed_parts({"http_port": 1}, {"http_port": 2}), {"server"})
        self.assertEqual(service.changed_parts({"mqtt_host": "a"}, {"mqtt_host": "b"}), {"mqtt"})
        self.assertEqual(service.changed_parts({"duration": 1}, {"duration": 2}), set())

    def test_ready_cameras_follow_the_screen(self):
        """#111: warm feeds on with CamAlert on, go2rtc as source and the screen not off; a fresh warm picture wins."""
        sources, kodiapi = Built.module("sources"), Built.module("kodiapi")
        values = {"enabled": "true", "source": "go2rtc", "server": "192.168.1.10:1984",
                  "ready_cameras": "front_door=front_door_jpeg", "verify_ssl": "true"}
        self.addCleanup(setattr, kodiapi, "addon_setting", kodiapi.addon_setting)
        kodiapi.addon_setting = lambda key: values.get(key, "")
        calls = []
        self.addCleanup(setattr, sources.WARM, "update", sources.WARM.update)
        sources.WARM.update = lambda server, ready, on: calls.append((server, ready, on))
        sources.warm_tick(False)
        self.assertEqual(calls[-1], ("192.168.1.10:1984", "front_door=front_door_jpeg", True))
        sources.warm_tick(True)  # screen off = Kodi's standby
        self.assertFalse(calls[-1][2])
        values["enabled"] = "false"
        sources.warm_tick(False)
        self.assertFalse(calls[-1][2])
        values.update(enabled="true", source="direct")
        sources.warm_tick(False)
        self.assertFalse(calls[-1][2])

        self.addCleanup(setattr, sources.WARM, "frame", sources.WARM.frame)
        sources.WARM.frame = lambda cam, max_age=5: b"warm" if cam == "front_door" else None
        asked = []

        def download(url, p, verify=True):
            asked.append(url)
            with open(p, "wb") as f:
                f.write(b"go2rtc")
            return p
        self.addCleanup(setattr, sources, "download", sources.download)
        sources.download = download
        out = os.path.join(Built.tmp, "warm.jpg")
        url = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
        self.assertEqual(sources.picture("front_door", url % "front_door", out, True, True, self.settings()), "warm")
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"warm")
        self.assertEqual(asked, [])
        self.assertEqual(sources.picture("garden", url % "garden", out, True, True, self.settings()), "cache")

    def test_protect_camera_pictures_come_from_protect(self):
        """#109: a camera of the UniFi console in devices.conf gets its picture from Protect; other cameras, and every
        camera with the setting off, from go2rtc (the first picture cached, #110)."""
        ptz, sources = Built.module("ptz"), Built.module("sources")
        path = ptz.device_file()
        with open(path, "w", encoding="utf-8") as f:
            f.write("protect|unifi|192.168.1.1:443|viewer|secret\ndoor|onvif|192.168.1.11:80||\n")
        self.addCleanup(os.remove, path)
        asked, protect = [], []

        def download(url, p, verify=True):
            asked.append(url)
            with open(p, "wb") as f:
                f.write(b"go2rtc")
            return p
        self.addCleanup(setattr, sources, "download", sources.download)
        sources.download = download
        self.addCleanup(setattr, sources.PROTECT, "fetch", None)
        sources.PROTECT.fetch = lambda dev, cam, names, width: (
            protect.append((dev["type"], cam, dict(names), width)) or (b"protect" if cam == "front_door" else None))
        sources._PROTECT_KEY[0] = None
        out = os.path.join(Built.tmp, "pic.jpg")
        s = self.settings(unifi_cameras="Haustuer=front_door")
        url = "http://192.168.1.10:1984/api/frame.jpeg?src=%s&width=640"
        self.assertEqual(sources.picture("front_door", url % "front_door", out, True, True, s), "protect")
        with open(out, "rb") as f:
            self.assertEqual(f.read(), b"protect")
        self.assertEqual(sources.picture("garden", url % "garden", out, True, True, s), "cache")
        self.assertEqual(protect, [("unifi", "front_door", {"haustuer": "front_door"}, 640),
                                   ("unifi", "garden", {"haustuer": "front_door"}, 640)])
        self.assertEqual(asked, [url % "garden" + "&cache=10s"])
        off = self.settings(protect_snapshots=False)
        self.assertEqual(sources.picture("front_door", url % "front_door", out, True, False, off), "go2rtc")
        self.assertEqual(len(protect), 2)

    def unifi_setup(self, enabled="true"):
        """#71: devices.conf with a UniFi console and an ONVIF camera, the source on, polls answered by a fake."""
        ptz = Built.module("ptz")
        path = ptz.device_file()
        with open(path, "w", encoding="utf-8") as f:
            f.write("protect|unifi|192.168.1.1:443|viewer|secret\ndoor|onvif|192.168.1.11:80||\n")
        os.chmod(path, 0o644)
        self.addCleanup(os.remove, path)
        keys = {"unifi_enabled": enabled, "unifi_kinds": "ring,motion", "ptz_user": "admin", "ptz_password": "pw"}
        Built.store.update(keys)
        self.addCleanup(lambda: [Built.store.pop(k, None) for k in keys])
        self.answers = []
        self.addCleanup(setattr, ptz.UnifiSource, "poll", ptz.UnifiSource.poll)
        ptz.UnifiSource.poll = staticmethod(lambda dev: self.answers.pop(0)(dev))
        ptz.UNIFI_STATUS.reset()
        shown = []
        poller = ptz.UnifiPoller(types_ns(show=lambda *a: shown.append(a)))
        return ptz, poller, shown

    @staticmethod
    def unifi_answer(*ids, kind="motion"):
        cam = "65a1b2c3d4e5f60718293a4b"
        return lambda dev: {"now": 1, "cams": {cam: "garden"},
                            "events": [{"id": i, "type": kind, "camera": cam, "smartDetectTypes": []} for i in ids]}

    def test_unifi_poller_baseline_then_event(self):
        ptz, poller, shown = self.unifi_setup()
        seen = []
        self.answers += [lambda dev: seen.append(dev) or self.unifi_answer("1")(dev), self.unifi_answer("1", "2")]
        poller.once()
        self.assertEqual(shown, [])  # first answer: old events never on screen
        self.assertEqual((seen[0]["user"], seen[0]["password"]), ("viewer", "secret"))
        self.assertEqual(os.stat(ptz.device_file()).st_mode & 0o777, 0o600)
        poller.once()
        self.assertEqual(shown, [("garden", 30, "photo", "normal", "unifi", "Motion", None)])
        self.assertEqual(ptz.UNIFI_STATUS.last_event["camera"], "garden")
        self.assertEqual(ptz.UNIFI_STATUS.consoles, 1)
        # consoles are never PTZ cameras and never get the default camera login
        self.assertEqual(set(ptz.ptz_devices()), {"door"})
        self.assertEqual(ptz.all_devices()["door"]["user"], "admin")
        self.assertFalse(Built.module("controller").Controller().has_ptz("protect"))

    def test_unifi_poller_per_camera_rule(self):
        """#9: the setting Per camera reaches the source; other cameras keep the general settings."""
        ptz, poller, shown = self.unifi_setup()
        keys = {"unifi_mode": "log", "unifi_camera_rules": "garden=high/photo/45|other=alarm"}
        Built.store.update(keys)
        self.addCleanup(lambda: [Built.store.pop(k, None) for k in keys])
        self.answers += [self.unifi_answer("1"), self.unifi_answer("1", "2")]
        poller.once()
        poller.once()
        self.assertEqual(shown, [("garden", 45, "photo", "high", "unifi", "Motion", None)])

    def test_unifi_poller_error_is_logged_once_and_resets_the_baseline(self):
        ptz, poller, shown = self.unifi_setup()
        kodiapi = Built.module("kodiapi")
        logged = []
        self.addCleanup(setattr, kodiapi, "log", kodiapi.log)
        kodiapi.log = lambda text, level="normal": logged.append(text)

        def fail(dev):
            raise ValueError("UniFi Protect login: HTTP 401 password=secret")
        self.answers += [self.unifi_answer("1"), fail, fail, self.unifi_answer("1", "9", kind="ring")]
        for _i in range(4):
            poller.once()
        self.assertEqual(len([t for t in logged if "HTTP 401" in t]), 1)
        self.assertFalse([t for t in logged if "secret" in t])
        self.assertEqual(shown, [])  # after an error the next answer is a new baseline
        self.assertIsNone(ptz.UNIFI_STATUS.error)
        diag = Built.module("diag")
        ptz.UNIFI_STATUS.failed("UniFi Protect events: not reachable (URLError)")
        lines = diag.unifi_lines(Built.module("service").unifi_state())
        self.assertTrue(lines[0].startswith("[FAIL]"), lines)
        self.assertTrue(any("garden" not in l and "UniFi" in l for l in lines))
        self.assertTrue(diag.unifi_lines(None)[0].startswith("[FAIL]"))  # no console known yet

    def test_unifi_poller_login_backoff_and_devices_file_change(self):
        """#78: a waiting login is logged once, the diagnostics show the next attempt; a changed devices.conf
        resets the backoff."""
        ptz, poller, shown = self.unifi_setup()
        client = Built.module("ptz").devices
        kodiapi = Built.module("kodiapi")
        logged, resets = [], []
        self.addCleanup(setattr, kodiapi, "log", kodiapi.log)
        kodiapi.log = lambda text, level="normal": logged.append(text)
        self.addCleanup(setattr, ptz.UnifiSource, "devices_changed", ptz.UnifiSource.devices_changed)
        ptz.UnifiSource.devices_changed = staticmethod(lambda: resets.append(1))

        def wait(dev):
            raise client.LoginError("UniFi Protect login: too many attempts (HTTP 429)", "rate", 2000000000)
        self.answers += [wait, wait, wait]
        for _i in range(3):
            poller.once()
        self.assertEqual(len([t for t in logged if "HTTP 429" in t]), 1)
        self.assertEqual(resets, [1])  # first read of the file only
        state = Built.module("service").unifi_state()
        self.assertEqual(state["next_retry"], 2000000000)
        lines = Built.module("diag").unifi_lines(state)
        self.assertTrue(any("next login attempt" in l for l in lines), lines)
        os.utime(ptz.device_file(), (1, 1))
        self.answers.append(self.unifi_answer("1"))
        poller.once()
        self.assertEqual(resets, [1, 1])

    def test_unifi_poller_off_polls_nothing(self):
        ptz, poller, shown = self.unifi_setup(enabled="false")
        ptz.UNIFI_STATUS.consoles = 3
        poller.once()
        self.assertEqual((shown, ptz.UNIFI_STATUS.consoles, poller.state), ([], 0, {}))
        self.assertEqual(ptz.unifi_interval({"unifi_interval": "1"}), 2)
        self.assertEqual(ptz.unifi_interval({}), 5)
        service = Built.module("service")
        self.assertEqual(service.changed_parts({"unifi_enabled": False}, {"unifi_enabled": True}), {"ptz"})

    def test_unifi_log_only_mode(self):
        ctl_mod, kodiapi = Built.module("controller"), Built.module("kodiapi")
        rang = []
        self.addCleanup(setattr, kodiapi, "chime", kodiapi.chime)
        kodiapi.chime = lambda: rang.append(1)
        Built.store.update({"chime": "all"})
        self.addCleanup(Built.store.pop, "chime", None)
        ctl = ctl_mod.Controller()
        ctl._show = lambda *a: self.fail("log only must not open anything")
        self.assertEqual(ctl.show("garden", 10, "log", "alarm", "unifi", "Person"), "ignore")
        e = ctl.events[0]
        self.assertEqual((e["source"], e["action"], e["reason"], e["label"], rang),
                         ("unifi", "ignore", "log_only", "Person", []))

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
        self.assertEqual(ctl.colour_key("garden", "red"), "red")
        self.assertEqual(sent, [("garden", "red")])

    def test_cooldown_and_substreams(self):
        ctl_mod = Built.module("controller")
        sources = Built.module("sources")
        Built.store.update({"cooldown": "*=60", "camera": "garden", "substreams": "garden=garden_sub",
                            "server": self.go2rtc.url})
        try:
            ctl = ctl_mod.Controller()
            ctl._show = lambda *a: "show"
            self.assertEqual(ctl.show("garden"), "show")
            self.assertEqual(ctl.show("garden"), "ignore")
            self.assertEqual(ctl.events[0]["reason"], "cooldown:60")  # a code, translated on screen (#41)
            self.assertEqual(ctl.show("garden", priority="alarm"), "show")
            live, snap, _title = sources.camera_urls("garden")
            self.assertIn("src=garden_sub", live)
            self.assertIn("garden", snap)
            self.assertNotIn("garden_sub", snap)
        finally:
            for k in ("cooldown", "camera", "substreams", "server"):
                Built.store.pop(k, None)

    def test_window_ends_the_screensaver_first(self):
        """#119: a CamAlert window (every priority) first ends a running screensaver, CamAlert's own (#99) or
        another one, so it is not hidden behind it; without a screensaver nothing is sent."""
        ctl_mod, kodiapi = Built.module("controller"), Built.module("kodiapi")
        state = {"saver": True}
        sent = []
        for name in ("cond", "jsonrpc", "notify"):
            self.addCleanup(setattr, kodiapi, name, getattr(kodiapi, name))

        def cond(expr):
            return state["saver"] if expr == "System.ScreenSaverActive" else False

        def jsonrpc(method, params=None):
            sent.append((method, params))
            if method == "Input.ExecuteAction":
                state["saver"] = False  # Kodi ends the screensaver on any action
            return "OK"

        kodiapi.cond, kodiapi.jsonrpc = cond, jsonrpc
        kodiapi.notify = lambda *a, **kw: None
        Built.store.update({"camera": "garden", "server": self.go2rtc.url})
        try:
            ctl = ctl_mod.Controller()
            self.assertEqual(ctl.show("garden", 10, "notify", "normal", "api"), "show")
            self.assertIn(("Input.ExecuteAction", {"action": "noop"}), sent)
            del sent[:]
            ctl.last_shown.clear()
            self.assertEqual(ctl.show("garden", 10, "notify", "normal", "api"), "show")
            self.assertNotIn("Input.ExecuteAction", [m for m, _p in sent])  # no screensaver: nothing sent
        finally:
            for k in ("camera", "server"):
                Built.store.pop(k, None)

    def test_notification_says_the_priority(self):
        """#49: the notification has the label and, for high/alarm, the translated priority, like Enigma2."""
        ctl_mod, kodiapi = Built.module("controller"), Built.module("kodiapi")
        notified = []
        self.addCleanup(setattr, kodiapi, "notify", kodiapi.notify)
        kodiapi.notify = lambda heading, message, *a, **kw: notified.append(message)
        Built.store.update({"camera": "garden", "server": self.go2rtc.url})
        try:
            ctl = ctl_mod.Controller()
            self.assertEqual(ctl.show("garden", 10, "notify", "high", "api", "Person"), "show")
            ctl.last_shown.clear()
            self.assertEqual(ctl.show("garden", 10, "notify", "normal", "api"), "show")
        finally:
            for k in ("camera", "server"):
                Built.store.pop(k, None)
        self.assertEqual(len(notified), 2, notified)
        self.assertIn("Person", notified[0])
        self.assertTrue(notified[0].endswith("  ·  High"), notified[0])
        self.assertNotIn("·", notified[1])
        self.assertEqual(ctl_mod.notification_text("Garden", "alarm"), kodiapi.tr(30180).replace("%s", "Garden") + "  ·  Alarm")

    def test_status_screen(self):
        """#63: status "screen" on Kodi: mosaic/tour over the window over live view."""
        import types
        ctl = Built.module("controller").Controller()
        self.assertEqual(ctl.status()["screen"], "none")
        ctl.live_stream = "garden"
        self.assertEqual(ctl.status()["screen"], "live")
        ctl.window = types.SimpleNamespace(stream="garden", cams=self.CAMS[:1])
        self.assertEqual(ctl.status()["screen"], "photo")
        ctl.window.cams = self.CAMS
        self.assertEqual(ctl.status()["screen"], "strip")
        ctl.full = types.SimpleNamespace(tour=False)
        self.assertEqual(ctl.status()["screen"], "mosaic")
        ctl.full.tour = True
        self.assertEqual(ctl.status()["screen"], "tour")

    def test_no_chime_for_a_test_request(self):
        """#62: source "test" never plays the chime; the event keeps the source."""
        ctl_mod, kodiapi = Built.module("controller"), Built.module("kodiapi")
        rang = []
        self.addCleanup(setattr, kodiapi, "chime", kodiapi.chime)
        kodiapi.chime = lambda: rang.append(1)
        Built.store.update({"chime": "all", "camera": "garden"})
        try:
            ctl = ctl_mod.Controller()
            ctl._show = lambda *a: "show"
            self.assertEqual(ctl.show("garden", source="test"), "show")
            self.assertEqual((rang, ctl.events[0]["source"]), ([], "test"))
            ctl.last_shown.clear()
            self.assertEqual(ctl.show("garden", source="api"), "show")
            self.assertEqual(rang, [1])
            self.addCleanup(setattr, kodiapi, "cond", kodiapi.cond)
            kodiapi.cond = lambda expr: expr == "Player.Muted"  # #20: Kodi muted = no chime
            ctl.last_shown.clear()
            self.assertEqual(ctl.show("garden", source="api"), "show")
            self.assertEqual(rang, [1])
        finally:
            for k in ("chime", "camera"):
                Built.store.pop(k, None)

    def test_diagnostics_os_while_kodi_is_busy(self):
        """#59: System.OSVersionInfo answers "Busy" (translated) at first: retried, then Python's platform."""
        import types
        kodiapi, klogic = Built.module("kodiapi"), Built.module("klogic")
        self.assertEqual(klogic.os_label("Bezig", ("Busy", "Bezig"), "Linux 6.6"), "Linux 6.6")
        self.assertEqual(klogic.os_label(" ", ("Busy", ""), "Linux 6.6"), "Linux 6.6")
        self.assertEqual(klogic.os_label("LibreELEC 12.2", ("Busy",), "Linux"), "LibreELEC 12.2")
        answers = ["Bezig", "Bezig", "LibreELEC (official): 12.2.1"]
        fake = types.SimpleNamespace(getInfoLabel=lambda label: answers.pop(0) if answers else "Bezig",
                                     getLocalizedString=lambda i: "Bezig" if i == 503 else "", sleep=lambda ms: None)
        self.addCleanup(setattr, kodiapi, "xbmc", kodiapi.xbmc)
        kodiapi.xbmc = fake
        self.assertEqual(kodiapi.os_version(), "LibreELEC (official): 12.2.1")
        self.assertNotIn("Bezig", kodiapi.os_version())  # still busy after the retries: platform
        import inspect
        self.assertIn("kodiapi.os_version()", inspect.getsource(Built.module("diag").collect))

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

    def wait_for(self, cond, seconds=3.0):
        import time
        end = time.time() + seconds
        while time.time() < end and not cond():
            time.sleep(0.01)
        return cond()

    def test_unreachable_camera_changes_the_title(self):
        """#51: the active Feeder (one thread per tile) reports a camera that does not answer, and its recovery."""
        display = Built.module("display")
        sources = Built.module("sources")
        controller = Built.module("controller")
        with open(display.__file__, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual((text.count("\nclass Feeder("), text.count("\nclass PtzMode(")), (1, 1))  # no dead copies
        answers = {"ok": False}

        def download(url, path, verify=True):
            if not answers["ok"]:
                raise IOError("timed out")
            with open(path, "wb") as f:
                f.write(b"jpg")
            return path
        self.addCleanup(setattr, sources, "download", sources.download)
        sources.download = download
        w = display.PhotoWindow(FakeController(), self.CAMS[:1], self.settings(), keys=True)
        w.feeder.retry = 0.01
        labels = []
        w.label.setLabel = labels.append
        before = controller.STATS["unreachable"]
        w.feeder.start()
        try:
            self.assertTrue(self.wait_for(lambda: any("not reachable" in x for x in labels)), labels)
            self.assertIn("Front door - camera not reachable", labels)
            self.assertEqual(controller.STATS["unreachable"], before + 1)
            answers["ok"] = True
            self.assertTrue(self.wait_for(lambda: labels and "not reachable" not in labels[-1]), labels)
        finally:
            w.feeder.stop()

    def core_strings(self):
        """kodiapi with our strings.po; Kodi 'translates' every id as <id> so the test sees which ids are used."""
        kodiapi = Built.module("kodiapi")
        for name in ("addon_path", "tr"):
            self.addCleanup(setattr, kodiapi, name, getattr(kodiapi, name))
        self.addCleanup(setattr, kodiapi, "_core_ids", None)
        kodiapi.addon_path = lambda *p: os.path.join(ADDON, *p)
        kodiapi._core_ids = None
        return kodiapi

    def test_unreachable_tile_is_dimmed_with_text(self):
        """#49: every tile type shows a dimmed 'Camera not reachable' layer instead of a frozen or black picture.
        #110: until the first picture the layer says 'Loading picture...', and the first request asks go2rtc for a
        cached frame."""
        display = Built.module("display")
        sources = Built.module("sources")
        self.core_strings()
        down = {"garden"}
        asked = []

        def download(url, path, verify=True):
            asked.append(url)
            if any("src=%s&" % c in url for c in down):
                raise IOError("timed out")
            with open(path, "wb") as f:
                f.write(b"jpg")
            return path
        self.addCleanup(setattr, sources, "download", sources.download)
        sources.download = download

        def watch(win):
            seen = {}
            for tile in win.tiles:
                dim, text = tile["error"]
                self.assertEqual(text._args[4], "Loading picture...")
                labels = tile["labels"] = []
                text.setLabel = labels.append
                dim.setVisible = lambda v, n=tile["name"]: seen.__setitem__(n, v)
            win.feeder.retry = 0.01
            return seen

        strip = display.PhotoWindow(FakeController(), self.CAMS, self.settings(), keys=True)
        titles = []
        strip.label.setLabel = titles.append
        mosaic = display.FullScreen(FakeController(), self.CAMS, self.settings(), tour=False)
        tour = display.FullScreen(FakeController(), self.CAMS[::-1], self.settings(), tour=True)
        for win in (strip, mosaic, tour):
            seen = watch(win)
            win.feeder.start()
            try:
                self.assertTrue(self.wait_for(lambda: seen.get("garden") is True), (win, seen))
                bad = [t for t in win.tiles if t["name"] == "garden"][0]
                self.assertEqual(bad["labels"][-1], "Camera not reachable")
                if win is not tour:  # the camera that answers: its first picture hides 'Loading picture...'
                    self.assertTrue(self.wait_for(lambda: seen.get("front_door") is False), (win, seen))
                if win is tour:
                    down.clear()
                    self.assertTrue(self.wait_for(lambda: seen.get("garden") is False), seen)
                    down.add("garden")
            finally:
                win.feeder.stop()
        self.assertEqual(titles, [])  # a multi-camera window keeps its title; the tile says it
        front = [u for u in asked if "src=front_door&" in u]
        self.assertTrue(front and front[0].endswith("&cache=10s"), front[:2])

    def test_only_the_first_picture_is_cached(self):
        """#110: the first request of a tile asks go2rtc for a cached frame, the refreshes for a new one."""
        display = Built.module("display")
        sources = Built.module("sources")
        asked = []

        def download(url, path, verify=True):
            asked.append(url)
            with open(path, "wb") as f:
                f.write(b"jpg")
            return path
        self.addCleanup(setattr, sources, "download", sources.download)
        sources.download = download
        url = "http://192.168.1.10:1984/api/frame.jpeg?src=cache_test&width=640"  # feeders of other tests may
        win = display.PhotoWindow(FakeController(), [("cache_test", "Cache test", url)], self.settings(), keys=False)
        hidden = []  # still be finishing a download: only this camera's requests count
        win.tiles[0]["error"][0].setVisible = hidden.append
        win.feeder.start()
        mine = lambda: [u for u in asked if "src=cache_test&" in u]  # noqa: E731
        try:
            self.assertTrue(self.wait_for(lambda: len(mine()) >= 2, 10), asked)
        finally:
            win.feeder.stop()
        self.assertTrue(mine()[0].endswith("&cache=10s"), mine())
        self.assertFalse(mine()[1].endswith("&cache=10s"), mine())
        self.assertEqual(hidden[:1], [False])  # 'Loading picture...' hidden by the first picture

    def test_diagnostics_caller_uses_region_date_and_translated_source(self):
        diag = Built.module("diag")
        self.core_strings()
        when, who = diag.caller_text(1764000000, "ha")
        self.assertEqual(who, "Home Assistant")
        self.assertRegex(when, r"^\d\d.\d\d.\d{4} \d\d:\d\d:\d\d$")  # stubs: no region format -> English (UK)
        self.assertEqual(diag.caller_text(1764000000, "api")[1], "API")

    def test_key_hints_come_from_the_key_map(self):
        """#41: no hard-coded English hints; the photo window, PTZ, live, tour and mosaic hints are
        present.key_hint() texts, translated through Kodi string ids."""
        display = Built.module("display")
        with open(display.__file__, encoding="utf-8") as f:
            text = f.read()
        for old in ('"   OK = live', "< >  BACK", "MENU = PTZ", "PLAY = live", "  -  BACK", "OK = home  BACK"):
            self.assertFalse(old in text, old)
        kodiapi = self.core_strings()
        from camalert.camalert_core import present
        from camalert.camalert_core.i18n import no_translation
        english = present.key_hint("kodi", "window", no_translation, ptz_key="blue", glyphs=False)
        self.assertEqual(english, "OK = live   < > = other camera   BACK = close")  # Estuary has no \u25c0 \u25b6
        w = display.PhotoWindow(FakeController(), self.CAMS[:1], self.settings(), keys=True)
        hints = []
        w.hint_label.setLabel = hints.append
        w.ptz_label(False)
        self.assertEqual(hints[-1], english)  # Kodi has no strings yet: English from our strings.po
        kodiapi.tr = lambda i: "<%d>%s" % (i, " ".join(re.findall(r"%[ds]", kodiapi.english(i))))
        w.ptz_label(False)
        self.assertRegex(hints[-1], r"^OK = <305\d\d>   < > = <305\d\d>   BACK = <305\d\d>$")
        w.ptz_label(True)
        self.assertIn("CH+ CH- = <305", hints[-1])
        self.assertIsNone(display.PhotoWindow(FakeController(), self.CAMS, self.settings(), keys=True).hint_label)
        o = display.LiveOverlay(FakeController(), "garden", "Garden", self.settings())
        labels = []
        o.label.setLabel = labels.append
        o.ptz_label(False)
        self.assertTrue(labels[-1].startswith("Garden      "), labels)
        tour = display.FullScreen(FakeController(), self.CAMS, self.settings(), tour=True, interval=8)
        tour.title.setLabel = labels.append
        tour.update_title()
        self.assertTrue(labels[-1].startswith("Front door   (1/2, <305"), labels[-1])

    def test_event_list_shows_translated_values(self):
        """#41: the controller stores reason codes; the event list shows translated labels with the date."""
        script = Built.module("script")
        kodiapi = self.core_strings()
        ev = {"time": 1764000000, "camera": "garden", "label": "Person", "source": "frigate", "priority": "high",
              "action": "ignore", "reason": "cooldown:30", "snapshot": None}
        self.addCleanup(setattr, script, "service_state", script.service_state)
        script.service_state = lambda: {"events": [ev]}
        shown = []
        import xbmcgui
        self.addCleanup(setattr, xbmcgui.Dialog, "select", xbmcgui.Dialog.select)
        xbmcgui.Dialog.select = lambda self, heading, items, **kw: shown.extend(items) or -1
        script.events()
        self.assertEqual(len(shown), 1)
        self.assertIn("garden \u00b7 Person  (Frigate, High) -> Ignored", shown[0].label)
        self.assertIn("Reason: Cooldown (30 s)", shown[0].label2)
        kodiapi.tr = lambda i: "<%d>%s" % (i, " ".join(re.findall(r"%[ds]", kodiapi.english(i))))
        shown[:] = []
        script.events()
        self.assertNotIn("Frigate", shown[0].label)
        self.assertNotIn("Cooldown", shown[0].label2)

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
        for aid, button in ((79, 0), (122, 252)):  # PLAY, GREEN (colour action + button code): live (#2)
            ctl.calls = []
            ctl.show = lambda *a: ctl.calls.append(("show",) + a)
            display.FullScreen(ctl, self.CAMS, self.settings(), tour=True, interval=8).onAction(self.Action(aid, button))
            self.assertIn(("show", self.CAMS[0][0], None, "live", "high"), ctl.calls)
        ctl.calls = []
        display.FullScreen(ctl, self.CAMS, self.settings(), tour=True, interval=8).onAction(self.Action(122, 251))
        self.assertEqual(ctl.calls, [])  # RED does nothing in the tour
        if "mosaic labels" in KNOWN_STUB_PROBLEMS:  # fails like on a real Kodi; a fixed problem fails here too
            with self.assertRaises(TypeError, msg="fixed: remove 'mosaic labels' from KNOWN_STUB_PROBLEMS"):
                display.FullScreen(ctl, self.CAMS, self.settings(), tour=False)
            return
        mosaic = display.FullScreen(ctl, self.CAMS, self.settings(), tour=False)
        self.assertEqual(len(mosaic.tiles), 2)
        for aid in (7, 135, 92):  # OK (SELECT, ENTER) and BACK close the mosaic (#58); LEFT does nothing
            ctl.calls = []
            m = display.FullScreen(ctl, self.CAMS, self.settings(), tour=False)
            m.onAction(self.Action(1))
            self.assertEqual(ctl.calls, [])
            m.onAction(self.Action(aid))
            self.assertEqual(ctl.calls, [("closed",)], aid)

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
        Built.store.update({"live_volume": "50", "server": self.go2rtc.url})
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

    def test_live_still_until_the_camera_is_on_screen(self):
        """#91: a still picture at once (warm / Protect / go2rtc cache / frame.jpeg, in a thread), closed as soon as
        this camera's stream is on screen; a stream that is faster is never covered."""
        ctl_mod, display = Built.module("controller"), Built.module("display")
        Built.store.update({"server": self.go2rtc.url})
        self.addCleanup(Built.store.pop, "server", None)
        ctl = ctl_mod.Controller()
        ctl._show_overlay = lambda *a: None
        fetch, watch, calls = ctl._fetch_still, ctl._watch_still, []
        ctl._fetch_still = lambda *a: calls.append(("fetch", a))
        ctl._watch_still = lambda *a: calls.append(("watch", a))
        s = Built.module("kodiapi").settings()
        snap = "%s/api/frame.jpeg?src=garden&width=640" % self.go2rtc.url
        live = "%s/api/stream.mp4?src=garden" % self.go2rtc.url
        on_screen = []
        ctl._stream_on_screen = lambda url: url in on_screen
        ctl._live("garden", live, "Garden", 10, s, "normal", "none", "", 0, False, "show", snap)
        (k1, fa), (k2, wa) = calls  # both in threads: the live view starts at once
        self.assertEqual((k1, k2, fa[1], wa[0]), ("fetch", "watch", snap, live))
        fetch(*fa)
        self.assertIsInstance(ctl.still_win, display.LiveStillWindow)
        path = ctl.still_win.path
        self.assertTrue(os.path.exists(path))
        watch(*wa)  # not on screen within the maximum: the still stays until it expires
        self.assertIsNotNone(ctl.still_win)
        on_screen.append(live)
        watch(*wa)
        self.assertIsNone(ctl.still_win)
        self.assertFalse(os.path.exists(path))

        del calls[:]
        ctl.live_other(1)  # another camera: its own still and its own watcher
        (_k, fa2), (_k, wa2) = calls
        self.assertNotEqual(fa2[0], "garden")
        watch(*wa)  # the old watcher stops: its token is gone
        on_screen.append(wa2[0])
        watch(*wa2)  # stream faster than the picture
        fetch(*fa2)
        self.assertIsNone(ctl.still_win)

        del calls[:]
        ctl.live_other(1)
        (_k, fa3), _w = calls
        ctl.end_live()
        fetch(*fa3)
        self.assertIsNone(ctl.still_win)

    def test_live_still_window_keys(self):
        display = Built.module("display")
        ctl = FakeController()
        ctl.live_other = lambda step: ctl.calls.append(("other", step))
        w = display.LiveStillWindow(ctl, "/tmp/x.jpg")
        for aid in (1, 2, 92):
            w.onAction(self.Action(aid))
        self.assertEqual(ctl.calls, [("other", -1), ("other", 1), ("hide",)])

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

    def test_diagnostics_show_ready_cameras(self):
        """#111: the diagnostics (another interpreter) show each ready camera from the service state."""
        diag = Built.module("diag")
        state = {"warm": {"active": True, "cameras": {"front_door": 1.4, "garden": None}}}
        lines = [l for l in diag.collect(state) if "Ready:" in l]
        self.assertEqual(len(lines), 2, lines)
        self.assertIn("Ready: front_door (last picture 1 s ago)", lines[0])
        self.assertIn("Ready: garden not connected", lines[1])

    def test_helper_stream_is_not_a_camera(self):
        """#113: the stream behind 'Keep cameras ready' is left out of the camera list."""
        from fakes.go2rtc import CAMERAS
        fake = FakeGo2rtc(cameras=dict(CAMERAS, front_door_jpeg=(0, 0, 0))).start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        sources, kodiapi = Built.module("sources"), Built.module("kodiapi")
        old = (Built.store.get("server"), Built.store.get("ready_cameras"))
        self.addCleanup(Built.store.update, {"server": old[0], "ready_cameras": old[1] or ""})
        Built.store["server"] = fake.url
        Built.store["ready_cameras"] = ""
        self.assertIn("front_door_jpeg", sources.all_camera_names(kodiapi.settings()))
        Built.store["ready_cameras"] = "front_door=front_door_jpeg"
        names = sources.all_camera_names(kodiapi.settings())
        self.assertNotIn("front_door_jpeg", names)
        self.assertEqual(len(names), len(CAMERAS))

    def test_derived_stream_is_hidden_without_own_setting(self):
        """#117: a helper stream another player uses (ffmpeg:<camera>#...) is not a camera here either."""
        from fakes.go2rtc import CAMERAS
        fake = FakeGo2rtc(cameras=dict(CAMERAS, front_door_jpeg=(0, 0, 0)),
                          sources={"front_door_jpeg": "ffmpeg:front_door#video=mjpeg#width=640"}).start()
        self.addCleanup(fake.server_close)
        self.addCleanup(fake.shutdown)
        sources, kodiapi = Built.module("sources"), Built.module("kodiapi")
        old = (Built.store.get("server"), Built.store.get("ready_cameras"))
        self.addCleanup(Built.store.update, {"server": old[0], "ready_cameras": old[1] or ""})
        Built.store["server"] = fake.url
        Built.store["ready_cameras"] = ""
        names = sources.all_camera_names(kodiapi.settings())
        self.assertNotIn("front_door_jpeg", names)
        self.assertEqual(len(names), len(CAMERAS))

    def test_go2rtc_address_not_set(self):
        """#73: no default address. Not set = no network call, the diagnostics, the service start and the camera
        choice say so; a usable address or direct mode say nothing."""
        sources, diag, script, kodiapi = (Built.module(n) for n in ("sources", "diag", "script", "kodiapi"))
        for value, text in (("", "go2rtc address not set"), ("ftp://x", "No valid go2rtc address")):
            Built.store["server"] = value
            s = kodiapi.settings()
            self.assertEqual(sources.all_camera_names(s), [])
            self.assertIsNone(sources.camera_urls("garden", s))
            self.assertEqual(sources.go2rtc_problem(s), text)
            lines = [l for l in diag.collect({}) if "go2rtc" in l]
            self.assertEqual(len(lines), 1, lines)
            self.assertIn(text, lines[0])
            said = []
            self.addCleanup(setattr, script.xbmcgui.Dialog, "ok", script.xbmcgui.Dialog.ok)
            script.xbmcgui.Dialog.ok = lambda self, heading, message: said.append(message)
            script.choose_camera()
            self.assertEqual(said, [text])
        notified = []
        self.addCleanup(setattr, kodiapi, "notify", kodiapi.notify)
        kodiapi.notify = lambda heading, message, *a, **kw: notified.append(message)
        service = Built.module("service")
        for name in ("server", "mqtt", "ptz"):
            mod = Built.module(name)
            self.addCleanup(setattr, mod, "start", mod.start)
            mod.start = lambda *a: None
        Built.store["server"] = ""
        service.Service().start_all()
        self.assertEqual(notified, ["go2rtc address not set"])
        Built.store["server"] = self.go2rtc.url
        service.Service().start_all()
        self.assertEqual(len(notified), 1)
        self.assertIsNone(sources.go2rtc_problem(kodiapi.settings()))
        Built.store.update({"server": "", "source": "direct"})
        self.addCleanup(Built.store.pop, "source", None)
        self.assertIsNone(sources.go2rtc_problem(kodiapi.settings()))

    def test_default_go2rtc_address_is_empty(self):
        """#73: klogic and settings.xml have no default address; a saved one stays."""
        klogic = Built.module("klogic")
        self.assertEqual(klogic.DEFAULTS["server"], "")
        self.assertEqual(klogic.parse_settings({})["server"], "")
        self.assertEqual(klogic.parse_settings({"server": "http://192.168.1.10:1984"})["server"],
                         "http://192.168.1.10:1984")
        root = ET.parse(os.path.join(ADDON, "resources", "settings.xml")).getroot()
        server = [e for e in root.iter("setting") if e.get("id") == "server"][0]
        self.assertEqual(server.findtext("default") or "", "")
        self.assertEqual(server.find("constraints").findtext("allowempty"), "true")

    def password_setup(self, devices_text=None):
        """#55: a clean devices.conf (or none) and the stored settings restored afterwards."""
        ptz = Built.module("ptz")
        path = ptz.device_file()
        for p in (path, path + ".tmp"):
            if os.path.exists(p):
                os.remove(p)
        if devices_text is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(devices_text)
            os.chmod(path, 0o644)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        saved = dict(Built.store)
        self.addCleanup(lambda: (Built.store.clear(), Built.store.update(saved)))
        kodi_stubs.LOGGED[:] = []
        return ptz, path

    def assert_secret_nowhere(self, secret):
        """The password is not in the stored settings (= settings.xml), Kodi's log or camalert.log."""
        self.assertNotIn(secret, json.dumps(Built.store))
        self.assertFalse([m for m in kodi_stubs.LOGGED if secret in m])
        log = Built.module("kodiapi").camlog().path
        if os.path.exists(log):
            with open(log, encoding="utf-8") as f:
                self.assertNotIn(secret, f.read())

    def test_camera_password_moves_to_devices_conf(self):
        """#55: on service start (migration of an existing install) a camera password in the settings goes into
        devices.conf (0600, camera lines kept) and the setting is emptied; afterwards nothing changes."""
        cams = "front_door|onvif|192.168.1.10:80||\nprotect|unifi|192.168.1.1:443|viewer|console-pw\n"
        ptz, path = self.password_setup(cams)
        service = Built.module("service")
        Built.store.update({"ptz_user": "admin", "ptz_password": "Secr3t|pw"})
        svc = service.Service()
        self.assertEqual(Built.store["ptz_password"], "")
        self.assertEqual(Built.store["ptz_user"], "admin")  # the user name is no secret and stays
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text, cams + "*|default|*||Secr3t|pw\n")
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertFalse(os.path.exists(path + ".tmp"))
        self.assert_secret_nowhere("Secr3t")
        self.assertTrue([m for m in kodi_stubs.LOGGED if "moved from the add-on settings to devices.conf" in m])
        # cameras still get the default login, UniFi consoles keep their own
        devs = ptz.all_devices()
        self.assertEqual((devs["front_door"]["user"], devs["front_door"]["password"]), ("admin", "Secr3t|pw"))
        self.assertEqual(devs["protect"]["password"], "console-pw")
        # idempotent: a new start or settings change with an empty field changes nothing
        mtime = os.stat(path).st_mtime_ns
        self.assertFalse(svc.move_secrets())
        svc.settings_changed()
        self.assertEqual(os.stat(path).st_mtime_ns, mtime)
        # a new password typed in the settings replaces the stored one (one line), on settings change
        Built.store["ptz_password"] = "Other9"
        svc.settings_changed()
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text, cams + "*|default|*||Other9\n")
        self.assertEqual(Built.store["ptz_password"], "")
        self.assertEqual(svc.settings["ptz_password"], "")
        self.assert_secret_nowhere("Other9")

    def test_camera_password_without_devices_conf(self):
        """#55: no devices.conf yet: it is made with the example and the password line, owner only."""
        ptz, path = self.password_setup()
        Built.store["ptz_password"] = "Secr3t"
        self.assertTrue(ptz.move_camera_password())
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(ptz.EXAMPLE))
        self.assertEqual(ptz.default_login(), ("", "Secr3t"))
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertFalse(ptz.move_camera_password())

    def test_camera_password_kept_when_devices_conf_cannot_be_written(self):
        """#55: if devices.conf cannot be written the setting stays (cameras keep working) and the error is logged
        without the password; nothing half-written is left."""
        ptz, path = self.password_setup()
        Built.store["ptz_password"] = "Secr3t"
        self.addCleanup(setattr, ptz.os, "replace", ptz.os.replace)

        def fail(*a):
            raise OSError(13, "Permission denied")
        ptz.os.replace = fail
        self.assertFalse(ptz.move_camera_password())
        self.assertEqual(Built.store["ptz_password"], "Secr3t")
        self.assertFalse(os.path.exists(path + ".tmp"))
        self.assertEqual(ptz.all_devices({"ptz_user": "", "ptz_password": "Secr3t"}), {})
        self.assertTrue([m for m in kodi_stubs.LOGGED if "could not be moved" in m and "Permission denied" in m])
        self.assertFalse([m for m in kodi_stubs.LOGGED if "Secr3t" in m])
        # the service never stops on an unexpected error either
        ptz.os.replace = lambda *a: 1 / 0
        self.assertFalse(Built.module("service").Service.move_secrets())
        self.assertTrue([m for m in kodi_stubs.LOGGED if "not moved: ZeroDivisionError" in m])

    def menu_setup(self):
        """script.py with recording fakes: select answers, sent commands, called actions."""
        import types
        script = Built.module("script")
        xbmcgui = script.xbmcgui
        rec = types.SimpleNamespace(seen=[], answers=[], sent=[], calls=[], said=[])
        for name in ("select", "ok"):
            self.addCleanup(setattr, xbmcgui.Dialog, name, getattr(xbmcgui.Dialog, name))
        xbmcgui.Dialog.select = lambda self, heading, items, **kw: (rec.seen.append((heading, list(items))) or
                                                                   (rec.answers.pop(0) if rec.answers else -1))
        xbmcgui.Dialog.ok = lambda self, heading, message: rec.said.append(message)
        fakes = {"send": lambda **cmd: rec.sent.append(cmd), "events": lambda: rec.calls.append("events"),
                 "diagnostics": lambda: rec.calls.append("diagnostics"),
                 "open_settings": lambda: rec.calls.append("settings"),
                 "time": types.SimpleNamespace(sleep=lambda s: None, time=__import__("time").time)}
        for name, fake in fakes.items():
            self.addCleanup(setattr, script, name, getattr(script, name))
            setattr(script, name, fake)
        return script, rec

    MENU = ["Show mosaic", "Start tour", "Show camera", "Event list", "Diagnostics", "Settings", "Start the wizard again",
            "Export settings", "Import settings", "Undo the last import"]  # #7

    def test_menu_without_arguments(self):
        """#106: opening CamAlert from Add-ons > Program add-ons shows a choice list, not the settings."""
        script, rec = self.menu_setup()
        Built.store["camera"] = "garden"
        self.addCleanup(Built.store.pop, "camera", None)
        cases = [([0], [{"do": "mosaic"}], []), ([1], [{"do": "tour"}], []), ([3], [], ["events"]),
                 ([4], [], ["diagnostics"]), ([5], [], ["settings"]), ([-1], [], [])]
        for answers, sent, calls in cases:
            rec.seen[:], rec.sent[:], rec.calls[:] = [], [], []
            rec.answers[:] = answers
            script.run([])
            self.assertEqual(rec.seen[0], ("CamAlert", self.MENU), answers)
            self.assertEqual((rec.sent, rec.calls), (sent, calls), answers)
        # Show camera: a camera picker, the chosen camera is shown; the default camera setting stays as it was
        rec.seen[:] = []
        rec.answers[:] = [2, 1]
        script.run([])
        heading, titles = rec.seen[1]
        self.assertEqual(heading, "Choose camera")
        self.assertEqual(len(titles), 4)
        names = Built.module("sources").all_camera_names(Built.module("kodiapi").settings())
        self.assertEqual(rec.sent, [{"do": "show", "cam": names[1]}])
        self.assertEqual(Built.store["camera"], "garden")
        rec.sent[:] = []
        rec.answers[:] = [2, -1]  # picker cancelled: nothing happens
        script.run([])
        self.assertEqual(rec.sent, [])

    def picker_setup(self, raw):
        """#50: script.py with recording dialogs and a fixed camera list; raw = {setting: text}."""
        script, rec = self.menu_setup()
        xbmcgui = script.xbmcgui
        rec.inputs, rec.multi, rec.yes, rec.saved = [], [], [], {}
        for name in ("input", "multiselect", "yesno"):
            self.addCleanup(setattr, xbmcgui.Dialog, name, getattr(xbmcgui.Dialog, name))
        xbmcgui.Dialog.input = lambda self, heading, defaultt="", **kw: (rec.seen.append((heading, defaultt)) or
                                                                        (rec.inputs.pop(0) if rec.inputs else ""))
        xbmcgui.Dialog.multiselect = lambda self, heading, options, preselect=None, **kw: (
            rec.seen.append((heading, list(options), list(preselect or []))) or (rec.multi.pop(0) if rec.multi else None))
        xbmcgui.Dialog.yesno = lambda self, heading, message, **kw: rec.yes.pop(0) if rec.yes else False
        fakes = {"camera_names": lambda: ["back_door", "front_door", "garden"],
                 "raw_setting": lambda key: raw.get(key, ""),
                 "save_setting": lambda key, value: rec.saved.__setitem__(key, value)}
        for name, fake in fakes.items():
            self.addCleanup(setattr, script, name, getattr(script, name))
            setattr(script, name, fake)
        return script, rec

    def test_pickers_per_camera(self):
        """#50: per-camera settings edited with choice lists instead of typing name=value|... by hand."""
        cases = [  # setting, raw before, select answers, input answers, saved
            ("orientation", "garden=rot180", [1, 1], [], "front_door=mirror|garden=rot180"),
            ("orientation", "garden=rot180", [2, 0], [], ""),  # normal = remove
            ("refresh", "", [0, 3], [], "back_door=5"),
            ("cooldown", "garden=120", [0, 2], [], "*=30|garden=120"),  # first entry = all cameras
            ("cooldown", "*=30|garden=120", [3, 0], [], "*=30"),  # off = remove
            ("substreams", "", [1, 2], [], "front_door=garden"),
            ("substreams", "front_door=garden", [1, 0], [], ""),  # the camera itself = remove
            ("titles", "garden=Tuin", [0], ["Achter"], "back_door=Achter|garden=Tuin"),
        ]
        for setting, raw, answers, inputs, saved in cases:
            script, rec = self.picker_setup({setting: raw})
            rec.answers[:], rec.inputs[:] = answers, inputs
            script.run(["pick", setting])
            self.assertEqual(rec.saved, {setting: saved}, (setting, raw, answers))
        # the camera list shows the current value next to each camera
        script, rec = self.picker_setup({"orientation": "garden=rot180"})
        rec.answers[:] = [-1]
        script.run(["pick", "orientation"])
        heading, items = rec.seen[0]
        self.assertEqual(heading, "Choose camera")
        self.assertEqual(len(items), 3)
        self.assertIn("turned 180 degrees", items[2])
        self.assertEqual(rec.saved, {})  # cancelled: nothing saved

    def test_picker_titles_empty_name(self):
        """#50: Kodi returns '' for a cancelled keyboard too: an existing name is only removed after a yes."""
        script, rec = self.picker_setup({"titles": "garden=Tuin"})
        rec.answers[:], rec.inputs[:], rec.yes[:] = [2], [""], [False]
        script.run(["pick", "titles"])
        self.assertEqual(rec.saved, {})
        script, rec = self.picker_setup({"titles": "garden=Tuin"})
        rec.answers[:], rec.inputs[:], rec.yes[:] = [2], [""], [True]
        script.run(["pick", "titles"])
        self.assertEqual(rec.saved, {"titles": ""})

    def test_picker_mosaic(self):
        """#50: mosaic cameras with a multiselect; at most 9; nothing chosen = all cameras."""
        script, rec = self.picker_setup({"mosaic": "garden"})
        rec.multi[:] = [[0, 2]]
        script.run(["pick", "mosaic"])
        self.assertEqual(rec.saved, {"mosaic": "back_door,garden"})
        self.assertEqual(rec.seen[0][2], [2])  # preselected: the current mosaic cameras
        script, rec = self.picker_setup({"mosaic": "garden"})
        rec.multi[:] = [[]]
        script.run(["pick", "mosaic"])
        self.assertEqual(rec.saved, {"mosaic": ""})
        script, rec = self.picker_setup({"mosaic": "garden"})
        rec.multi[:] = [None]  # cancelled
        script.run(["pick", "mosaic"])
        self.assertEqual(rec.saved, {})

    def test_picker_limits_and_unknown(self):
        script, rec = self.picker_setup({})
        script.camera_names = lambda: ["c%d" % i for i in range(12)]
        rec.multi[:] = [list(range(12))]
        script.run(["pick", "mosaic"])
        self.assertEqual(rec.saved["mosaic"], ",".join("c%d" % i for i in range(9)))
        self.assertEqual(len(rec.said), 1)  # said that only 9 are used
        script, rec = self.picker_setup({})
        script.camera_names = lambda: None  # no go2rtc: camera_names already said why
        script.run(["pick", "orientation"])
        self.assertEqual((rec.saved, rec.seen), ({}, []))
        script.run(["pick", "nonsense"])
        self.assertEqual(rec.saved, {})

    def test_picker_buttons_in_settings(self):
        """#50: every per-camera setting has a button right below it that opens its picker."""
        import xml.etree.ElementTree as ET
        tree = ET.parse(os.path.join(_paths.KODI_ADDON, "resources", "settings.xml"))
        for group in tree.iter("group"):
            ids = [s.get("id") for s in group.findall("setting")]
            for setting in ("titles", "orientation", "refresh", "cooldown", "substreams", "mosaic"):
                if setting in ids:
                    nxt = group.findall("setting")[ids.index(setting) + 1]
                    self.assertEqual(nxt.get("type"), "action", setting)
                    self.assertEqual(nxt.find("data").text, "RunScript(service.camalert,pick,%s)" % setting)

    def test_menu_settings_and_old_arguments(self):
        """#106: RunScript(service.camalert,settings) still opens the settings; the old buttons still work."""
        script, rec = self.menu_setup()
        script.run(["settings"])
        script.run(["mosaic"])
        script.run(["tour"])
        self.assertEqual(rec.calls, ["settings"])
        self.assertEqual(rec.sent, [{"do": "mosaic"}, {"do": "tour"}])
        self.assertEqual(rec.seen, [])

    def test_menu_show_camera_without_go2rtc(self):
        """#106/#73: no go2rtc address: the menu says why instead of an empty camera list."""
        script, rec = self.menu_setup()
        Built.store["server"] = ""
        Built.store["wizard_done"] = "true"  # the wizard was left (#120): the menu opens
        self.addCleanup(Built.store.pop, "wizard_done", None)
        rec.answers[:] = [2]
        script.run([])
        self.assertEqual(rec.said, ["go2rtc address not set"])
        self.assertEqual(rec.sent, [])
        self.assertEqual(len(rec.seen), 1)

    def test_wizard_on_first_start(self):
        """#120: without go2rtc address and before the wizard ran, opening the add-on starts the wizard: the search
        result, a camera with a preview (a test request: no chime), the test notification and the HA hint."""
        import types
        script = Built.module("script")
        kw = Built.module("kwizard")
        saved = {k: Built.store.get(k) for k in ("server", "camera", "wizard_done", "source")}
        for k, v in saved.items():
            self.addCleanup(lambda k=k, v=v: Built.store.__setitem__(k, v) if v is not None else Built.store.pop(k, None))
        Built.store["server"], Built.store["source"] = "", "go2rtc"
        Built.store.pop("wizard_done", None)
        sent, said = [], []

        class Dialog(object):
            def __init__(self, selects, yesnos):
                self.selects, self.yesnos, self.seen = list(selects), list(yesnos), []

            def select(self, heading, items, preselect=-1):
                self.seen.append((heading, list(items)))
                return self.selects.pop(0)

            def yesno(self, heading, message):
                said.append(message)
                return self.yesnos.pop(0)

            def ok(self, heading, message):
                said.append(message)

            def input(self, heading, defaultt=""):
                return ""

        for name, fake in (("search", lambda progress=None: [("http://192.168.1.10:1984", ["front_door", "garden"])]),
                           ("send", lambda **cmd: sent.append(cmd))):
            self.addCleanup(setattr, kw, name, getattr(kw, name))
            setattr(kw, name, fake)
        core = kw.core
        self.addCleanup(setattr, core, "own_ip", core.own_ip)
        core.own_ip = lambda *a: "192.168.1.40"
        self.assertTrue(kw.should_start())
        d = Dialog([0, 0, 1], [False, True, True])  # go2rtc, front_door (not right), garden (right), test: yes
        saved_values = kw.run(dialog=d, wait=lambda s: None)
        self.assertEqual(d.seen[0][1][0], "http://192.168.1.10:1984 (2 cameras)")
        self.assertEqual(d.seen[1], ("Which camera should CamAlert show by default?", ["front_door", "garden"]))
        self.assertEqual([c for c in sent if c["do"] == "show"],
                         [{"do": "show", "cam": "front_door", "mode": "photo", "seconds": 15, "test": True},
                          {"do": "show", "cam": "garden", "mode": "photo", "seconds": 15, "test": True},
                          {"do": "show", "cam": "garden", "mode": "notify", "seconds": 10, "test": True}])
        self.assertEqual(saved_values, {"wizard_done": True, "source": "go2rtc", "server": "http://192.168.1.10:1984",
                                        "camera": "garden"})
        self.assertEqual((Built.store["server"], Built.store["camera"], Built.store["wizard_done"]),
                         ("http://192.168.1.10:1984", "garden", "true"))
        self.assertIn("Address: 192.168.1.40:8099", said[-1])
        self.assertFalse(kw.should_start())
        # leaving early (BACK in the first list) also ends it for good
        Built.store["server"] = ""
        Built.store.pop("wizard_done", None)
        self.assertEqual(kw.run(dialog=Dialog([-1], [])), {"wizard_done": True})
        self.assertEqual(Built.store["server"], "")

    def test_wizard_service_command_is_a_test(self):
        """#120: the wizard's preview/test command reaches the controller as a test request with its seconds."""
        import json
        import types
        svc = Built.module("service")
        seen = []
        fake = types.SimpleNamespace(ctl=types.SimpleNamespace(show=lambda *a: seen.append(a)))
        win = sys.modules["xbmcgui"].Window
        cmd = json.dumps({"do": "show", "cam": "garden", "mode": "notify", "seconds": 10, "test": True})
        for name, fn in (("getProperty", lambda self, key: cmd if key == "camalert.cmd" else ""),
                         ("clearProperty", lambda self, key: None)):
            self.addCleanup(setattr, win, name, getattr(win, name, None))
            setattr(win, name, fn)
        svc.Service.script_commands(fake)
        self.assertEqual(seen, [("garden", 10, "notify", "high", "test")])

    def test_change_camera_password_button(self):
        """#55: the settings button shows whether a password is stored (never the password) and changes or removes
        it directly in devices.conf; the input dialog hides what is typed."""
        ptz, path = self.password_setup("garden|foscam|192.168.1.11:88||\n")
        script = Built.module("script")
        xbmcgui = script.xbmcgui
        seen, said, answers, inputs = [], [], [], []
        for name in ("select", "input", "ok"):
            self.addCleanup(setattr, xbmcgui.Dialog, name, getattr(xbmcgui.Dialog, name))
        xbmcgui.Dialog.select = lambda self, heading, items, **kw: seen.append((heading, list(items))) or answers.pop(0)
        xbmcgui.Dialog.input = lambda self, heading, *a, **kw: inputs.append(kw) or "N3w|pw"
        xbmcgui.Dialog.ok = lambda self, heading, message: said.append(message)
        answers += [0]
        script.run(["camera_password"])
        self.assertEqual(seen[0], ("Camera password (default): Not set", ["Change password"]))
        self.assertEqual(inputs[0]["option"], xbmcgui.ALPHANUM_HIDE_INPUT)
        self.assertEqual(ptz.default_login(), ("", "N3w|pw"))
        self.assertEqual(said, ["Camera password stored in devices.conf."])
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        answers += [-1]  # cancelled: nothing changes
        script.run(["camera_password"])
        self.assertEqual(seen[1], ("Camera password (default): \u2022\u2022\u2022\u2022 (stored)",
                                   ["Change password", "Remove stored password"]))
        self.assertNotIn("N3w", json.dumps(seen))
        xbmcgui.Dialog.input = lambda self, heading, *a, **kw: ""  # empty input = no change
        answers += [0]
        script.run(["camera_password"])
        self.assertEqual(ptz.default_login()[1], "N3w|pw")
        answers += [1]
        script.run(["camera_password"])
        self.assertEqual(ptz.default_login(), ("", ""))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "garden|foscam|192.168.1.11:88||\n")
        self.assertEqual(said[-1], "Camera password removed.")
        # a password typed in the settings field just before is moved first
        Built.store["ptz_password"] = "Typed1"
        answers += [-1]
        script.run(["camera_password"])
        self.assertEqual(Built.store["ptz_password"], "")
        self.assertTrue(seen[-1][0].endswith("(stored)"))
        self.assert_secret_nowhere("Typed1")

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
        """Every name from the core or klogic.py that a Kodi module uses must be imported."""
        import importcheck
        self.assertEqual(importcheck.check_folder(_paths.KODI_LIB, ("klogic.py",)), {})


class TestKodiPackage(unittest.TestCase):
    def test_zip(self):
        b = Built.get()
        self.assertEqual(os.path.basename(b.addon_zip), "service.camalert-%s.zip" % build_kodi.version())
        names = zipfile.ZipFile(b.addon_zip).namelist()
        self.assertTrue(all(n.startswith("service.camalert/") for n in names))
        for f in ("addon.xml", "service.py", "default.py", "LICENSE.txt", "resources/settings.xml", "resources/icon.png",
                  "resources/fanart.jpg", "resources/lib/camalert/camalert_core/rules.py",
                  "resources/lib/camalert/controller.py", "resources/lib/camalert/camalert_core/obs/camlog.py",
                  "resources/media/chime.wav"):
            self.assertIn("service.camalert/" + f, names)
        for lang in LANGS:
            self.assertIn("service.camalert/resources/language/resource.language.%s/strings.po" % lang, names)
        self.assertFalse([n for n in names if n.endswith(".pyc") or "__pycache__" in n])
        # the whole core is in the zip, as it is in the source tree
        z = zipfile.ZipFile(b.addon_zip)
        for f in os.listdir(_paths.CORE):
            if f.endswith(".py"):
                self.assertEqual(z.read("service.camalert/resources/lib/camalert/camalert_core/" + f),
                                 open(os.path.join(_paths.CORE, f), "rb").read(), f)

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
