"""The Home Assistant integration's API client against the real API of both players (#4, #5): every call the
integration makes works on Enigma2 and on Kodi, with POST + token header (API version 1)."""
import asyncio
import json as _json
import sys
import unittest
from urllib.parse import parse_qsl, urlsplit

import _paths
from contract.adapters import Enigma2Adapter, KodiAdapter, Request
from fakes.controller import RecordingController

_paths.add(_paths.HA)
import api as ha_api  # noqa: E402  (custom_components/camalert/api.py, no Home Assistant imports)


class _Resp(object):
    def __init__(self, status, data):
        self.status, self.data = status, data

    async def json(self, content_type=None):
        return self.data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class PlayerSession(object):
    """aiohttp-like session that hands every request to a player's API adapter."""

    def __init__(self, adapter, ctl, settings):
        self.adapter, self.ctl, self.settings, self.sent = adapter, ctl, settings, []

    def request(self, method, url, headers=None, json=None, **kw):
        u = urlsplit(url)
        self.sent.append((method, u.path, dict(headers or {}), json))
        body = None if json is None else _json.dumps(json).encode()
        req = Request(u.path, dict(parse_qsl(u.query)), "192.168.1.5", (headers or {}).get("X-CamAlert-Token"),
                      "HomeAssistant/2026.11 aiohttp/3.12", self.settings, method, body)
        if method == "POST" and body is None:
            req.body = b""
        ans = self.adapter.call(req, self.ctl)
        return _Resp(ans.code, ans.body)


def fake_aiohttp():
    if "aiohttp" not in sys.modules:
        import types
        mod = types.ModuleType("aiohttp")
        mod.ClientError = type("ClientError", (Exception,), {})
        mod.ClientTimeout = lambda total=None: total
        sys.modules["aiohttp"] = mod


class HaCallsCase(object):
    adapter_class = None

    @classmethod
    def setUpClass(cls):
        fake_aiohttp()
        cls.adapter = cls.adapter_class()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls.adapter, "close"):
            cls.adapter.close()

    def test_every_integration_call(self):
        self.adapter.reset()
        self.adapter.set_cameras(["front_door", "garden"])
        ctl = RecordingController()
        session = PlayerSession(self.adapter, ctl, {"token": "secret"})
        client = ha_api.CamAlertApi(session, "192.168.1.30", 8099, token="secret")

        async def run():
            status = await client.status()
            out = {"status": status, "cameras": await client.cameras()}
            for name, call in (("show", client.show(["garden", "front_door"], 20, priority="high", label="Person")),
                               ("dnd", client.dnd(True)), ("ptz", client.ptz("garden", "left")),
                               ("mosaic", client.mosaic(["garden"], 30)), ("hide", client.hide()),
                               ("webhook", client.webhook("http://192.168.1.20:8123/api/webhook/x")),
                               ("unhook", client.webhook("")), ("events", client.events()), ("log", client.log(5))):
                out[name] = await call
            return out
        try:
            out = asyncio.run(run())
        finally:
            self.adapter.set_cameras(None)
        self.assertEqual(out["status"]["platform"], self.adapter.platform)
        self.assertEqual(client.api_version, 1)
        self.assertEqual([c["name"] for c in out["cameras"]], ["front_door", "garden"])
        self.assertEqual(ctl.calls, [("show", "garden,front_door", 20, "strip", "high", "ha", "Person"), ("dnd", True),
                                     ("ptz", "left", "garden"), ("mosaic", "garden", 30), ("hide",)])
        self.assertEqual(out["webhook"], {"result": True, "webhook": True, "signed": False})
        posts = [p for m, p, _h, _b in session.sent if m == "POST"]
        self.assertEqual(posts, ["/camalert/show", "/camalert/dnd", "/camalert/ptz", "/camalert/mosaic",
                                 "/camalert/hide", "/camalert/webhook", "/camalert/webhook"])
        self.assertTrue(all(h == {"X-CamAlert-Token": "secret"} for _m, _p, h, _b in session.sent))
        self.assertTrue(all("token" not in p for _m, p, _h, _b in session.sent))


class TestHaCallsEnigma2(HaCallsCase, unittest.TestCase):
    adapter_class = Enigma2Adapter


class TestHaCallsKodi(HaCallsCase, unittest.TestCase):
    adapter_class = KodiAdapter


if __name__ == "__main__":
    unittest.main()
