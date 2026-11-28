"""camalert_core.api: the HTTP API in core (#5), run directly with a fake backend: the whole contract table
(tests/contract/api_table.py) plus the parts the table does not reach."""
import json
import unittest

import _paths

_paths.core()
from camalert_core import api  # noqa: E402
from contract.api_table import TABLE  # noqa: E402
from contract.test_http_contract import differences  # noqa: E402
from contract.adapters import Answer, DEFAULTS  # noqa: E402
from fakes.controller import RecordingController  # noqa: E402
from urllib.parse import urlencode  # noqa: E402


class FakeBackend(api.Backend):
    platform, version = "test", "9.9"

    def __init__(self):
        self.values, self.ctl, self.logged, self.webhook, self.camera_list = dict(DEFAULTS), None, [], None, []

    def settings(self):
        return self.values

    def controller(self):
        return self.ctl

    def node(self):
        return "node1", "CamAlert test"

    def cameras(self):
        if self.camera_list is None:
            raise OSError("go2rtc down")
        return [{"name": n, "title": n.replace("_", " ").capitalize(), "snapshot": True} for n in self.camera_list]

    def set_webhook(self, url, secret=""):
        self.webhook = url
        self.secret = secret

    def set_display(self, key, value):
        self.values[key] = value

    def set_setup(self, server, camera):
        self.values["server"] = server
        if camera:
            self.values["camera"] = camera

    def log_tail(self, lines):
        return ["a", "token=secret"][-lines:]

    def metrics(self):
        return "camalert_uptime_seconds 1\ncamalert_requests_total{key=\"show\"} 0\n"

    def status_extra(self):
        return {"mqtt": False}

    def start_update(self, version):  # #126: the player would download and install in the background
        self.ctl.calls.append(("update", version))
        self.update_state = "downloading"

    def update_status(self):
        return {"update_state": getattr(self, "update_state", "idle"), "update_version": None, "update_error": None}

    def log(self, message, level="normal"):
        self.logged.append((level, message))


class CoreAdapter(object):
    """The contract table straight against api.handle()."""
    platform = "core"

    def __init__(self):
        self.b = FakeBackend()

    def reset(self):
        api.LIMIT.seen.clear()
        api.WARNED.clear()

    def set_cameras(self, names):
        self.b.camera_list = names or []

    def call(self, req, ctl=None):
        self.b.ctl = ctl or RecordingController()
        self.b.values = dict(req.settings)
        self.b.update_state = "idle"  # every row starts on an idle player (#126)
        args, body, ctype = req.args, b"", ""
        if req.method == "POST" and req.body is None:
            args, body, ctype = {}, urlencode(req.args).encode(), "application/x-www-form-urlencoded"
        elif req.body is not None:
            body, ctype = req.body, "application/json"
        resp = api.handle(self.b, api.Request(req.method, req.path, args, req.ip, req.header, req.user_agent, body,
                                              ctype))
        return Answer(resp.code, resp.body, resp.content_type.split(";")[0], self.b.ctl, resp.headers)


class TestApiContract(unittest.TestCase):
    def test_contract_table(self):
        a = CoreAdapter()
        found = ["%s: %s" % (r["name"], "; ".join(d)) for r in TABLE for d in [differences(a, r)] if d]
        self.assertEqual(found, [])


class TestApiDetails(unittest.TestCase):
    def setUp(self):
        api.LIMIT.seen.clear()
        api.WARNED.clear()
        self.b = FakeBackend()
        self.b.ctl = RecordingController()

    def call(self, path, method="GET", args=None, ip="192.168.1.5", token=None, body=b"", ctype=""):
        return api.handle(self.b, api.Request(method, path, args, ip, token, "", body, ctype))

    def test_route_of(self):
        self.assertEqual(api.route_of("/camalert/show/").name, "show")
        self.assertEqual(api.route_of("/camalert").name, "camalert")
        self.assertIsNone(api.route_of("/other/show"))
        self.assertIsNone(api.route_of("/camalertx/show"))

    def test_status(self):
        out = self.call("/camalert/status").body
        self.assertEqual((out["platform"], out["api_version"], out["min_ha_version"]), ("test", 1, api.MIN_HA_VERSION))
        self.assertEqual(out["capabilities"], list(api.CAPABILITIES))
        self.assertEqual((out["id"], out["mqtt"]), ("node1", False))

    def test_screen(self):
        """#63: status says what is on screen; a controller without "screen" gets it from window/live."""
        self.assertEqual(self.call("/camalert/status").body["screen"], "none")
        self.b.ctl.status = lambda: {"window": "garden", "live": None, "paused": False, "dnd": False}
        self.assertEqual(self.call("/camalert/status").body["screen"], "photo")
        self.b.ctl.status = lambda: {"window": None, "live": "garden", "paused": False, "dnd": False}
        self.assertEqual(self.call("/camalert/status").body["screen"], "live")
        self.b.ctl.status = lambda: {"window": None, "live": None, "paused": False, "dnd": False, "screen": "tour"}
        self.assertEqual(self.call("/camalert/status").body["screen"], "tour")
        self.assertEqual(api.screen_name(), "none")
        self.assertEqual(api.screen_name("mosaic", "photo", True, True), "mosaic")
        self.assertEqual(api.screen_name(None, "strip", True, True), "strip")
        self.assertEqual(api.screen_name(None, None, True, True), "notification")
        self.assertEqual(api.screen_name(None, None, False, True), "live")
        self.assertEqual(api.screen_name("bogus"), "none")
        self.assertIn("screen", api.CAPABILITIES)

    def test_test_flag(self):
        """#62: test=1 on any request makes the caller source "test" (also last_caller); 0 keeps it; else 400."""
        out = self.call("/camalert/mosaic", "POST", {"test": "1"})
        self.assertEqual(out.code, 200)
        self.assertEqual(self.b.ctl.last_caller[2], "test")
        self.assertEqual(self.b.ctl.calls[-1], ("mosaic", None, 60))  # the flag is not passed on as a parameter
        self.call("/camalert/show", "POST", body=b'{"cam": "garden", "test": true}', ctype="application/json")
        self.assertEqual(self.b.ctl.calls[-1], ("show", "garden", None, None, None, "test", None))
        self.call("/camalert/show", "POST", {"cam": "garden", "test": "0"})
        self.assertEqual(self.b.ctl.calls[-1][5], "api")
        bad = self.call("/camalert/show", "POST", {"cam": "garden", "test": "x"})
        self.assertEqual((bad.code, bad.body["error"]), (400, "test must be 1 or 0"))
        self.assertIn("test", api.CAPABILITIES)

    def test_query_token_and_exposure_are_logged_once(self):
        self.b.values.update(token="secret")
        for _ in range(3):
            self.assertEqual(self.call("/camalert/status", args={"token": "secret"}).code, 200)
        self.assertEqual(sum("token in the URL" in m for _l, m in self.b.logged), 1)
        self.assertFalse(any("secret" in m for _l, m in self.b.logged))
        self.b.values.update(token="", allow="any")
        self.call("/camalert/status", ip="8.8.8.8")
        self.call("/camalert/status", ip="8.8.8.8")
        self.assertEqual(sum("outside the local network" in m for _l, m in self.b.logged), 1)

    def test_get_action_deprecation_logged_once(self):
        for _ in range(2):
            self.assertEqual(self.call("/camalert/hide").headers, {"Deprecation": "true"})
        self.assertEqual(sum("use POST" in m for _l, m in self.b.logged), 1)

    def test_verbose_log_is_redacted(self):
        self.call("/camalert/show", "POST", body=b'{"cam": "garden", "label": "pwd=hunter2"}')
        line = [m for lvl, m in self.b.logged if lvl == "verbose"][0]
        self.assertIn("POST /camalert/show", line)
        self.assertNotIn("hunter2", line)

    def test_method_and_errors(self):
        resp = self.call("/camalert/hide", "DELETE")
        self.assertEqual((resp.code, resp.headers["Allow"]), (405, "GET, POST"))
        self.b.settings = lambda: 1 / 0
        self.assertEqual(self.call("/camalert/status").code, 500)

    def test_bodies(self):
        self.assertEqual(api.parse_body("application/json", b'{"sec": 20, "on": true, "x": null}'),
                         {"sec": "20", "on": "true", "x": ""})
        self.assertEqual(api.parse_body("application/x-www-form-urlencoded", b"cam=a&sec="), {"cam": "a", "sec": ""})
        self.assertEqual(api.parse_body("", b""), {})
        for bad in (b"[1]", b"{nope"):
            with self.assertRaises(api.Invalid):
                api.parse_body("application/json", bad)
        resp = self.call("/camalert/dnd", "POST", body=b'{"on": true}', ctype="application/json")
        self.assertEqual(resp.body["dnd"], True)

    def test_local_url(self):
        ok = ("http://192.168.1.20:8123/x", "https://[fd00::1]/x", "http://homeassistant/x", "http://ha.local/x",
              "http://ha.home.arpa/x", "http://ha.lan.example/x", "http://8.8.8.8/x")
        lan = lambda host: ["192.168.1.20"] if host == "ha.lan.example" else []  # noqa: E731
        for url in ok[:-1]:
            self.assertEqual(api.local_url(url, "192.168.1.5", lan), url)
        self.assertEqual(api.local_url(ok[-1], "8.8.8.8"), ok[-1])  # the caller itself
        for url in ("http://8.8.8.8/x", "https://example.com/x", "file:///etc/passwd", "http://:80/x",
                    "http://[zz/x", "http://198.51.100.7/x"):
            with self.assertRaises(api.Invalid):
                api.local_url(url, "192.168.1.5", lambda host: ["203.0.113.10"])
        self.assertTrue(api.ROUTES["webhook"].blocking)  # resolving a name blocks: Enigma2 answers from a thread

    def test_cameras_failure_and_webhook(self):
        self.b.camera_list = None
        self.assertEqual(self.call("/camalert/cameras").body, {"result": False, "error": "camera source not reachable"})
        self.assertEqual(self.call("/camalert/webhook", "POST", {"url": "http://192.168.1.20/h"}).body["webhook"], True)
        self.assertEqual(self.b.webhook, "http://192.168.1.20/h")

    def test_backend_interface(self):
        b = api.Backend()
        for name in ("settings", "controller", "node", "cameras", "log_tail", "metrics"):
            with self.assertRaises(NotImplementedError):
                getattr(b, name)() if name not in ("log_tail",) else b.log_tail(1)
        with self.assertRaises(NotImplementedError):
            b.set_webhook("")
        with self.assertRaises(NotImplementedError):
            b.set_display("size", "small")
        with self.assertRaises(NotImplementedError):
            b.set_setup("http://192.168.1.10:1984", None)
        self.assertEqual(b.status_extra(), {})
        self.assertIsNone(b.log("x"))

    def test_window_settings(self):
        """#84: position and size are read and saved, only when they change, with their schema choices."""
        self.assertEqual(api.DISPLAY_SETTINGS["size"], ("small", "medium", "large"))
        self.b.values.update(position="top_right", size="medium")
        r = self.call("/camalert/settings", "POST", {"size": "large"})
        self.assertEqual(r.body, {"result": True, "position": "top_right", "size": "large"})
        self.assertEqual(self.b.values["size"], "large")
        self.assertIn(("normal", "window size set to large"), self.b.logged)
        logged = len(self.b.logged)
        self.call("/camalert/settings", "POST", {"size": "large"})  # unchanged: nothing saved, nothing logged
        self.assertEqual([m for m in self.b.logged[logged:] if "window" in m[1]], [])
        st = self.call("/camalert/status").body
        self.assertEqual((st["position"], st["size"]), ("top_right", "large"))
        self.assertIn("settings", st["capabilities"])
        self.assertEqual(self.call("/camalert/settings", "POST", {"position": "centre"}).code, 400)
        self.assertEqual(self.b.values["position"], "top_right")

    def test_setup(self):
        """#122: Home Assistant may set the go2rtc address of a player that was never set up (any address), or
        send a local-network address to one that was; status says whether the player is set up."""
        self.assertFalse(api.configured({"server": "", "source": "go2rtc"}))
        self.assertFalse(api.configured({}))  # a player without source / wizard_done: go2rtc, wizard not done
        self.assertTrue(api.configured({"server": "http://192.168.1.10:1984"}))
        self.assertTrue(api.configured({"server": "", "source": "direct"}))
        self.assertTrue(api.configured({"server": "", "wizard_done": True}))
        self.assertTrue(api.configured({"server": "not an address"}))  # set, even if wrong: only the LAN may fix it
        self.assertFalse(self.call("/camalert/status").body["configured"])
        self.assertIn("setup", self.call("/camalert/status").body["capabilities"])
        r = self.call("/camalert/setup", "POST", {"server": "https://ha.public.example:1984", "camera": "garden"})
        self.assertEqual((r.code, r.body["server"], r.body["camera"]), (200, "https://ha.public.example:1984", "garden"))
        self.assertEqual((self.b.values["server"], self.b.values["camera"]), ("https://ha.public.example:1984", "garden"))
        self.assertTrue(any("set up by 192.168.1.5" in m for _, m in self.b.logged))
        self.assertTrue(self.call("/camalert/status").body["configured"])
        r = self.call("/camalert/setup", "POST", {"server": "http://8.8.8.8:1984"})  # now set up: internet refused
        self.assertEqual((r.code, r.body), (409, {"result": False, "error": "already set up"}))
        self.assertEqual(self.b.values["server"], "https://ha.public.example:1984")
        r = self.call("/camalert/setup", "POST", {"server": "192.168.1.30"})  # LAN: allowed, default port
        self.assertEqual((r.code, self.b.values["server"]), (200, "http://192.168.1.30:1984"))
        self.b.values.update(server="", wizard_done=True)  # the wizard ran and chose direct / no go2rtc yet
        self.assertEqual(self.call("/camalert/setup", "POST", {"server": "http://8.8.8.8:1984"}).code, 409)
        self.assertEqual(self.call("/camalert/setup", "POST", {"server": "ftp://192.168.1.10"}).code, 400)

    def test_payload(self):
        self.assertEqual(json.loads(api.Response(200, {"a": 1}).payload()), {"a": 1})
        self.assertEqual(api.Response(200, "x", "text/plain").payload(), b"x")


if __name__ == "__main__":
    unittest.main()
