#!/usr/bin/env python3
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""GitHub issues into Forgejo (#132): users report on the public GitHub mirror, the work happens in Forgejo.

    python3 tools/issue_sync.py            dry run: prints what it would do (numbers and titles only)
    ISSUE_SYNC=on python3 tools/issue_sync.py   creates / updates the Forgejo copies

Runs as the scheduled Forgejo workflow `issue-sync` on the home runner (GitHub cannot reach Forgejo).
Environment: GITHUB_REPO (kevinrossnl/camalert), GH_ISSUES_TOKEN (read-only, optional: against the rate limit),
FORGEJO_URL + FORGEJO_REPO (owner/name, the workflow passes this repository) + FORGEJO_TOKEN (issues read/write; only needed with ISSUE_SYNC=on, the
dry run reads without it when the repository allows it).

Idempotent: every copy carries the marker `<!-- github-issue: N -->` in its body, every copied comment
`<!-- github-comment: ID -->`. A copy gets the label `github`; title, body and open/closed follow GitHub. Only GitHub
issues are read (never pull requests), and nothing is ever written to GitHub, so no Forgejo address leaks there.
Secrets are never printed."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
LABEL = "github"
ISSUE_MARK = re.compile(r"<!-- github-issue: (\d+) -->")
COMMENT_MARK = re.compile(r"<!-- github-comment: (\d+) -->")
LABEL_COLOUR = "#24292f"


class Http(object):
    """JSON over urllib; tests replace it with a fake."""

    def __init__(self, base, token=None, auth="token"):
        self.base, self.token, self.auth = base.rstrip("/"), token, auth

    def request(self, method, path, body=None, query=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("User-Agent", "camalert-issue-sync")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "%s %s" % (self.auth, self.token))
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def github_issues(gh, repo):
    """Every GitHub issue (no pull requests), oldest first, with its comments."""
    out, page = [], 1
    while True:
        batch = gh.request("GET", "/repos/%s/issues" % repo,
                           query={"state": "all", "per_page": 100, "page": page, "direction": "asc"}) or []
        out += [i for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            break
        page += 1
    for i in out:
        i["_comments"] = gh.request("GET", "/repos/%s/issues/%d/comments" % (repo, i["number"]),
                                    query={"per_page": 100}) if i.get("comments") else []
    return out


def forgejo_copies(fj, repo):
    """{github number: forgejo issue} of the existing copies (label `github`, any state)."""
    out, page = {}, 1
    while True:
        batch = fj.request("GET", "/api/v1/repos/%s/issues" % repo,
                           query={"state": "all", "labels": LABEL, "type": "issues", "limit": 50, "page": page}) or []
        for i in batch:
            m = ISSUE_MARK.search(i.get("body") or "")
            if m:
                out[int(m.group(1))] = i
        if len(batch) < 50:
            break
        page += 1
    return out


def copy_body(gi):
    """The Forgejo body of a copy: who and where, then the GitHub text, then the marker."""
    user = (gi.get("user") or {}).get("login", "?")
    return ("Copied from GitHub [#%d](%s) by **%s** (%s). Answer on GitHub; this copy follows it.\n\n---\n\n%s\n\n"
            "<!-- github-issue: %d -->" % (gi["number"], gi.get("html_url", ""), user, (gi.get("created_at") or "")[:10],
                                          (gi.get("body") or "").strip(), gi["number"]))


def comment_body(c):
    user = (c.get("user") or {}).get("login", "?")
    return "**%s** on GitHub (%s):\n\n%s\n\n<!-- github-comment: %d -->" % (
        user, (c.get("created_at") or "")[:16].replace("T", " "), (c.get("body") or "").strip(), c["id"])


def title_of(gi):
    return "[GitHub #%d] %s" % (gi["number"], gi.get("title") or "")


def plan(gh_issues, copies, existing_comments):
    """The actions to take: ("create", gi), ("update", gi, copy, fields), ("comment", gi, copy, c).
    existing_comments: {forgejo number: set of copied GitHub comment ids}."""
    actions = []
    for gi in gh_issues:
        copy = copies.get(gi["number"])
        state = "closed" if gi.get("state") == "closed" else "open"
        if copy is None:
            actions.append(("create", gi))
            for c in gi.get("_comments") or []:
                actions.append(("comment", gi, None, c))
            continue
        fields = {}
        if copy.get("title") != title_of(gi):
            fields["title"] = title_of(gi)
        if (copy.get("body") or "").strip() != copy_body(gi).strip():
            fields["body"] = copy_body(gi)
        if copy.get("state") != state:
            fields["state"] = state
        if fields:
            actions.append(("update", gi, copy, fields))
        done = existing_comments.get(copy["number"], set())
        for c in gi.get("_comments") or []:
            if c["id"] not in done:
                actions.append(("comment", gi, copy, c))
    return actions


def copied_comments(fj, repo, copies):
    out = {}
    for copy in copies.values():
        if not copy.get("comments"):
            out[copy["number"]] = set()
            continue
        cs = fj.request("GET", "/api/v1/repos/%s/issues/%d/comments" % (repo, copy["number"])) or []
        out[copy["number"]] = {int(m.group(1)) for m in (COMMENT_MARK.search(c.get("body") or "") for c in cs) if m}
    return out


def label_id(fj, repo):
    labels = fj.request("GET", "/api/v1/repos/%s/labels" % repo, query={"limit": 100}) or []
    for lb in labels:
        if lb.get("name") == LABEL:
            return lb["id"]
    return fj.request("POST", "/api/v1/repos/%s/labels" % repo,
                      body={"name": LABEL, "color": LABEL_COLOUR, "description": "Copied from the GitHub mirror"})["id"]


def apply(fj, repo, actions):
    """Carries out the plan; a comment on a copy created in the same run goes to that new copy."""
    lid = None
    created = {}
    for a in actions:
        kind, gi = a[0], a[1]
        if kind == "create":
            if lid is None:
                lid = label_id(fj, repo)
            new = fj.request("POST", "/api/v1/repos/%s/issues" % repo,
                             body={"title": title_of(gi), "body": copy_body(gi), "labels": [lid]})
            if gi.get("state") == "closed":
                fj.request("PATCH", "/api/v1/repos/%s/issues/%d" % (repo, new["number"]), body={"state": "closed"})
            created[gi["number"]] = new
        elif kind == "update":
            fj.request("PATCH", "/api/v1/repos/%s/issues/%d" % (repo, a[2]["number"]), body=a[3])
        elif kind == "comment":
            copy = a[2] or created.get(gi["number"])
            if copy is not None:
                fj.request("POST", "/api/v1/repos/%s/issues/%d/comments" % (repo, copy["number"]),
                           body={"body": comment_body(a[3])})


def describe(actions):
    """Lines for the log: numbers, titles and what changes, never bodies or tokens."""
    out = []
    for a in actions:
        gi = a[1]
        if a[0] == "create":
            out.append("create  GitHub #%d %s (%s)" % (gi["number"], gi.get("title", ""), gi.get("state")))
        elif a[0] == "update":
            out.append("update  GitHub #%d -> Forgejo #%d: %s" % (gi["number"], a[2]["number"], ", ".join(sorted(a[3]))))
        else:
            out.append("comment GitHub #%d: comment %d" % (gi["number"], a[3]["id"]))
    return out


def main(env=None, gh=None, fj=None, out=sys.stdout):
    env = os.environ if env is None else env
    live = env.get("ISSUE_SYNC", "").strip().lower() == "on"
    repo_gh = env.get("GITHUB_REPO", "kevinrossnl/camalert")
    repo_fj = env.get("FORGEJO_REPO", "")
    gh = gh or Http(GITHUB_API, env.get("GH_ISSUES_TOKEN") or None, auth="Bearer")
    fj = fj or Http(env.get("FORGEJO_URL", ""), env.get("FORGEJO_TOKEN") or None)
    if not repo_fj or not env.get("FORGEJO_URL") and not hasattr(fj, "fake"):
        print("issue-sync: FORGEJO_URL and FORGEJO_REPO are needed", file=out)
        return 2
    if live and not env.get("FORGEJO_TOKEN") and not hasattr(fj, "fake"):
        print("issue-sync: ISSUE_SYNC=on needs FORGEJO_TOKEN", file=out)
        return 2
    issues = github_issues(gh, repo_gh)
    copies = forgejo_copies(fj, repo_fj)
    actions = plan(issues, copies, copied_comments(fj, repo_fj, copies))
    print("issue-sync: %d GitHub issues, %d copies in Forgejo, %d actions (%s)"
          % (len(issues), len(copies), len(actions), "live" if live else "dry run"), file=out)
    for line in describe(actions):
        print("  " + line, file=out)
    if live:
        apply(fj, repo_fj, actions)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:  # the status only: never the request headers
        print("issue-sync: HTTP %d on %s" % (e.code, urllib.parse.urlsplit(e.url or "").path), file=sys.stderr)
        sys.exit(1)
