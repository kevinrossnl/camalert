# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Server addresses and stream / snapshot URLs (go2rtc and direct cameras)."""

import json
import re
from urllib.parse import quote, unquote, urlsplit


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


def server_host(server):
    p = urlsplit(server or "")
    return p.hostname


def streams_from_json(text):
    """Stream names from the go2rtc /api/streams answer, sorted."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    return sorted(k for k in data.keys() if re.match(r"^[A-Za-z0-9_.-]+$", k))


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
    except (TypeError, ValueError):
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
