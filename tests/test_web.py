"""Web player and browser extension (#92, #127): generated files up to date, the extension package, and the rules of
the shared JS core (no dependencies, relative imports only, a subset of the players' API)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

import _paths

ROOT = _paths.ROOT
WEB = os.path.join(ROOT, "players", "web")
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "core"))
import build_web  # noqa: E402
from camalert_core import api  # noqa: E402


class TestWeb(unittest.TestCase):
    def test_generated_and_www_up_to_date(self):
        self.assertEqual(build_web.stale(), [], "run python3 tools/build_web.py update")

    def test_capabilities_are_a_subset_of_the_players(self):
        self.assertTrue(set(build_web.CAPABILITIES) <= set(api.CAPABILITIES))
        for c in ("post", "header_token", "webhook", "update", "ptz", "tour"):
            self.assertNotIn(c, build_web.CAPABILITIES, "a browser player has no %s" % c)

    def test_js_core_has_no_dependencies(self):
        """The core runs as plain ES modules in a page, the dashboard and the extension: relative imports only."""
        for folder in ("core", "page", "extension"):
            for name in os.listdir(os.path.join(WEB, folder)):
                if not name.endswith(".js"):
                    continue
                text = open(os.path.join(WEB, folder, name), encoding="utf-8").read()
                for spec in re.findall(r'^\s*import\s[^;]*?from\s+"([^"]+)"', text, re.M):
                    self.assertTrue(spec.startswith(("./", "../")), "%s/%s imports %s" % (folder, name, spec))
                self.assertNotIn("require(", text, name)
                self.assertNotIn("eval(", text, name)

    def test_extension_package(self):
        with tempfile.TemporaryDirectory() as d:
            path = build_web.dist(d)
            self.assertTrue(path.endswith("camalert-browser-%s.zip" % build_web.version()))
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                m = json.loads(z.read("manifest.json"))
        self.assertEqual(m["manifest_version"], 3)
        self.assertEqual(m["version"], build_web.version())
        self.assertEqual(m["background"], {"service_worker": "background.js", "type": "module"})
        self.assertEqual(set(m["permissions"]), {"storage", "alarms", "offscreen"})
        self.assertNotIn("host_permissions", m, "only optional host permissions, asked for the HA address")
        for f in ("background.js", "alert.html", "alert.js", "options.html", "options.js", "offscreen.html",
                  "offscreen.js", "popup.html", "popup.js", "icon.png", "chime.wav", "core/api.js", "core/ui.js",
                  "core/generated.js", "core/i18n.js", "core/transport.js", "core/player.js", "core/store.js",
                  "core/servers.js", "core/mqtt.js", "ext.js"):
            self.assertIn(f, names)
        self.assertNotIn("background.html", names)
        # the Chrome Web Store and Firefox want the declared sizes (#131)
        files = build_web.extension_files()
        for size, name in m["icons"].items():
            png = files[name]
            self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n", name)
            self.assertEqual((int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")),
                             (int(size), int(size)), name)

    def test_firefox_package(self):
        """#131: the same files as a Firefox add-on: Manifest V2 with a persistent background page (an MV3 event page
        would drop the WebSocket), no offscreen document, a fixed add-on id."""
        with tempfile.TemporaryDirectory() as d:
            build_web.dist(d)
            path = os.path.join(d, "camalert-browser-firefox-%s.zip" % build_web.version())
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                m = json.loads(z.read("manifest.json"))
                page = z.read("background.html").decode("utf-8")
        self.assertEqual(m["manifest_version"], 2)
        self.assertEqual(m["version"], build_web.version())
        self.assertEqual(m["background"], {"page": "background.html", "persistent": True})
        self.assertIn('<script type="module" src="background.js">', page)
        self.assertEqual(set(m["permissions"]), {"storage", "alarms"})
        self.assertEqual(m["optional_permissions"], ["http://*/*", "https://*/*"])
        gecko = m["browser_specific_settings"]["gecko"]
        self.assertEqual(gecko["id"], "camalert@camalert.invalid")
        self.assertEqual(gecko["data_collection_permissions"], {"required": ["none"]})
        self.assertNotIn("offscreen.html", names)
        self.assertNotIn("offscreen.js", names)
        for f in ("background.js", "ext.js", "alert.js", "options.html", "popup.html", "chime.wav", "core/mqtt.js",
                  "core/servers.js"):
            self.assertIn(f, names)
        self.assertNotIn("background.html", build_web.extension_files("chrome"))
        with self.assertRaises(ValueError):
            build_web.extension_files("safari")

    def test_extension_locales(self):
        """#131: name and short description per store language (_locales, en is the default); the Chrome Web Store
        allows 132 characters for the description."""
        m = json.load(open(os.path.join(WEB, "extension", "manifest.json")))
        self.assertEqual((m["name"], m["description"], m["default_locale"]), ("__MSG_name__", "__MSG_description__", "en"))
        folder = os.path.join(WEB, "extension", "_locales")
        self.assertEqual(sorted(os.listdir(folder)), ["de", "en", "fr", "it", "nl", "pl"])
        for lang in os.listdir(folder):
            msgs = json.load(open(os.path.join(folder, lang, "messages.json"), encoding="utf-8"))
            self.assertEqual(sorted(msgs), ["description", "name"], lang)
            self.assertEqual(msgs["name"]["message"], "CamAlert")
            self.assertLessEqual(len(msgs["description"]["message"]), 132, lang)
        self.assertEqual(json.loads(build_web.extension_files("firefox")["manifest.json"])["default_locale"], "en")

    def test_extension_uses_the_browser_api_through_ext_js(self):
        """#131: Firefox's `browser` or Chrome's `chrome`, chosen in ext.js; only the Chrome-only offscreen page
        uses `chrome` directly."""
        folder = os.path.join(WEB, "extension")
        for name in os.listdir(folder):
            if name.endswith(".js") and name not in ("ext.js", "offscreen.js"):
                text = open(os.path.join(folder, name), encoding="utf-8").read()
                self.assertNotRegex(text, r"\bchrome\.", name)
                self.assertIn('from "./ext.js"', text, name)

    def test_unpacked_extension(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_web.py"), "unpacked", d], check=True,
                           stdout=subprocess.DEVNULL)
            self.assertTrue(os.path.isfile(os.path.join(d, "core", "controller.js")))
            self.assertEqual(json.load(open(os.path.join(d, "manifest.json")))["manifest_version"], 3)

    def test_main_check_and_usage(self):
        self.assertEqual(build_web.main(["x", "check"]), 0)
        self.assertEqual(build_web.main(["x", "nonsense"]), 2)

    def test_tests_and_lock_file(self):
        """CI runs the Node unit tests everywhere and Playwright from the lock file (tools/ci.sh web)."""
        pkg = json.load(open(os.path.join(WEB, "package.json")))
        self.assertEqual(list(pkg["devDependencies"]), ["@playwright/test"])
        lock = json.load(open(os.path.join(WEB, "package-lock.json")))
        self.assertIn("node_modules/@playwright/test", lock["packages"])
        self.assertTrue(os.listdir(os.path.join(WEB, "tests", "unit")))
        self.assertTrue(os.listdir(os.path.join(WEB, "tests", "e2e")))

    def test_ha_serves_the_player_and_lists_its_dependencies(self):
        m = json.load(open(os.path.join(ROOT, "custom_components", "camalert", "manifest.json")))
        self.assertTrue({"http", "websocket_api"} <= set(m["dependencies"]))
        self.assertIn("frontend", m["after_dependencies"])
        www = os.path.join(ROOT, "custom_components", "camalert", "www")
        self.assertTrue(os.path.isfile(os.path.join(www, "page", "player.html")))
        self.assertTrue(os.path.isfile(os.path.join(www, "page", "frontend.js")))


if __name__ == "__main__":
    unittest.main()
