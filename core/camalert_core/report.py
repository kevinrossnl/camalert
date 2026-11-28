# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The problem report of a player (#132): what a bug report needs, without secrets.

    build(status, settings, log_lines, extra, now)  -> report dict (redacted)
    text(report)                                    -> the report as plain text (to save or paste)
    issue_url(report)                               -> a pre-filled GitHub issue form, short enough for a QR code

Everything that leaves the player goes through scrub(): passwords, tokens and user:pass@ (obs.log.redact), the
webhook id, e-mail addresses, public IP addresses and host names that are not in the local network. Settings go
through the schema: password fields, the token and the Home Assistant webhook never appear, not even masked.
The player's id (often derived from the MAC address) is shortened."""
import json
import re
import time

from . import schema
from .access import LOCAL_SUFFIXES, lan_address
from .i18n import N_
from .obs.log import redact

# texts of the "Report a problem" screens on every player (translated through the master catalogue)
TITLE = N_("Report a problem")
HELP = N_("Scan the code with your phone: a GitHub issue opens with the player and the versions filled in. Then paste the full report (without passwords or tokens) from the saved file.")  # noqa: E501 (one literal: tools/strings.py)
SAVE = N_("Save the report")
SAVED = N_("Report saved in %s")
SAVE_FAILED = N_("Could not save the report: %s")
FILE_NAME = "camalert-report.txt"

REPORT_VERSION = 1
ISSUES_URL = "https://github.com/kevinrossnl/camalert/issues/new"
# the "Player" dropdown of .github/ISSUE_TEMPLATE/bug_report.yml (a pre-filled dropdown must match exactly)
PLAYER_LABELS = {"enigma2": "Enigma2 receiver", "kodi": "Kodi", "androidtv": "Android TV / Fire TV app",
                 "browser": "Web player or browser extension"}
URL_MAX = 600       # bytes: a version-17 code at level M, easy to scan from a TV
LOG_LINES = 100
ERROR_LINES = 10
SECRET_IDS = frozenset(s.id for s in schema.SETTINGS if s.type == "password") | frozenset(
    ("token", "ha_webhook", "ha_webhook_secret"))
# values that are not passwords but still private: kept out of the report entirely
DROPPED = frozenset(("ha_webhook", "ha_webhook_secret"))
STATUS_DROPPED = frozenset(("capabilities",))

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
_URL_HOST = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://(?:\*\*\*(?::\*\*\*)?@)?)(\[[0-9a-f:]+\]|[^/\s:?#\]\[]+)")
_WEBHOOK = re.compile(r"(?i)(/api/webhook/)[A-Za-z0-9_-]+")


def constants():
    """What the Kotlin and JavaScript ports need (core.json "report", generated.js DATA.report)."""
    return {"version": REPORT_VERSION, "issues_url": ISSUES_URL, "player_labels": dict(PLAYER_LABELS),
            "url_max": URL_MAX, "log_lines": LOG_LINES, "error_lines": ERROR_LINES,
            "secret_ids": sorted(SECRET_IDS | DROPPED), "status_dropped": sorted(STATUS_DROPPED),
            "local_suffixes": list(LOCAL_SUFFIXES), "file_name": FILE_NAME,
            "texts": {"title": TITLE, "help": HELP, "save": SAVE, "saved": SAVED, "save_failed": SAVE_FAILED}}


def _host_ok(host):
    h = host.strip("[]").lower()
    if lan_address(h):
        return True
    if ":" in h:  # an IPv6 address outside the local network
        return False
    if "." not in h:  # a plain name such as "homeassistant" or "localhost"
        return True
    return h.endswith(LOCAL_SUFFIXES)


def _public_ip(m):
    ip = m.group(1)
    parts = ip.split(".")
    if any(int(p) > 255 for p in parts):
        return ip  # a version number such as 1.2.300.4, not an address
    return ip if lan_address(ip) else "<public-ip>"


def scrub(text):
    """text without secrets, e-mail addresses, public IP addresses and non-local host names in urls."""
    text = redact(text)
    text = _WEBHOOK.sub(r"\1***", text)
    text = _EMAIL.sub("<e-mail>", text)
    text = _URL_HOST.sub(lambda m: m.group(1) + (m.group(2) if _host_ok(m.group(2)) else "<host>"), text)
    return _IPV4.sub(_public_ip, text)


def _scrub_value(v):
    if isinstance(v, str):
        return scrub(v)
    if isinstance(v, dict):
        return {k: _scrub_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_scrub_value(x) for x in v]
    return v


def settings_part(settings):
    """{schema id: value} without secrets (dropped, not masked) and with scrubbed text values."""
    out = {}
    for k in sorted(settings or {}):
        if k in SECRET_IDS or k in DROPPED:
            continue
        out[k] = _scrub_value(settings[k])
    return out


def _short_id(node):
    node = str(node or "")
    return node[:4] + "…" if len(node) > 6 else node


def build(status, settings=None, log_lines=None, extra=None, now=None):
    """The report of one player. status: the /camalert/status answer; settings: {schema id: value} (secrets are
    dropped here as well); log_lines: the newest last; extra: player details (model, image, OS, ...)."""
    now = time.time() if now is None else now
    st = {k: v for k, v in (status or {}).items() if k not in STATUS_DROPPED and k != "result"}
    if "id" in st:
        st["id"] = _short_id(st["id"])
    lines = [scrub(x) for x in (log_lines or [])][-LOG_LINES:]
    errors = [x for x in lines if re.search(r"(?i)\b(error|failed|traceback|exception)\b", x)][-ERROR_LINES:]
    return {
        "report": REPORT_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "camalert": (status or {}).get("version", ""),
        "platform": (status or {}).get("platform", ""),
        "player": _scrub_value(dict(extra or {})),
        "status": _scrub_value(st),
        "settings": settings_part(settings),
        "errors": errors,
        "log": lines,
    }


def player_version(report):
    """One line for the issue form: model, image/OS and version, as far as the player knows them."""
    p = report.get("player") or {}
    parts = [p.get(k) for k in ("model", "image", "os", "kodi", "android", "browser") if p.get(k)]
    return ", ".join(str(x) for x in parts)[:120]


def summary(report):
    """A few lines that tell a developer where to look (also on the player's screen)."""
    st = report.get("status") or {}
    platform = report.get("platform") or ""
    lines = ["CamAlert %s on %s" % (report.get("camalert") or "?", PLAYER_LABELS.get(platform, platform or "?"))]
    pv = player_version(report)
    if pv:
        lines.append(pv)
    state = []
    for key in ("go2rtc", "mqtt", "home_assistant", "protect", "screen"):
        if st.get(key) not in (None, ""):
            v = st[key]
            state.append("%s: %s" % (key, v if not isinstance(v, (dict, list)) else json.dumps(v, sort_keys=True)))
    if state:
        lines.append(", ".join(state))
    errors = report.get("errors") or []
    if errors:
        lines.append("Last error: " + errors[-1][:160])
    return lines


def make(backend, source="menu"):
    """(report, issue url) of a player from its api.Backend (the same answer as GET /camalert/report)."""
    from . import api
    out = api._report(backend, backend.controller(), {}, backend.settings(), source)
    return out["report"], out["issue_url"]


def text(report):
    """The whole report as text: a header to read, then the JSON (paste it into the issue)."""
    head = "\n".join(summary(report))
    return "%s\n\n%s\n" % (head, json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


def _quote(s):
    out = []
    for ch in s.encode("utf-8"):
        c = chr(ch)
        if c.isalnum() and ch < 128 or c in "-._~":
            out.append(c)
        else:
            out.append("%%%02X" % ch)
    return "".join(out)


def issue_url(report, base=ISSUES_URL, limit=URL_MAX):
    """The bug report form with player, versions and a short summary filled in. Shortened (the error line first,
    then the summary) so it stays below `limit` bytes for a QR code; the full report is pasted by hand."""
    fields = [("template", "bug_report.yml"),
              ("player", PLAYER_LABELS.get(report.get("platform"), "Other / not sure")),
              ("camalert_version", str(report.get("camalert") or "")),
              ("player_version", player_version(report))]
    pv = player_version(report)
    what = "\n".join(x for x in summary(report)[1:] if x != pv)

    def make(w):
        q = fields + ([("logs", w)] if w else [])
        return base + "?" + "&".join("%s=%s" % (k, _quote(v)) for k, v in q if v)

    url = make(what)
    while len(url.encode("utf-8")) > limit and what:
        what = what[:max(0, len(what) - max(10, (len(url) - limit) // 3))].rstrip()
        url = make(what)
    return url
