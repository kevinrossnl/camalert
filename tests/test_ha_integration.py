import json
import os
import re
import sys
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

    def test_sources_compile(self):
        for f in os.listdir(CC):
            if f.endswith(".py"):
                compile(open(os.path.join(CC, f), encoding="utf-8").read(), f, "exec")


if __name__ == "__main__":
    unittest.main()
