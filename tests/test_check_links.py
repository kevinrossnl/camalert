"""The nightly external link check (#79): what is collected, how answers count, the one Forgejo issue."""
import json
import os
import tempfile
import unittest

import _paths

_paths.tools()
import check_links as cl  # noqa: E402


class FakeForge(object):
    def __init__(self, issues=()):
        self.issues, self.calls = list(issues), []

    def find(self):
        return self.issues[0] if self.issues else None

    def call(self, method, path, body=None):
        self.calls.append((method, path, body))
        return {}


class TestCheckLinks(unittest.TestCase):
    def test_collects_only_public_links(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write("See [go2rtc](https://github.com/AlexxIT/go2rtc), <https://www.videolan.org/>.\n"
                        "```\nwget -O x https://github.com/kevinrossnl/camalert/releases/download/v1.3.1/x.ipk\n```\n"
                        "Not: http://192.168.1.20:8099/camalert/status, http://<player>:8099, http://homeassistant.local,"
                        " https://example.com/x, http://admin:pw@192.168.1.5/, http://[fd00::10]:8099, "
                        "https://github.com/kevinrossnl/camalert/releases/download/vX.Y.Z/x\n")
            found = cl.collect([p])
        self.assertEqual(sorted(found), ["https://github.com/AlexxIT/go2rtc",
                                         "https://github.com/kevinrossnl/camalert/releases/download/v1.3.1/x.ipk",
                                         "https://www.videolan.org/"])

    def test_answers(self):
        def opener(codes):
            return lambda url, method: codes[method]
        self.assertEqual(cl.check("u", opener({"HEAD": 200})), (cl.OK, "200"))
        self.assertEqual(cl.check("u", opener({"HEAD": 301})), (cl.OK, "301"))
        self.assertEqual(cl.check("u", opener({"HEAD": 405, "GET": 200})), (cl.OK, "200"))  # HEAD refused
        self.assertEqual(cl.check("u", opener({"HEAD": 404})), (cl.BROKEN, "404"))
        self.assertEqual(cl.check("u", opener({"HEAD": 429})), (cl.WARNING, "429"))
        self.assertEqual(cl.check("u", opener({"HEAD": 503})), (cl.BROKEN, "503"))

        def down(url, method):
            raise OSError("timed out")
        self.assertEqual(cl.check("u", down)[0], cl.WARNING)

    def test_report_and_issue(self):
        found = {"https://a.example.org/x": ["docs/a.md:3"], "https://b.example.org/": ["README.md:1"]}
        results = {"https://a.example.org/x": (cl.BROKEN, "404"), "https://b.example.org/": (cl.OK, "200")}
        broken, text = cl.report(found, results)
        self.assertEqual(broken, ["https://a.example.org/x"])
        self.assertIn("docs/a.md:3", text)
        f = FakeForge()
        self.assertEqual(cl.to_issue(f, broken, text), "created")
        self.assertEqual(f.calls[0][:2], ("POST", "/issues"))
        self.assertEqual(f.calls[0][2]["title"], cl.TITLE)
        f = FakeForge([{"number": 7, "state": "open"}])
        self.assertEqual(cl.to_issue(f, broken, text), "updated")
        self.assertEqual(cl.to_issue(f, [], "all fine"), "closed")
        self.assertIn(("PATCH", "/issues/7", {"state": "closed"}), f.calls)
        self.assertEqual(cl.to_issue(FakeForge([{"number": 7, "state": "closed"}]), [], "fine"), "nothing")

    def test_main_with_issue_never_fails(self):
        orig = cl.run
        cl.run = lambda found, opener=None, workers=8: {u: (cl.BROKEN, "404") for u in found}
        try:
            env = {k: os.environ.pop(k, None) for k in ("REPO_TOKEN",)}
            self.assertEqual(cl.main(["--issue"]), 0)
            self.assertEqual(cl.main([]), 1)
        finally:
            cl.run = orig
            for k, v in env.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
