#!/usr/bin/env python3
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Labels for a new GitHub bug report (#132), run by .github/workflows/issue-triage.yml.

Reads the issue form (.github/ISSUE_TEMPLATE/bug_report.yml) from the issue body, adds the label of the chosen
player, and when the CamAlert version or the problem report is missing it asks for it once, kindly, in one comment
with the marker below (edited, never repeated). Never closes, locks or removes anything.
Environment: GITHUB_TOKEN (issues: write), GITHUB_REPOSITORY, GITHUB_EVENT_PATH."""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MARK = "<!-- camalert-triage -->"
PLAYER_LABELS = {
    "Enigma2 receiver": "player: enigma2",
    "Kodi": "player: kodi",
    "Android TV / Fire TV app": "player: android tv",
    "Web player or browser extension": "player: web",
    "Home Assistant integration or blueprint": "player: home assistant",
    "TV with a notification app (PiPup, TvOverlay, Notifications for Android TV)": "player: notification app",
}
LABEL_COLOUR = "c5def5"
EMPTY = {"", "_no response_", "none", "n/a", "-", "?"}


def fields(body):
    """{heading: value} of an issue form body ("### Heading\\n\\nvalue")."""
    out = {}
    for part in re.split(r"^### ", body or "", flags=re.M)[1:]:
        head, _, value = part.partition("\n")
        out[head.strip()] = value.strip()
    return out


def missing(f):
    """What to ask for: the CamAlert version, the problem report."""
    want = []
    if f.get("CamAlert version", "").strip().lower() in EMPTY:
        want.append("version")
    logs = next((v for k, v in f.items() if k.startswith("Problem report")), "")
    if logs.strip().lower() in EMPTY:
        want.append("report")
    return want


def comment_text(want):
    lines = [MARK, "Thanks for the report! To look into it we need a little more:", ""]
    if "version" in want:
        lines.append("- **the CamAlert version** (shown in the settings, under About or Diagnostics);")
    if "report" in want:
        lines.append("- **the problem report**: open CamAlert on the player, choose *Report a problem*, save the "
                     "report and paste it here (passwords and tokens are already left out). In Home Assistant: "
                     "the *Problem report* button of the player.")
    lines += ["", "Just edit the issue or add a comment. Nothing is closed in the meantime."]
    return "\n".join(lines)


def decide(issue, comments):
    """{"labels": [...], "comment": text or None, "edit": comment id or None}. Never a close."""
    f = fields(issue.get("body"))
    labels = []
    label = PLAYER_LABELS.get(f.get("Player", "").strip())
    if label and label not in [lb.get("name") for lb in issue.get("labels") or []]:
        labels.append(label)
    mine = next((c for c in comments if MARK in (c.get("body") or "")), None)
    want = missing(f) if "Player" in f else []
    text = comment_text(want) if want else None
    if text is None:
        return {"labels": labels, "comment": None, "edit": None}
    if mine is None:
        return {"labels": labels, "comment": text, "edit": None}
    return {"labels": labels, "comment": text if mine.get("body") != text else None, "edit": mine["id"]}


class GitHub(object):
    def __init__(self, token, repo, base="https://api.github.com"):
        self.token, self.repo, self.base = token, repo, base

    def request(self, method, path, body=None):
        req = urllib.request.Request(self.base + "/repos/" + self.repo + path, method=method,
                                     data=json.dumps(body).encode("utf-8") if body is not None else None)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "camalert-issue-triage")
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def run(gh, issue):
    n = issue["number"]
    comments = gh.request("GET", "/issues/%d/comments?per_page=100" % n) or []
    d = decide(issue, comments)
    for label in d["labels"]:
        try:
            gh.request("GET", "/labels/" + urllib.parse.quote(label))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            gh.request("POST", "/labels", {"name": label, "color": LABEL_COLOUR})
    if d["labels"]:
        gh.request("POST", "/issues/%d/labels" % n, {"labels": d["labels"]})
    if d["comment"] and d["edit"]:
        gh.request("PATCH", "/issues/comments/%d" % d["edit"], {"body": d["comment"]})
    elif d["comment"]:
        gh.request("POST", "/issues/%d/comments" % n, {"body": d["comment"]})
    return d


def main():
    with open(os.environ["GITHUB_EVENT_PATH"]) as f:
        issue = json.load(f)["issue"]
    if "pull_request" in issue:
        return 0
    d = run(GitHub(os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]), issue)
    print("issue-triage: #%d labels %s, comment %s" % (issue["number"], d["labels"] or "-",
                                                      "yes" if d["comment"] else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
