# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Server addresses and stream / snapshot URLs (go2rtc and direct cameras)."""

import json
import re
from urllib.parse import parse_qs, quote, unquote, urlsplit


def normalize_server(url):
    """Accepts '192.168.1.10', '192.168.1.10:1984' or 'http://host:1984/'; returns 'http://host:port' or None."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return None
    if "://" not in u:
        if u.count(":") > 1 and not u.startswith("["):  # bare IPv6 literal, e.g. fd00::10
            u = "[%s]" % u
        u = "http://" + u
    try:
        p = urlsplit(u)
        port = p.port
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    port = port or (443 if p.scheme == "https" else 1984)
    host = "[%s]" % p.hostname if ":" in p.hostname else p.hostname
    return "%s://%s:%d" % (p.scheme, host, port)


GO2RTC_STATES = ("not_set", "invalid", "ok")


def go2rtc_state(server):
    """'not_set' (empty: the default since #73, nothing is contacted), 'invalid' (not an address) or 'ok'."""
    if not (server or "").strip():
        return "not_set"
    return "ok" if normalize_server(server) else "invalid"


def server_host(server):
    p = urlsplit(server or "")
    return p.hostname


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _source_stream(url):
    """The go2rtc stream a producer url reads from, or None when it reads from somewhere else (#117):
    ``ffmpeg:<stream>#...`` (configured, idle) or ``rtsp://127.0.0.1:8554/<stream>?...`` (go2rtc's own RTSP server,
    what go2rtc 1.9 shows while the derived stream runs; ``source=ffmpeg:<stream>#...`` in the query)."""
    if not isinstance(url, str):
        return None
    if url.startswith("ffmpeg:"):
        return url[len("ffmpeg:"):].split("#", 1)[0]
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme not in ("rtsp", "rtsps") or p.hostname not in LOOPBACK:
        return None
    source = (parse_qs(p.query).get("source") or [""])[0]
    if source.startswith("ffmpeg:"):
        return source[len("ffmpeg:"):].split("#", 1)[0]
    return unquote(p.path.lstrip("/")) or None


def derived_streams(data):
    """Names of helper streams in a go2rtc /api/streams answer (#117): every source of the stream transcodes
    another stream of the same go2rtc, as Keep cameras ready and the live substreams do. Such a stream is not a
    camera, whichever player made it."""
    if not isinstance(data, dict):
        return set()
    out = set()
    for name, info in data.items():
        producers = info.get("producers") if isinstance(info, dict) else None
        if not isinstance(producers, list) or not producers:
            continue
        bases = [_source_stream(p.get("url") if isinstance(p, dict) else None) for p in producers]
        if all(b is not None and b != name and b in data for b in bases):
            out.add(name)
    return out


def _inputs(url):
    """The -i arguments of an ``exec:ffmpeg ...`` or ``ffmpeg:...`` producer url (#125)."""
    if not isinstance(url, str) or not (url.startswith("exec:") or url.startswith("ffmpeg:")):
        return []
    parts = url.split()
    return [parts[i + 1].strip("'\"") for i, p in enumerate(parts[:-1]) if p == "-i"]


def composite_streams(data):
    """Names of streams in a go2rtc /api/streams answer that put two or more other streams of the same go2rtc
    together (an own mosaic: ``exec:ffmpeg -i rtsp://127.0.0.1:8554/<a> -i rtsp://127.0.0.1:8554/<b> ...
    -filter_complex ...``), #125. They stay cameras (show, default camera), but a mosaic, tour or camera overview
    without an explicit list leaves them out: a mosaic in a mosaic."""
    if not isinstance(data, dict):
        return set()
    out = set()
    for name, info in data.items():
        producers = info.get("producers") if isinstance(info, dict) else None
        if not isinstance(producers, list) or not producers:
            continue
        bases = []
        for p in producers:
            inputs = _inputs(p.get("url") if isinstance(p, dict) else None)
            if not inputs:
                bases = None
                break
            bases.extend(_source_stream(i) for i in inputs)
        if bases and all(b is not None and b != name and b in data for b in bases) and len(set(bases)) >= 2:
            out.add(name)
    return out


def stream_info_from_json(text):
    """(camera names as streams_from_json, set of composite streams among them) from one /api/streams answer."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return [], set()
    names = streams_from_json(text)
    return names, composite_streams(data) & set(names) if isinstance(data, dict) else set()


def overview_cameras(names, composites):
    """The default list for a mosaic, tour or camera overview: every camera except composite streams (#125)."""
    skip = set(composites or ())
    return [n for n in names if n not in skip]


def streams_from_json(text, all_streams=False):
    """Camera names from the go2rtc /api/streams answer, sorted; helper streams (#117) are left out unless
    all_streams is set."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    skip = set() if all_streams else derived_streams(data)
    return sorted(k for k in data.keys() if re.match(r"^[A-Za-z0-9_.-]+$", k) and k not in skip)


def rtsp_url(server, stream, port=8554):
    """RTSP over TCP (rtspt://) towards go2rtc. Plain HTTP-TS gives a black picture on many boxes."""
    host = server_host(server)
    if not host or not stream:
        return None
    if ":" in host:
        host = "[%s]" % host
    return "rtspt://%s:%d/%s" % (host, int(port), quote(stream, safe="_.-"))


def snapshot_url(server, stream, width=640):
    if not server or not stream:
        return None
    return "%s/api/frame.jpeg?src=%s&width=%d" % (server, quote(stream, safe="_.-"), int(width))


def tcp_url(url):
    """rtsp:// -> rtspt:// (RTSP over TCP; UDP often fails between networks)."""
    return "rtspt://" + url[len("rtsp://"):] if url.startswith("rtsp://") else url


def split_credentials(url):
    """'http://user:pw@host/x' -> ('http://host/x', 'user', 'pw'); without credentials user/pw are None."""
    p = urlsplit(url)
    if p.username is None:
        return url, None, None
    host = p.hostname + (":%d" % p.port if p.port else "")
    clean = "%s://%s%s%s" % (p.scheme, host, p.path, ("?" + p.query) if p.query else "")
    return clean, unquote(p.username), unquote(p.password or "")


def valid_port(value, default):
    """Port number 1..65535, otherwise the default (ports are free number fields in the settings)."""
    try:
        p = int(value)
    except (TypeError, ValueError, OverflowError):  # OverflowError: float('inf'), found by #34
        return default
    return p if 1 <= p <= 65535 else default


def parse_hostport(text, default_port=514):
    """'host:port' or 'host' -> (host, port) or None."""
    text = (text or "").strip()
    if not text:
        return None
    host, sep, port = text.rpartition(":")
    if not sep or not port.isdigit():
        return text, default_port
    return host, valid_port(port, default_port)
