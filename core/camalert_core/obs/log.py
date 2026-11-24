# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Log levels, redaction of secrets and RFC 5424 syslog lines."""

import re


LOG_LEVELS = ("off", "errors", "normal", "verbose")
_LEVEL_RANK = {"error": 1, "normal": 2, "verbose": 3}
LOG_MAX_BYTES = 1024 * 1024


def log_allowed(setting, level):
    """Does a message of `level` (error/normal/verbose) go to the log with the setting off/errors/normal/verbose?"""
    limit = LOG_LEVELS.index(setting) if setting in LOG_LEVELS else 2
    return _LEVEL_RANK.get(level, 2) <= limit


_REDACT = [
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@]*:[^/\s@]*@"), r"\1***:***@"),  # user:pass@ in urls
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@]+@"), r"\1***@"),               # user@ (token as user)
    (re.compile(r"(?i)([?&](?:token|pwd|pass|password|passwd|usr|user|key|apikey|api_key|access_token|auth)=)[^&\s\"']*"),
     r"\1***"),
    (re.compile(r"(?i)(\bauthorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?[^\s,;\"']+"), r"\1***"),
    (re.compile(r"(?i)(\"(?:token|password|pwd|access_token|api_key)\"\s*:\s*\")[^\"]*(\")"), r"\1***\2"),
    (re.compile(r"(?i)(<(?:\w+:)?(?:Password|Nonce|Username)[^>]*>)[^<]*"), r"\1***"),
    (re.compile(r"(?i)\b((?:password|passwd|token|pwd)\s*[=:]\s*)[^\s&,;|\"']+"), r"\1***"),
]


def redact(text):
    """Removes passwords, tokens and user:pass@ from anything that goes to a log, a status page or diagnostics."""
    text = "" if text is None else str(text)
    for rx, repl in _REDACT:
        text = rx.sub(repl, text)
    return text


SYSLOG_SEVERITY = {"error": 3, "normal": 6, "verbose": 7}


def syslog_line(message, level, hostname, timestamp, app="camalert", facility=16):
    """RFC 5424 line (local0 by default) for a remote syslog (Loki/Alloy, rsyslog, ...)."""
    import time as _t
    pri = facility * 8 + SYSLOG_SEVERITY.get(level, 6)
    ts = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime(timestamp)) + ".%03dZ" % (int(timestamp * 1000) % 1000)
    host = re.sub(r"[^\x21-\x7e]", "_", hostname or "-")[:255] or "-"
    return "<%d>1 %s %s %s - - - %s" % (pri, ts, host, app, redact(message).replace("\n", " "))
