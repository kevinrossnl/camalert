#!/usr/bin/env python3
"""Nightly check of the external links in the docs (#79). Never part of a push or the gate.

    python3 tools/check_links.py                # report, exit 1 when a link is broken
    python3 tools/check_links.py --issue        # also open / update / close one Forgejo issue, always exit 0

Collects every http(s) URL in README.md, docs/**/*.md, CHANGELOG.md and the blueprints (also inside code blocks:
download links are worth checking), skips placeholders (<player>, {...}), private and example addresses
(192.168.x, homeassistant.local, example.com, localhost) and GitHub's own permalinks that need a login. Each URL is
asked with HEAD, then GET when HEAD is refused (403/405/501); 2xx and 3xx are fine, 429 and timeouts are only
warnings (retried the next night), 404/410/5xx are broken. With --issue the result goes into one issue titled
TITLE: created when something is broken, updated while it stays broken, closed when everything works again.
Needs REPO_TOKEN (the workflow's forgejo.token), GITHUB_SERVER_URL and GITHUB_REPOSITORY (set by Forgejo Actions).
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import concurrent.futures
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TITLE = "Nightly link check: broken external links"
URL = re.compile(r"https?://[^\s)<>\"'`\]|]+")
SKIP_HOST = re.compile(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|[^/]*\.local$|[^/]*\.lan$|"
                       r"[^/]*\.invalid$|[^/]*\.test$|[^/]*\.home\.arpa$|(www\.)?example\.(com|org|net)$|[^/]*\.example$)")
PLACEHOLDER = re.compile(r"[<>{}]|\$|%[sd]|[Xx]\.[Yy]\.[Zz]")
AGENT = "camalert-linkcheck/1 (+https://github.com/kevinrossnl/camalert)"
BROKEN, WARNING, OK = "broken", "warning", "ok"


def files(root=ROOT):
    out = [os.path.join(root, "README.md"), os.path.join(root, "CHANGELOG.md")]
    out += sorted(glob.glob(os.path.join(root, "docs", "**", "*.md"), recursive=True))
    out += sorted(glob.glob(os.path.join(root, "homeassistant", "blueprints", "*.yaml")))
    return [f for f in out if os.path.exists(f)]


def host_of(url):
    return re.sub(r"^https?://", "", url).split("/", 1)[0].split("@")[-1].split(":")[0].lower()


def clean(url):
    return url.rstrip(".,;:!?*_")


def wanted(url):
    """Only public host names: no placeholder, no private / example address, no bare name (http://admin:...@),
    no IPv6 literal (the docs only use local ones)."""
    host = host_of(url)
    return not PLACEHOLDER.search(url) and not SKIP_HOST.match(host) and "." in host and "[" not in url[:12]


def collect(paths):
    """{url: [file:line, ...]} of every external URL worth checking."""
    found = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for no, line in enumerate(f, 1):
                for m in URL.finditer(line):
                    url = clean(m.group(0))
                    if wanted(url):
                        found.setdefault(url, []).append("%s:%d" % (os.path.relpath(path, ROOT).replace(os.sep, "/"), no))
    return found


def fetch(url, method, timeout=20):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def check(url, opener=fetch):
    """(status, detail) for one URL."""
    try:
        code = opener(url, "HEAD")
        if code in (403, 405, 501) or code is None:
            code = opener(url, "GET")
    except Exception as e:  # noqa: BLE001 - network trouble is a warning, not a broken link
        return WARNING, "%s" % e.__class__.__name__
    if code is not None and code < 400:
        return OK, str(code)
    if code in (401, 403, 429) or (code is not None and code >= 500 and code not in (501,)):
        return (WARNING if code in (401, 403, 429) else BROKEN), str(code)
    return BROKEN, str(code)


def run(found, opener=fetch, workers=8):
    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for url, res in zip(found, pool.map(lambda u: check(u, opener), found)):
            out[url] = res
    return out


def report(found, results):
    broken = sorted(u for u, (s, _d) in results.items() if s == BROKEN)
    warn = sorted(u for u, (s, _d) in results.items() if s == WARNING)
    lines = ["%d external links checked: %d broken, %d warnings." % (len(results), len(broken), len(warn))]
    for title, group in (("Broken", broken), ("Warnings (not counted, retried next night)", warn)):
        if group:
            lines += ["", "### " + title, ""]
            lines += ["- %s (%s) in %s" % (u, results[u][1], ", ".join(found[u][:3])) for u in group]
    return broken, "\n".join(lines)


class Forgejo(object):
    def __init__(self, server, repo, token, opener=urllib.request.urlopen):
        self.base, self.token, self.opener = "%s/api/v1/repos/%s" % (server.rstrip("/"), repo), token, opener

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": "token " + self.token,
                                              "Content-Type": "application/json"})
        with self.opener(req, timeout=20) as r:
            text = r.read().decode() or "null"
        return json.loads(text)

    def find(self):
        for state in ("open", "closed"):
            for i in self.call("GET", "/issues?type=issues&state=%s&limit=50&q=%s"
                               % (state, urllib.request.quote(TITLE))) or []:
                if i.get("title") == TITLE:
                    return i
        return None


def to_issue(forge, broken, text):
    """Creates / updates / closes the one issue. Returns what it did."""
    issue = forge.find()
    if broken:
        if issue is None:
            forge.call("POST", "/issues", {"title": TITLE, "body": text})
            return "created"
        forge.call("PATCH", "/issues/%d" % issue["number"], {"body": text, "state": "open"})
        return "updated"
    if issue is not None and issue.get("state") == "open":
        forge.call("POST", "/issues/%d/comments" % issue["number"], {"body": "All external links work again.\n\n" + text})
        forge.call("PATCH", "/issues/%d" % issue["number"], {"state": "closed"})
        return "closed"
    return "nothing"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--issue", action="store_true", help="open/update/close the Forgejo issue; always exit 0")
    a = ap.parse_args(argv)
    found = collect(files())
    results = run(found)
    broken, text = report(found, results)
    print(text)
    if a.issue:
        token, server, repo = (os.environ.get(k, "") for k in ("REPO_TOKEN", "GITHUB_SERVER_URL", "GITHUB_REPOSITORY"))
        if token and server and repo:
            try:
                print("issue:", to_issue(Forgejo(server, repo, token), broken, text))
            except Exception as e:  # noqa: BLE001 - never fail the nightly run on the issue part
                print("issue: could not update (%s)" % e.__class__.__name__)
        else:
            print("issue: no REPO_TOKEN / GITHUB_SERVER_URL / GITHUB_REPOSITORY, skipped")
        return 0
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
