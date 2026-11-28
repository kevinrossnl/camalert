"""GitHub issues into Forgejo and the triage of new GitHub reports (#132), against in-memory fakes."""
import io
import os
import re
import unittest

import _paths

_paths.tools()
import issue_sync as sync  # noqa: E402
import issue_triage as triage  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

FORGEJO = "https://forgejo.example.invalid"


class FakeGitHub(object):
    """Read-only: any write is a test failure (the sync never writes to GitHub)."""
    fake = True

    def __init__(self, issues, comments=None):
        self.issues, self.comments, self.calls = issues, comments or {}, []

    def request(self, method, path, body=None, query=None):
        self.calls.append((method, path))
        assert method == "GET", "the sync wrote to GitHub: %s %s" % (method, path)
        m = re.match(r"/repos/[^/]+/[^/]+/issues/(\d+)/comments$", path)
        if m:
            return self.comments.get(int(m.group(1)), [])
        page, per = int(query["page"]), int(query["per_page"])
        return self.issues[(page - 1) * per:page * per]


class FakeForgejo(object):
    fake = True

    def __init__(self):
        self.issues, self.comments, self.labels, self.writes = [], {}, [], []

    def request(self, method, path, body=None, query=None):
        if method != "GET":
            self.writes.append((method, path, body))
        base = "/api/v1/repos/owner/camalert"
        assert path.startswith(base), path
        path = path[len(base):]
        if path == "/labels":
            if method == "GET":
                return list(self.labels)
            lb = dict(body, id=len(self.labels) + 1)
            self.labels.append(lb)
            return lb
        if path == "/issues" and method == "GET":
            want = query.get("labels")
            hits = [i for i in self.issues if not want or want in [lb["name"] for lb in i["labels"]]]
            page, lim = int(query["page"]), int(query["limit"])
            return hits[(page - 1) * lim:page * lim]
        if path == "/issues" and method == "POST":
            n = len(self.issues) + 1
            labels = [lb for lb in self.labels if lb["id"] in body.get("labels", [])]
            issue = {"number": n, "title": body["title"], "body": body["body"], "state": "open", "labels": labels,
                     "comments": 0}
            self.issues.append(issue)
            return issue
        m = re.match(r"/issues/(\d+)(/comments)?$", path)
        issue = self.issues[int(m.group(1)) - 1]
        if m.group(2):
            if method == "GET":
                return list(self.comments.get(issue["number"], []))
            self.comments.setdefault(issue["number"], []).append({"body": body["body"]})
            issue["comments"] += 1
            return {}
        issue.update(body)
        return issue


def gh_issue(n, title, state="open", body="text", comments=0, pr=False):
    i = {"number": n, "title": title, "state": state, "body": body, "comments": comments,
         "html_url": "https://github.com/kevinrossnl/camalert/issues/%d" % n,
         "user": {"login": "someone"}, "created_at": "2026-11-20T10:00:00Z"}
    if pr:
        i["pull_request"] = {}
    return i


def run(gh, fj, live=True):
    out = io.StringIO()
    env = {"ISSUE_SYNC": "on" if live else "", "FORGEJO_URL": FORGEJO, "FORGEJO_REPO": "owner/camalert"}
    assert sync.main(env=env, gh=gh, fj=fj, out=out) == 0
    return out.getvalue()


class TestSync(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGitHub([gh_issue(1, "Kodi shows nothing"), gh_issue(2, "A pull request", pr=True),
                              gh_issue(3, "Old bug", state="closed", comments=1)],
                             {3: [{"id": 77, "body": "Fixed for me", "user": {"login": "x"},
                                   "created_at": "2026-11-21T09:00:00Z"}]})
        self.fj = FakeForgejo()

    def test_copies_issues_but_not_pull_requests(self):
        run(self.gh, self.fj)
        self.assertEqual([i["title"] for i in self.fj.issues], ["[GitHub #1] Kodi shows nothing", "[GitHub #3] Old bug"])
        self.assertEqual([i["state"] for i in self.fj.issues], ["open", "closed"])
        for i in self.fj.issues:
            self.assertEqual([lb["name"] for lb in i["labels"]], ["github"])
            self.assertRegex(i["body"], r"<!-- github-issue: \d+ -->")
        self.assertIn("<!-- github-comment: 77 -->", self.fj.comments[2][0]["body"])

    def test_idempotent(self):
        run(self.gh, self.fj)
        writes = len(self.fj.writes)
        log = run(self.gh, self.fj)
        self.assertEqual(len(self.fj.writes), writes)
        self.assertIn("0 actions", log)
        self.assertEqual(len(self.fj.labels), 1)

    def test_follows_github(self):
        run(self.gh, self.fj)
        self.gh.issues[0].update(title="Kodi shows nothing at all", state="closed")
        self.gh.issues[2].update(comments=2)
        self.gh.comments[3].append({"id": 78, "body": "Me too", "user": {"login": "y"}, "created_at": ""})
        run(self.gh, self.fj)
        self.assertEqual(self.fj.issues[0]["title"], "[GitHub #1] Kodi shows nothing at all")
        self.assertEqual(self.fj.issues[0]["state"], "closed")
        self.assertEqual(len(self.fj.comments[2]), 2)
        self.assertEqual(len(self.fj.issues), 2)

    def test_dry_run_writes_nothing_and_logs_only_numbers_and_titles(self):
        self.gh.issues[0]["body"] = "secret body text"
        log = run(self.gh, self.fj, live=False)
        self.assertEqual(self.fj.writes, [])
        self.assertIn("dry run", log)
        self.assertIn("create  GitHub #1 Kodi shows nothing", log)
        self.assertNotIn("secret body text", log)

    def test_never_writes_to_github_and_no_forgejo_url_goes_out(self):
        run(self.gh, self.fj)
        self.assertTrue(all(m == "GET" for m, _ in self.gh.calls))
        for i in self.fj.issues:  # the copy points to GitHub, the GitHub side never learns the Forgejo address
            self.assertIn("https://github.com/kevinrossnl/camalert/issues/", i["body"])

    def test_live_needs_a_token(self):
        out = io.StringIO()

        class Real(object):
            def request(self, *a, **k):
                raise AssertionError("no request without a token")
        self.assertEqual(sync.main(env={"ISSUE_SYNC": "on", "FORGEJO_URL": FORGEJO, "FORGEJO_REPO": "owner/camalert"}, gh=Real(),
                                   fj=Real(), out=out), 2)

    def test_many_pages(self):
        self.gh.issues = [gh_issue(n, "Issue %d" % n) for n in range(1, 131)]
        run(self.gh, self.fj)
        self.assertEqual(len(self.fj.issues), 130)
        self.assertIn("0 actions", run(self.gh, self.fj))


FORM = """### Player

Kodi

### CamAlert version

%s

### Player type and version

Kodi 21

### Problem report, log excerpt and diagnostics (secrets removed)

%s
"""


class TestTriage(unittest.TestCase):
    def test_labels_the_player(self):
        d = triage.decide({"body": FORM % ("1.4.0", "CamAlert 1.4.0 on Kodi"), "labels": []}, [])
        self.assertEqual(d, {"labels": ["player: kodi"], "comment": None, "edit": None})

    def test_asks_once_for_what_is_missing(self):
        d = triage.decide({"body": FORM % ("_No response_", "_No response_"), "labels": []}, [])
        self.assertIn("CamAlert version", d["comment"])
        self.assertIn("Report a problem", d["comment"])
        again = triage.decide({"body": FORM % ("_No response_", "_No response_"),
                               "labels": [{"name": "player: kodi"}]}, [{"id": 5, "body": d["comment"]}])
        self.assertEqual(again, {"labels": [], "comment": None, "edit": 5})

    def test_edits_its_comment_when_less_is_missing(self):
        first = triage.decide({"body": FORM % ("_No response_", "_No response_"), "labels": []}, [])["comment"]
        d = triage.decide({"body": FORM % ("1.4.0", "_No response_"), "labels": []}, [{"id": 5, "body": first}])
        self.assertEqual(d["edit"], 5)
        self.assertNotIn("CamAlert version", d["comment"])

    def test_leaves_free_form_issues_alone(self):
        self.assertEqual(triage.decide({"body": "Just a question", "labels": []}, []),
                         {"labels": [], "comment": None, "edit": None})

    def test_run_never_closes_or_deletes(self):
        calls = []

        class Gh(object):
            def request(self, method, path, body=None):
                calls.append((method, path, body))
                return [] if method == "GET" and path.endswith("/comments?per_page=100") else {}
        triage.run(Gh(), {"number": 9, "body": FORM % ("_No response_", "_No response_"), "labels": []})
        self.assertNotIn("DELETE", [m for m, _, _ in calls])
        for _, path, body in calls:
            self.assertNotIn("state", body or {})
            self.assertNotIn("/lock", path)
        self.assertIn(("POST", "/issues/9/labels", {"labels": ["player: kodi"]}), calls)

    @unittest.skipIf(yaml is None, "PyYAML")
    def test_labels_cover_the_issue_form(self):
        with open(os.path.join(_paths.ROOT, ".github", "ISSUE_TEMPLATE", "bug_report.yml")) as f:
            form = yaml.safe_load(f)
        body = {b.get("id"): b for b in form["body"]}
        options = body["player"]["attributes"]["options"]
        self.assertEqual(set(triage.PLAYER_LABELS), set(options) - {"Other / not sure"})
        labels = {b["attributes"]["label"] for b in form["body"] if "attributes" in b and "label" in b["attributes"]}
        self.assertIn("CamAlert version", labels)
        self.assertTrue(any(x.startswith("Problem report") for x in labels))


@unittest.skipIf(yaml is None, "PyYAML")
class TestWorkflows(unittest.TestCase):
    def load(self, *p):
        with open(os.path.join(_paths.ROOT, *p)) as f:
            return yaml.safe_load(f)

    def test_sync_runs_on_the_home_runner_and_is_off_by_default(self):
        wf = self.load(".forgejo", "workflows", "issue-sync.yml")
        job = wf["jobs"]["sync"]
        self.assertEqual(job["runs-on"], "truenas")
        env = job["steps"][-1]["env"]
        self.assertEqual(env["ISSUE_SYNC"], "${{ vars.ISSUE_SYNC }}")
        self.assertEqual(env["FORGEJO_TOKEN"], "${{ secrets.CAMALERT_SYNC_TOKEN }}")
        self.assertEqual(env["GH_ISSUES_TOKEN"], "${{ secrets.GH_ISSUES_TOKEN }}")
        self.assertIn("schedule", wf[True] if True in wf else wf["on"])

    def test_triage_only_writes_issues(self):
        wf = self.load(".github", "workflows", "issue-triage.yml")
        self.assertEqual(wf["permissions"], {"issues": "write"})


if __name__ == "__main__":
    unittest.main()
