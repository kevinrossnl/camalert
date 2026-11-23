#!/usr/bin/env python3
"""Fails if the repository contains anything that looks private.

    check_private.py [root]

Generic checks: private keys, tokens, passwords in URLs. Personal words (own IP ranges, domains, names) come from
the environment variable CAMALERT_DENYLIST (one entry per line or comma separated), stored as a CI secret so the
list itself is never published.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import os
import re
import subprocess
import sys

GENERIC = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "JWT token"),
    (re.compile(r"\b(?:ghp|gho|github_pat|glpat)_[A-Za-z0-9_]{20,}"), "access token"),
    (re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@\"']+:(?!<|\{|PASSWORD|password|pass\b)[^@\s/\"']{4,}@", re.I), "password in URL"),
    (re.compile(r"\bntfy\.sh/[A-Za-z0-9_-]{6,}"), "ntfy topic"),
]
SKIP_DIRS = {".git", "dist", "__pycache__"}


def files(root):
    try:
        out = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=root).decode()
        return [os.path.join(root, f) for f in out.splitlines() if f]
    except (subprocess.CalledProcessError, OSError):
        res = []
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            res += [os.path.join(d, n) for n in names]
        return res


def denylist():
    raw = os.environ.get("CAMALERT_DENYLIST", "")
    return [w.strip().lower() for w in re.split(r"[\n,]", raw) if len(w.strip()) >= 3]


# Public names that may appear even though parts of them are on the denylist (the GitHub owner of the project).
PUBLIC = ["kevinrossnl"]


def problems(root, deny):
    found = []
    for p in files(root):
        rel = os.path.relpath(p, root)
        try:
            text = open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        low = text.lower()
        for name in PUBLIC:
            low = low.replace(name, " ")
        for i, line in enumerate(text.splitlines(), 1):
            for pat, what in GENERIC:
                if pat.search(line):
                    found.append("%s:%d: %s" % (rel, i, what))
        for w in deny:
            if w in low or w in rel.lower().replace("kevinrossnl", " "):
                found.append("%s: contains a denylisted word (#%d)" % (rel, deny.index(w) + 1))
    return found


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..")
    deny = denylist()
    p = problems(root, deny)
    for x in p:
        print("PRIVATE?", x)
    print("privacy check: %d denylist entries, %d problems" % (len(deny), len(p)))
    sys.exit(1 if p else 0)
