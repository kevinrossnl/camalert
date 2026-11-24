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

    def set_webhook(self, url):
        self.webhook = url

    def log_tail(self, lines):
        return ["a", "token=secret"][-lines:]

    def metrics(self):
        return "camalert_uptime_seconds 1\ncamalert_requests_total{key=\"show\"} 0\n"

    def status_extra(self):
        return {"mqtt": False}

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
              "http://ha.home.arpa/x", "http://8.8.8.8/x")
        for url in ok[:-1]:
            self.assertEqual(api.local_url(url, "192.168.1.5"), url)
        self.assertEqual(api.local_url(ok[-1], "8.8.8.8"), ok[-1])  # the caller itself
        for url in ("http://8.8.8.8/x", "https://example.com/x", "file:///etc/passwd", "http://:80/x",
                    "http://[zz/x"):
            with self.assertRaises(api.Invalid):
                api.local_url(url, "192.168.1.5")

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
        self.assertEqual(b.status_extra(), {})
        self.assertIsNone(b.log("x"))

    def test_payload(self):
        self.assertEqual(json.loads(api.Response(200, {"a": 1}).payload()), {"a": 1})
        self.assertEqual(api.Response(200, "x", "text/plain").payload(), b"x")


if __name__ == "__main__":
    unittest.main()
