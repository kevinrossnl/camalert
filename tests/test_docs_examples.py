"""Docs tests, examples part (#36): every HTTP API example in the docs and the Home Assistant package names an
existing route with known parameters and the right method, the MQTT topics in the docs are the ones of the MQTT
contract table, every Kodi fixture version is on the compatibility page, and the CI areas and tool subcommands named in the DEVELOPMENT.md files and docs exist."""
import glob
import inspect
import json
import os
import re
import unittest

import _paths

_paths.core()
from camalert_core import api  # noqa: E402
from contract import mqtt_table  # noqa: E402

ROOT = _paths.ROOT
# parameters every route takes (handled in api.handle, not in the route handlers)
COMMON = {"token", "test"}
# an API path: /camalert/<route> with an optional query string; not part of a GitHub URL (/<owner>/camalert/...)
API_PATH = re.compile(r"(?<![\w.-])/camalert/(\w+)(\?[^\s`'\")|<]*)?")
METHOD_ROW = re.compile(r"`(GET|POST) /camalert/(\w+)`(?:\s*`(\{[^`]*\})`)?")
QUERY_KEY = re.compile(r"[?&]([a-z_]+)=")
CURL_DATA = re.compile(r"\s-d\s+([a-z_]+)=")
TOPIC = re.compile(r"`(camalert/<id>/[\w/]+)`")


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def example_files():
    files = [os.path.join(ROOT, "README.md")] + glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True)
    files += glob.glob(os.path.join(ROOT, "homeassistant", "**", "*.yaml"), recursive=True)
    files += [os.path.join(ROOT, "homeassistant", "blueprints", "README.md")]
    return sorted(f for f in files if os.path.isfile(f))


def route_params():
    """{route: parameters its handler reads}, taken from the handler source in core/camalert_core/api.py."""
    out = {}
    for name, route in api.ROUTES.items():
        src = inspect.getsource(route.handler)
        keys = set(re.findall(r"a\.get\(\"(\w+)\"\)|a\[\"(\w+)\"\]|\"(\w+)\" in a\b|choice_param\(a, \"(\w+)\"", src))
        out[name] = {k for t in keys for k in t if k and not k.startswith("_")} | COMMON
    return out


class TestApiExamples(unittest.TestCase):
    params = route_params()

    def test_route_params_are_found(self):
        """The source scan sees the parameters of the handlers (guards the regex above)."""
        self.assertLessEqual({"cam", "sec", "mode", "priority", "label"}, self.params["show"])
        self.assertLessEqual({"cam", "move"}, self.params["ptz"])
        self.assertIn("on", self.params["dnd"])
        self.assertIn("interval", self.params["tour"])
        self.assertIn("url", self.params["webhook"])
        self.assertIn("lines", self.params["log"])

    def test_examples_name_routes_and_known_parameters(self):
        bad, seen = [], 0
        for path in example_files():
            for n, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
                where = "%s:%d" % (rel(path), n)
                for m in API_PATH.finditer(line):
                    seen += 1
                    route = m.group(1)
                    if route not in self.params:
                        bad.append("%s: unknown route /camalert/%s" % (where, route))
                        continue
                    keys = QUERY_KEY.findall(m.group(2) or "")
                    if "curl" in line:
                        keys += CURL_DATA.findall(line)
                    bad += ["%s: /camalert/%s has no parameter %r" % (where, route, k)
                            for k in keys if k not in self.params[route]]
        self.assertGreater(seen, 20)
        self.assertEqual(bad, [])

    def test_method_rows_use_the_right_method_and_json_keys(self):
        """`POST /camalert/x` only for actions (and dnd with on), `GET` only for reads; JSON bodies parse and use
        known parameters."""
        bad, seen = [], 0
        for path in example_files():
            for n, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
                for method, route, body in METHOD_ROW.findall(line):
                    seen += 1
                    where = "%s:%d" % (rel(path), n)
                    r = api.ROUTES.get(route)
                    if r is None:
                        bad.append("%s: unknown route %s" % (where, route))
                        continue
                    keys = set(json.loads(body)) if body else set()
                    action = r.action or (route == "dnd" and "on" in keys)
                    if method == "GET" and r.action:
                        bad.append("%s: GET for the action %s (deprecated, document POST)" % (where, route))
                    if method == "POST" and not action and route != "dnd":
                        bad.append("%s: POST for the read %s" % (where, route))
                    bad += ["%s: %s has no parameter %r" % (where, route, k) for k in keys - self.params[route]]
        self.assertGreater(seen, 10)
        self.assertEqual(bad, [])

    def test_home_assistant_package_payload_keys(self):
        text = open(os.path.join(ROOT, "homeassistant", "camalert_package.yaml"), encoding="utf-8").read()
        payload = text.split("payload:", 1)[1].split("headers:", 1)[0]
        keys = set(re.findall(r"\"(\w+)\":", payload))
        self.assertIn("cam", keys)
        self.assertEqual(keys - self.params["show"], set())


class TestMqttTopics(unittest.TestCase):
    def contract(self):
        pub = {t.replace("{node}", "<id>") for t, _r, _c in mqtt_table.PUBLISHED if t.startswith("camalert/")}
        sub = {t.replace("{node}", "<id>") for t in mqtt_table.SUBSCRIBED if t.startswith("camalert/")}
        return pub, sub

    def test_mqtt_page_lists_the_contract_topics(self):
        """docs/integrations/mqtt.md: every topic of the contract table, '(published)' exactly for the published ones."""
        pub, sub = self.contract()
        doc_pub, doc_sub = set(), set()
        for line in open(os.path.join(ROOT, "docs", "integrations", "mqtt.md"), encoding="utf-8"):
            m = re.match(r"\|\s*`(camalert/<id>/[\w/]+)`\s*\|(.*)", line)
            if m:
                (doc_pub if "(published)" in m.group(2) else doc_sub).add(m.group(1))
        self.assertEqual(doc_pub, pub)
        self.assertEqual(doc_sub, sub)

    def test_topics_in_the_docs_exist(self):
        pub, sub = self.contract()
        bad = []
        for path in example_files():
            for topic in TOPIC.findall(open(path, encoding="utf-8").read()):
                if topic not in pub | sub:
                    bad.append("%s: %s" % (rel(path), topic))
        self.assertEqual(bad, [])


class TestCompatibilityPage(unittest.TestCase):
    def test_every_kodi_fixture_version_is_listed(self):
        """docs/dev/compatibility.md names every Kodi version with an API fixture (the Enigma2 images: compat tests)."""
        text = open(_paths.COMPATIBILITY_DOC, encoding="utf-8").read()
        versions = sorted(os.path.splitext(f)[0] for f in os.listdir(_paths.KODI_API_FIXTURES) if f.endswith(".json"))
        self.assertTrue(versions)
        self.assertEqual([v for v in versions if not re.search(r"\b%s [A-Z][a-z]+" % v, text)], [])


class TestCommands(unittest.TestCase):
    """Commands in the DEVELOPMENT.md files, tests/README.md and docs/dev name CI areas and subcommands that exist."""

    def files(self):
        out = glob.glob(os.path.join(ROOT, "**", "DEVELOPMENT.md"), recursive=True)
        out += [os.path.join(ROOT, "tests", "README.md")] + glob.glob(os.path.join(ROOT, "docs", "dev", "*.md"))
        return [f for f in out if "/dist/" not in f and "/.venv" not in f]

    def test_ci_areas_exist(self):
        ci = open(os.path.join(ROOT, "tools", "ci.sh"), encoding="utf-8").read()
        areas = set(re.findall(r"^  ([a-z]+)\)", ci, re.M))
        self.assertLessEqual({"lint", "core", "unit", "build", "privacy", "ha", "androidtv"}, areas)
        bad = []
        for path in self.files():
            for named in re.findall(r"tools/ci\.sh ([a-z|]+)", open(path, encoding="utf-8").read()):
                bad += ["%s: ci.sh %s" % (rel(path), a) for a in named.split("|") if a and a not in areas]
        self.assertEqual(bad, [])

    def test_tool_subcommands_exist(self):
        """`python3 tools/docs.py update`, `tools/i18n/i18n.py update|build|check`: the tool knows the word."""
        bad = []
        for path in self.files():
            for tool, words in re.findall(r"tools/((?:i18n/)?(?:docs|i18n)\.py) ([a-z|]+)", open(path, encoding="utf-8").read()):
                src = open(os.path.join(ROOT, "tools", tool), encoding="utf-8").read()
                bad += ["%s: %s %s" % (rel(path), tool, w) for w in words.split("|")
                        if not re.search(r"[\"']%s[\"']" % w, src)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
