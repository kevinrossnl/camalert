#!/usr/bin/env python3
"""Records a real answer (go2rtc, Frigate, ONVIF, Kodi JSON-RPC, ...) as a test fixture, always anonymised (#32).

    record_fixture.py URL OUT.json [--name real=camN ...] [--header 'Name: value']
    record_fixture.py --file answer.json OUT.json        (anonymise a saved answer instead of fetching one)

Before anything is written, the text goes through anonymise():
  - IPv4 addresses -> 192.0.2.x (RFC 5737), IPv6 -> 2001:db8::x (RFC 3849), each real address always to the same one
    (loopback and the documentation ranges stay as they are);
  - host names with a dot (not .example/.invalid/.test/.localhost) -> hostN.example;
  - camera / stream names given with --name real=new (and JSON keys of a go2rtc /api/streams answer) -> cam1, cam2..;
  - passwords, tokens, user:pass@ -> *** (the same redaction as the logs);
  - ISO timestamps -> 2026-11-23T20:15:00, Unix times (9-10 digits) -> 1795464900;
then tools/check_private.py's generic checks and the CAMALERT_DENYLIST must pass, or nothing is written.
JSON fixtures get "anonymised": true at the top level (a list is wrapped as {"anonymised": true, "data": [...]}).
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import ipaddress
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "core"))
sys.path.insert(0, HERE)
from camalert_core.obs.log import redact  # noqa: E402
import check_private  # noqa: E402

FIXED_ISO = "2026-11-23T20:15:00"
FIXED_EPOCH = "1795464900"
RESERVED = (".example", ".invalid", ".test", ".localhost")
IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
IPV6 = re.compile(r"(?<![0-9A-Fa-f:])((?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4})(?![0-9A-Fa-f:])")
HOST = re.compile(r"(?i)\b((?:[a-z0-9-]+\.)+(?:[a-z]{2,24}))\b")
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?")
EPOCH = re.compile(r"(?<![\d.])1\d{9}(?:\.\d+)?(?![\d])")
KEEP_HOSTS = ("onvif.org", "w3.org", "xmlsoap.org", "docs.oasis-open.org", "w3c.org")


class Anonymiser(object):
    def __init__(self, names=None):
        self.names = dict(names or {})
        self.v4, self.v6, self.hosts = {}, {}, {}

    def _v4(self, m):
        text = m.group(1)
        try:
            ip = ipaddress.IPv4Address(text)
        except ValueError:
            return text
        if ip.is_loopback or ip.is_unspecified or ip in ipaddress.IPv4Network("192.0.2.0/24") \
                or ip in ipaddress.IPv4Network("198.51.100.0/24") or ip in ipaddress.IPv4Network("203.0.113.0/24"):
            return text
        if text not in self.v4:
            self.v4[text] = "192.0.2.%d" % (len(self.v4) + 10)
        return self.v4[text]

    def _v6(self, m):
        text = m.group(1)
        try:
            ip = ipaddress.IPv6Address(text)
        except ValueError:
            return text
        if ip.is_loopback or ip.is_unspecified or ip in ipaddress.IPv6Network("2001:db8::/32"):
            return text
        if text not in self.v6:
            self.v6[text] = "2001:db8::%x" % (len(self.v6) + 10)
        return self.v6[text]

    def _host(self, m):
        host = m.group(1)
        low = host.lower()
        if low.endswith(RESERVED) or any(low == k or low.endswith("." + k) for k in KEEP_HOSTS):
            return host
        if re.match(r"^[\d.]+$", host) or re.search(r"\.(?:jpe?g|png|mp4|json|xml|html?|py|txt|cgi|fcgi)$", low):
            return host
        if low not in self.hosts:
            self.hosts[low] = "host%d.example" % (len(self.hosts) + 1)
        return self.hosts[low]

    def text(self, s):
        s = redact(s)
        s = IPV4.sub(self._v4, s)
        s = IPV6.sub(self._v6, s)
        s = HOST.sub(self._host, s)
        s = ISO.sub(FIXED_ISO, s)
        s = EPOCH.sub(FIXED_EPOCH, s)
        for real, new in sorted(self.names.items(), key=lambda kv: -len(kv[0])):
            s = re.sub(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(real), new, s)
        return s

    def streams(self, data):
        """A go2rtc /api/streams answer: every stream name becomes camN (in sorted order)."""
        if isinstance(data, dict):
            for real in sorted(data):
                self.names.setdefault(real, "cam%d" % (len(self.names) + 1))
        return data


def anonymise(raw, names=None, streams=False):
    """Anonymised fixture text (str) from raw text. JSON stays JSON and gets "anonymised": true."""
    a = Anonymiser(names)
    try:
        data = json.loads(raw)
    except ValueError:
        return a.text(raw)
    if streams:
        a.streams(data)
    data = json.loads(a.text(json.dumps(data)))
    if isinstance(data, dict):
        data = dict({"anonymised": True}, **{k: v for k, v in data.items() if k != "anonymised"})
    else:
        data = {"anonymised": True, "data": data}
    return json.dumps(data, indent=1, sort_keys=False, ensure_ascii=False) + "\n"


def leaks(text, deny=None):
    """Problems check_private would report for this text (generic patterns and the denylist)."""
    deny = check_private.denylist() if deny is None else deny
    found = [what for pat, what in check_private.GENERIC if pat.search(text)]
    low = text.lower()
    found += ["denylisted word (#%d)" % (deny.index(w) + 1) for w in deny if w in low]
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", help="URL to fetch (or a file with --file)")
    ap.add_argument("out")
    ap.add_argument("--file", action="store_true", help="source is a saved answer, not a URL")
    ap.add_argument("--name", action="append", default=[], help="real=new name mapping (repeatable)")
    ap.add_argument("--streams", action="store_true", help="answer is go2rtc /api/streams: rename every stream")
    ap.add_argument("--header", action="append", default=[], help="'Name: value' request header")
    a = ap.parse_args(argv)
    if a.file:
        with open(a.source, encoding="utf-8") as f:
            raw = f.read()
    else:
        req = urllib.request.Request(a.source)
        for h in a.header:
            k, _, v = h.partition(":")
            req.add_header(k.strip(), v.strip())
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    names = dict(x.split("=", 1) for x in a.name if "=" in x)
    out = anonymise(raw, names, a.streams)
    bad = leaks(out)
    if bad:
        print("NOT written, still private: %s" % ", ".join(sorted(set(bad))), file=sys.stderr)
        return 1
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(out)
    print("wrote %s (%d bytes, anonymised)" % (a.out, len(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
