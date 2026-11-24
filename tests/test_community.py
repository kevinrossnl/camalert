"""Community and publication files for GitHub (#23): contributing guide, security policy, code of conduct, issue
forms and pull request template exist, parse, and ask for what a bug report needs (player, versions, redacted logs)."""
import glob
import os
import unittest

import yaml

try:
    import PIL  # noqa: F401  (optional: the Forgejo CI has no Pillow)
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

import _paths

ROOT = _paths.ROOT
GH = "https://github.com/kevinrossnl/camalert"


def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


class CommunityFiles(unittest.TestCase):
    def test_files_exist(self):
        for rel in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "LICENSE", ".github/PULL_REQUEST_TEMPLATE.md",
                    ".github/ISSUE_TEMPLATE/config.yml", ".github/ISSUE_TEMPLATE/bug_report.yml",
                    ".github/ISSUE_TEMPLATE/feature_request.yml", ".github/ISSUE_TEMPLATE/question.yml"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rel)), rel)

    def test_security_policy_uses_private_vulnerability_reporting(self):
        text = read("SECURITY.md")
        self.assertIn("Report a vulnerability", text)
        self.assertIn(GH + "/security", text)
        self.assertNotIn("@", text.replace("@kevinrossnl", ""))  # no e-mail address in the policy

    def test_code_of_conduct_is_contributor_covenant_2_1(self):
        text = read("CODE_OF_CONDUCT.md")
        self.assertIn("Contributor Covenant, version 2.1", text)
        self.assertIn("contributor-covenant.org/version/2/1/code_of_conduct", text)

    def test_issue_forms(self):
        forms = {}
        for path in glob.glob(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "*.yml")):
            data = yaml.safe_load(open(path, encoding="utf-8"))
            forms[os.path.basename(path)] = data
        self.assertFalse(forms["config.yml"]["blank_issues_enabled"])
        self.assertTrue(any("/security/" in c["url"] for c in forms["config.yml"]["contact_links"]))
        for name in ("bug_report.yml", "feature_request.yml", "question.yml"):
            form = forms[name]
            self.assertTrue(form["name"] and form["description"] and form["body"], name)
            ids = [b.get("id") for b in form["body"] if b["type"] != "markdown"]
            self.assertEqual(len(ids), len(set(ids)), name)
            self.assertTrue(all(ids), name)
        bug = {b.get("id"): b for b in forms["bug_report.yml"]["body"]}
        for field in ("player", "camalert_version", "player_version", "ha_version", "logs", "checks"):
            self.assertIn(field, bug)
        self.assertIn("Kodi", bug["player"]["attributes"]["options"])
        self.assertIn("Enigma2 receiver", bug["player"]["attributes"]["options"])
        self.assertTrue(bug["checks"]["attributes"]["options"][0]["required"])  # secrets removed
        self.assertIn("secrets removed", bug["logs"]["attributes"]["label"])

    def test_links_point_to_the_public_repository(self):
        for rel in ("CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", ".github/PULL_REQUEST_TEMPLATE.md",
                    *[os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", "*"))]):
            text = read(rel)
            self.assertNotIn("forgejo", text.lower(), rel)
            for part in text.split("github.com/")[1:]:
                self.assertTrue(part.startswith(("kevinrossnl/camalert", "AlexxIT/")), (rel, part[:40]))


class ReleaseWorkflow(unittest.TestCase):
    """#22/#23: the GitHub workflow builds and attaches every package, checks tag = version and dated CHANGELOG,
    and publishes Pages only after hassfest and the HACS check."""

    def setUp(self):
        self.text = read(".github/workflows/release.yml")
        self.wf = yaml.safe_load(self.text)

    def test_jobs(self):
        jobs = self.wf["jobs"]
        self.assertEqual(sorted(jobs), ["build", "hacs", "hassfest", "pages"])
        self.assertEqual(sorted(jobs["pages"]["needs"]), ["build", "hacs", "hassfest"])
        self.assertEqual(jobs["pages"]["permissions"], {"pages": "write", "id-token": "write"})
        self.assertEqual(self.wf["permissions"], {"contents": "read"})

    def test_release_assets(self):
        steps = self.wf["jobs"]["build"]["steps"]
        release = next(s for s in steps if s.get("uses", "").startswith("softprops/action-gh-release"))
        files = release["with"]["files"].split()
        self.assertEqual(files, ["dist/*.ipk", "dist/service.camalert-*.zip", "dist/repository.camalert-*.zip",
                                 "dist/camalert-homeassistant-*.zip"])
        self.assertEqual(release["with"]["body_path"], "dist/release-notes.md")
        self.assertNotIn(".apk", self.text)  # Android TV: no release APK before release signing (#65)

    def test_tag_must_match_version_and_dated_changelog(self):
        self.assertIn('test "${GITHUB_REF_NAME}" = "v$ver"', self.text)
        self.assertIn("CHANGELOG.md has no dated section", self.text)

    def test_private_repository_skips_hacs_and_pages(self):
        """The HACS action only validates public repositories and GitHub Free has no Pages for private ones:
        both are skipped (not failed) while the repository is private; the release itself still runs."""
        jobs = self.wf["jobs"]
        self.assertIn("!github.event.repository.private", jobs["hacs"]["if"])
        self.assertIn("!github.event.repository.private", jobs["pages"]["if"])
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", jobs["pages"]["if"])
        steps = jobs["build"]["steps"]
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-pages-artifact"))
        self.assertIn("!github.event.repository.private", upload["if"])
        release = next(s for s in steps if s.get("uses", "").startswith("softprops/action-gh-release"))
        self.assertNotIn("private", release["if"])
        self.assertNotIn("if", jobs["hassfest"])
        self.assertNotIn("if", jobs["build"])

    def test_actions_on_node24_majors(self):
        """Node.js 20 actions are deprecated on GitHub: at least these majors (all node24)."""
        import re
        minimum = {"actions/checkout": 7, "actions/setup-python": 7, "actions/upload-artifact": 7,
                   "actions/download-artifact": 8, "actions/upload-pages-artifact": 5, "actions/deploy-pages": 5,
                   "softprops/action-gh-release": 3}
        used = re.findall(r"uses: ([\w.-]+/[\w.-]+)@v(\d+)", self.text)
        self.assertTrue(used)
        for name, major in used:
            self.assertIn(name, minimum, name)
            self.assertGreaterEqual(int(major), minimum[name], name)

    def test_runs_the_ci_areas(self):
        for area in ("lint", "core", "unit"):
            self.assertIn("sh tools/ci.sh %s" % area, self.text)


class Changelog(unittest.TestCase):
    def test_keep_a_changelog_layout(self):
        import re
        text = read("CHANGELOG.md")
        heads = re.findall(r"^## (.*)$", text, re.M)
        self.assertEqual(heads[0], "[Unreleased]")
        for h in heads[1:]:
            self.assertRegex(h, r"^\[\d+\.\d+\.\d+\] - (\d{4}-\d{2}-\d{2}|YYYY-MM-DD)$")
        version = json_version()
        self.assertIn("## [%s] - " % version, text)
        self.assertIn("[%s]: %s/releases/tag/v%s" % (version, GH, version), text)
        self.assertIn("[Unreleased]: %s/compare/v%s...HEAD" % (GH, version), text)


def json_version():
    import json
    return json.load(open(os.path.join(ROOT, "custom_components", "camalert", "manifest.json")))["version"]


class BrandImages(unittest.TestCase):
    """HACS accepts custom_components/<domain>/brand/icon.png instead of home-assistant/brands (#23)."""

    def path(self, name):
        return os.path.join(ROOT, "custom_components", "camalert", "brand", name)

    def test_icons_are_square_rgba_png(self):
        import struct
        for name, size in (("icon.png", 256), ("icon@2x.png", 512)):
            data = open(self.path(name), "rb").read()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", name)
            w, h, depth, colour = struct.unpack(">IIBB", data[16:26])
            self.assertEqual((w, h, depth, colour), (size, size, 8, 6), name)  # 8-bit RGBA

    @unittest.skipUnless(HAVE_PIL, "Pillow not installed")
    def test_transparent_background_and_generator(self):
        import tempfile
        from PIL import Image, ImageChops
        _paths.tools()
        import make_brand
        with tempfile.TemporaryDirectory() as tmp:
            for path in make_brand.build(tmp):
                name = os.path.basename(path)
                theirs = Image.open(self.path(name)).convert("RGBA")
                size = theirs.size[0]
                self.assertEqual(theirs.getpixel((0, 0))[3], 0, name)                    # transparent corner
                self.assertEqual(theirs.getpixel((size // 4, size // 2))[3], 255, name)  # the TV is opaque
                diff = ImageChops.difference(Image.open(path).convert("RGBA"), theirs)
                # same drawing; small differences from another Pillow version's resampling are fine
                self.assertLessEqual(max(hi for lo, hi in diff.getextrema()), 16, name)

if __name__ == "__main__":
    unittest.main()
