"""Report under reports/<run>/ (git-ignored): report.json, junit.xml, report.html and the OSD screenshots.

Device addresses, ssh names, real camera names and secrets never appear: devices are named by their profile name,
real cameras as cam1, cam2, ... and the text is run through the generic patterns of tools/check_private.py and the
private denylist (CAMALERT_DENYLIST) before it is written.
"""
import html
import json
import os
import sys
from xml.sax.saxutils import escape, quoteattr

from .fakes import ROOT


def private_hits(text):
    """Number of check_private findings (generic patterns + denylist) in text; the matches are never printed."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    try:
        import check_private
    finally:
        sys.path.pop(0)
    hits = 0
    low = text.lower()
    for line in text.splitlines():
        hits += sum(1 for pat, _ in check_private.GENERIC if pat.search(line))
    hits += sum(1 for w in check_private.denylist() if w in low)
    return hits


def redact(text, words):
    """Replaces every word (hosts, ssh names, secrets, real camera names) by its placeholder."""
    for word, placeholder in sorted(words.items(), key=lambda kv: -len(kv[0])):
        if word:
            text = text.replace(word, placeholder)
    return text


def junit(devices):
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<testsuites>"]
    for d in devices:
        cases = d.get("scenarios") or []
        fails = sum(1 for c in cases if c["status"] == "failed") + (1 if d["status"] == "error" else 0)
        skips = sum(1 for c in cases if c["status"] == "skipped") + (1 if d["status"] == "skipped" else 0)
        out.append('<testsuite name=%s tests="%d" failures="%d" skipped="%d">' % (
            quoteattr("e2e." + d["device"]), max(1, len(cases)), fails, skips))
        if d["status"] in ("skipped", "error") or not cases:
            tag = {"skipped": "skipped", "error": "failure"}.get(d["status"])
            out.append('<testcase classname=%s name="device">%s</testcase>' % (
                quoteattr("e2e." + d["device"]), "<%s message=%s/>" % (tag, quoteattr(d.get("reason", "")))
                if tag else ""))
        for c in cases:
            detail = "; ".join(x["detail"] for x in c["checks"])
            inner = {"failed": "<failure message=%s/>" % quoteattr(detail),
                     "skipped": "<skipped message=%s/>" % quoteattr(detail)}.get(c["status"], "")
            out.append('<testcase classname=%s name=%s time="%.1f">%s</testcase>' % (
                quoteattr("e2e." + d["device"]), quoteattr(c["name"]), c["seconds"], inner))
        out.append("</testsuite>")
    out.append("</testsuites>")
    return "\n".join(out) + "\n"


def page(data):
    rows = []
    for d in data["devices"]:
        rows.append("<h2>%s: %s</h2><p>%s</p>" % (escape(d["device"]), escape(d["status"]),
                                                   escape(d.get("reason", ""))))
        rows.append("<ul>%s</ul>" % "".join("<li>%s %s</li>" % ("OK" if c["ok"] else "FAIL", escape(c["name"]))
                                             for c in d.get("preconditions", [])))
        rows.append("<table><tr><th>scenario</th><th>status</th><th>checks</th></tr>%s</table>" % "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (escape(c["name"]), escape(c["status"]), "<br>".join(
                escape(x["detail"]) for x in c["checks"])) for c in d.get("scenarios", [])))
        rows += ['<p><img src="%s" width="480"></p>' % html.escape(s) for c in d.get("scenarios", [])
                 for s in c["screenshots"]]
    return ("<!DOCTYPE html><meta charset=utf-8><title>CamAlert e2e %s</title><h1>CamAlert e2e run %s</h1>%s\n"
            % (escape(data["run"]), escape(data["run"]), "\n".join(rows)))


def write(folder, data, words):
    os.makedirs(folder, exist_ok=True)
    text = redact(json.dumps(data, indent=1, sort_keys=True), words)
    data = json.loads(text)
    data["privacy_findings"] = private_hits(text)
    files = {"report.json": json.dumps(data, indent=1, sort_keys=True) + "\n", "junit.xml": junit(data["devices"]),
             "report.html": page(data)}
    for name, body in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(body)
    return data
