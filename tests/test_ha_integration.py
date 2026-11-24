import asyncio
import json
import os
import re
import sys
import types
import unittest

import _paths  # noqa: E402

ROOT = _paths.ROOT
CC = _paths.HA
_paths.add(CC)
import api  # noqa: E402  (no Home Assistant imports at module level)


def keys(d, prefix=""):
    out = set()
    for k, v in d.items():
        out.add(prefix + k)
        if isinstance(v, dict):
            out |= keys(v, prefix + k + ".")
    return out


class TestIntegration(unittest.TestCase):
    def test_manifest_and_versions(self):
        m = json.load(open(os.path.join(CC, "manifest.json")))
        self.assertEqual(m["domain"], "camalert")
        self.assertTrue(m["config_flow"])
        plugin = re.search(r'__version__ = "([^"]+)"', open(os.path.join(_paths.ENIGMA2, "__init__.py")).read()).group(1)
        self.assertEqual(m["version"], plugin, "plugin and integration share one version")
        json.load(open(os.path.join(ROOT, "hacs.json")))

    def test_translations_complete(self):
        base = json.load(open(os.path.join(CC, "strings.json"), encoding="utf-8"))
        for f in os.listdir(os.path.join(CC, "translations")):
            t = json.load(open(os.path.join(CC, "translations", f), encoding="utf-8"))
            self.assertEqual(keys(t), keys(base), f)
            self.assertIn("{camera}", t["entity"]["button"]["show"]["name"], f)

    def test_services_match_strings(self):
        text = open(os.path.join(CC, "services.yaml")).read()
        services = re.findall(r"^([a-z_]+):\s*$", text, re.M)
        fields = set()
        for block in re.split(r"^\s*fields:\s*$", text, flags=re.M)[1:]:
            fields |= set(re.findall(r"^    ([a-z_]+):\s*$", re.split(r"^[a-z_]+:\s*$", block, flags=re.M)[0], re.M))
        base = json.load(open(os.path.join(CC, "strings.json")))["services"]
        self.assertEqual(sorted(services), sorted(base))
        documented = {f for s in base.values() for f in s.get("fields", {})}
        self.assertEqual(fields, documented)

    def test_build_url(self):
        self.assertEqual(api.build_url("192.168.1.30", 8099, False, "show", {"cam": "front door", "sec": 20, "mode": None}),
                         "http://192.168.1.30:8099/camalert/show?cam=front+door&sec=20")
        self.assertEqual(api.build_url("fd00::5", 8099, True, "status"), "https://[fd00::5]:8099/camalert/status")

    def test_show_params(self):
        self.assertEqual(api.show_params(["a", "b"]), ("a,b", "strip"))
        self.assertEqual(api.show_params("a, b,c"), ("a,b,c", "strip"))
        self.assertEqual(api.show_params(["a", "b"], "live"), ("a,b", "live"))
        self.assertEqual(api.show_params(["a"]), ("a", None))
        self.assertEqual(api.show_params(list("abcde")), ("a,b,c,d,e", None))
        self.assertEqual(api.show_params(None), (None, None))

    def test_plan_request(self):
        caps = ["post", "header_token"]
        self.assertEqual(api.plan_request("show", {"cam": "a", "sec": None}, caps), ("POST", {}, {"cam": "a"}))
        self.assertEqual(api.plan_request("status", None, caps), ("GET", {}, None))
        self.assertEqual(api.plan_request("dnd", {}, caps), ("GET", {}, None))
        self.assertEqual(api.plan_request("dnd", {"on": "1"}, caps), ("POST", {}, {"on": "1"}))
        self.assertEqual(api.plan_request("show", {"cam": "a"}, None), ("GET", {"cam": "a"}, None))  # older player

    def test_versions(self):
        self.assertGreater(api.version_tuple("1.10.0"), api.version_tuple("1.9"))
        client = api.CamAlertApi(None, "h", 1)
        self.assertFalse(client.integration_too_old())
        client.min_ha_version = "9.0.0"
        self.assertTrue(client.integration_too_old())
        self.assertEqual(api.INTEGRATION_VERSION, json.load(open(os.path.join(CC, "manifest.json")))["version"])

    def test_sources_compile(self):
        for f in os.listdir(CC):
            if f.endswith(".py"):
                compile(open(os.path.join(CC, f), encoding="utf-8").read(), f, "exec")


class FakeResponse(object):
    def __init__(self, status, data):
        self.status, self.data = status, data

    async def json(self, content_type=None):
        return self.data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession(object):
    """Records requests; answers from a list of (status, json)."""

    def __init__(self, answers):
        self.answers, self.sent = list(answers), []

    def request(self, method, url, **kw):
        self.sent.append((method, url, kw.get("headers"), kw.get("json")))
        return FakeResponse(*self.answers.pop(0))


def fake_aiohttp():
    if "aiohttp" not in sys.modules:
        mod = types.ModuleType("aiohttp")
        mod.ClientError = type("ClientError", (Exception,), {})
        mod.ClientTimeout = lambda total=None: total
        sys.modules["aiohttp"] = mod


STATUS_V1 = {"result": True, "api_version": 1, "platform": "kodi", "min_ha_version": "1.0.0",
             "capabilities": ["post", "header_token", "show", "ptz", "mosaic", "webhook"]}


class TestApiClient(unittest.TestCase):
    def setUp(self):
        fake_aiohttp()

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_actions_are_posted_with_the_token_in_a_header(self):
        s = FakeSession([(200, STATUS_V1), (200, {"result": True, "action": "show"})])
        client = api.CamAlertApi(s, "192.168.1.30", 8099, token="secret")
        self.run_async(client.status())
        self.assertEqual((client.api_version, client.platform), (1, "kodi"))
        self.assertTrue(client.supports("ptz"))
        self.assertFalse(client.supports("tour"))
        self.run_async(client.show(["garden", "front_door"], 20, priority="high"))
        method, url, headers, body = s.sent[1]
        self.assertEqual((method, url), ("POST", "http://192.168.1.30:8099/camalert/show"))
        self.assertEqual(headers, {"X-CamAlert-Token": "secret"})
        self.assertEqual(body, {"cam": "garden,front_door", "sec": 20, "mode": "strip", "priority": "high"})
        self.assertNotIn("secret", url)

    def test_older_player_gets_get_requests(self):
        s = FakeSession([(200, {"result": True, "version": "0.9"}), (200, {"result": True})])
        client = api.CamAlertApi(s, "192.168.1.30", 8099, token="secret")
        self.run_async(client.status())
        self.assertIsNone(client.capabilities)
        self.assertTrue(client.supports("ptz"))
        self.run_async(client.dnd(True))
        self.assertEqual(s.sent[1][:2], ("GET", "http://192.168.1.30:8099/camalert/dnd?on=1"))

    def test_errors_are_raised(self):
        for status, data, text in ((400, {"error": "invalid camera name"}, "invalid camera name"),
                                   (403, {"error": "forbidden"}, "forbidden"), (429, {}, "too many"),
                                   (405, {"error": "method not allowed"}, "not supported"), (200, ["x"], "unexpected")):
            client = api.CamAlertApi(FakeSession([(status, data)]), "h", 1)
            with self.assertRaises(api.CamAlertError) as ctx:
                self.run_async(client.hide())
            self.assertIn(text, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
