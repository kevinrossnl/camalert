import os
import subprocess
import tarfile
import tempfile
import unittest

import _paths  # noqa: E402

_paths.tools()
import build_ipk  # noqa: E402


class TestBuild(unittest.TestCase):
    def test_ipk_contents(self):
        with tempfile.TemporaryDirectory() as d:
            path = build_ipk.build(d, "someone")
            subprocess.check_call(["ar", "x", path], cwd=d)
            self.assertEqual(open(os.path.join(d, "debian-binary")).read(), "2.0\n")
            names = tarfile.open(os.path.join(d, "data.tar.gz")).getnames()
            base = "./usr/lib/enigma2/python/Plugins/Extensions/CamAlert/"
            for f in ("plugin.py", "__init__.py", "camalert_core/rules.py", "display.py", "server.py", "setup.py", "camalert.png",
                      "locale/nl/LC_MESSAGES/CamAlert.mo", "locale/de/LC_MESSAGES/CamAlert.mo"):
                self.assertIn(base + f, names)
            control = tarfile.open(os.path.join(d, "control.tar.gz")).extractfile("./control").read().decode()
            self.assertIn("Version: " + build_ipk.version(), control)
            self.assertIn("github.com/someone/", control)

    def test_feed(self):
        import gzip
        import build_feed
        with tempfile.TemporaryDirectory() as d:
            build_ipk.build(d, "someone")
            text = build_feed.build(d)
            self.assertIn("Package: enigma2-plugin-extensions-camalert", text)
            self.assertIn("Filename: enigma2-plugin-extensions-camalert_%s_all.ipk" % build_ipk.version(), text)
            self.assertRegex(text, r"SHA256sum: [0-9a-f]{64}")
            self.assertEqual(gzip.open(os.path.join(d, "Packages.gz")).read().decode(), text)

    def test_kodi_repo_has_every_asset(self):
        """#123: Kodi 19+ fetches the icon and fanart of each add-on in the repository from
        <datadir>/<addon id>/<path in <assets>>; every such file is in the repository tree."""
        import xml.etree.ElementTree as ET
        import build_kodi
        with tempfile.TemporaryDirectory() as d:
            _a, _r, tree = build_kodi.build(d, "https://someone.github.io/camalert/kodi")
            addons = ET.parse(os.path.join(tree, "addons.xml")).getroot()
            seen = 0
            for addon in addons.findall("addon"):
                for assets in addon.iter("assets"):
                    for item in assets:
                        path = os.path.join(tree, addon.get("id"), *(item.text or "").strip().split("/"))
                        self.assertTrue(os.path.isfile(path), "%s: %s" % (addon.get("id"), item.text))
                        seen += 1
            self.assertGreaterEqual(seen, 3)  # service: icon + fanart, repository: icon

    def test_pages_index(self):
        """GitHub Pages start page (#80): filled template, install lines that match the published files, small,
        no scripts/fonts/styles from other sites, links only to the repository and the site itself."""
        import re
        import shutil
        import build_feed
        import build_kodi
        template = os.path.join(_paths.ROOT, ".github", "pages", "index.html")
        with tempfile.TemporaryDirectory() as d:
            site = os.path.join(d, "feed")
            os.makedirs(site)
            build_ipk.build(site, "someone")
            build_kodi.build(os.path.join(d, "dist"), "https://someone.github.io/camalert/kodi")
            shutil.copytree(os.path.join(d, "dist", "kodi-repo"), os.path.join(site, "kodi"))
            build_feed.build(site)
            html = open(build_feed.write_index(site, template, "someone"), encoding="utf-8").read()
            with self.assertRaises(ValueError):
                build_feed.write_index(site, template, "")
            # the relative Kodi link points to a file that is published
            links = re.findall(r'href="([^"]+)"', html)
            local = [h for h in links if not h.startswith("https://")]
            self.assertEqual(local, ["kodi/repository.camalert/repository.camalert-%s.zip" % build_kodi.repo_version()])
            for h in local:
                self.assertTrue(os.path.isfile(os.path.join(site, h)), h)
        self.assertNotRegex(html, r"@[A-Z_]+@")
        self.assertLess(len(html.encode("utf-8")), 8000)
        self.assertIn('<html lang="en">', html)
        self.assertIn('name="viewport"', html)
        self.assertIn("<main>", html)
        self.assertIn("<title>", html)
        self.assertIn("src/gz camalert https://someone.github.io/camalert</code>", html)
        self.assertIn("https://someone.github.io/camalert/camalert-feed.conf", html)
        self.assertIn("<code>https://github.com/someone/camalert</code>", html)  # HACS custom repository
        self.assertIn("This site has version <strong>%s</strong>" % build_ipk.version(), html)
        for bad in ("<script", "<link", "<img", "<iframe", "@import", "url(", "src="):
            self.assertNotIn(bad, html.lower(), bad)
        for h in links:
            if h.startswith("https://"):
                self.assertTrue(h.startswith(("https://github.com/someone/camalert", "https://someone.github.io/camalert")), h)
            m = re.match(r"https://github.com/someone/camalert/blob/v[^/]+/([^#]+)", h)
            if m:  # documentation links: the files exist
                self.assertTrue(os.path.isfile(os.path.join(_paths.ROOT, m.group(1))), h)

    def test_sources_compile(self):
        src = _paths.ENIGMA2
        for f in os.listdir(src):
            if f.endswith(".py"):
                compile(open(os.path.join(src, f), encoding="utf-8").read(), f, "exec")


if __name__ == "__main__":
    unittest.main()
