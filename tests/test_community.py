"""Community and publication files for GitHub (#23): contributing guide, security policy, code of conduct, issue
forms and pull request template exist, parse, and ask for what a bug report needs (player, versions, redacted logs)."""
import glob
import os
import unittest

import yaml

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


if __name__ == "__main__":
    unittest.main()
