# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Who may call the API: address allowlist, token check, rate limit."""

import ipaddress
import socket

# The local network (#52): an explicit list instead of ipaddress.is_private, which also counts the documentation
# ranges (RFC 5737, RFC 3849), benchmarking (198.18.0.0/15) and other reserved blocks as private, but not CGNAT.
LAN_NETWORKS = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",   # RFC 1918
    "100.64.0.0/10",                                      # RFC 6598 CGNAT, also used by Tailscale
    "127.0.0.0/8", "169.254.0.0/16",                      # loopback, link-local
    "::1/128", "fe80::/10", "fc00::/7",                   # IPv6 loopback, link-local, unique local (incl. Tailscale)
))
# host names that are local by convention: no dots, or one of these suffixes (not resolved when set)
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal")


def ip_of(text):
    """ipaddress object of an address (an IPv4-mapped IPv6 address becomes IPv4), or None."""
    try:
        a = ipaddress.ip_address(str(text or "").strip().strip("[]").split("%")[0])
    except ValueError:
        return None
    mapped = getattr(a, "ipv4_mapped", None)
    return mapped or a


def lan_address(ip):
    """True for an address in the local network (LAN_NETWORKS); False for anything else or garbage."""
    a = ip_of(ip)
    return a is not None and any(a.version == n.version and a in n for n in LAN_NETWORKS)


def client_allowed(ip, allow="lan"):
    """'lan' allows LAN_NETWORKS only (RFC 1918, CGNAT/Tailscale, loopback, link-local, ULA); 'any' everything."""
    if allow == "any":
        return True
    return lan_address(ip)


def local_name(host):
    """A host name that is local by convention (no dots or a LOCAL_SUFFIXES suffix)."""
    h = (host or "").lower().rstrip(".")
    return bool(h) and ("." not in h or h.endswith(LOCAL_SUFFIXES))


def resolve(host, port=None):
    """Every address a host name resolves to (blocking: call it from a thread on Enigma2). [] if it does not."""
    try:
        infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    except (socket.error, UnicodeError, ValueError):
        return []
    return sorted({i[4][0] for i in infos})


def url_target(url, caller_ip=None, resolver=None):
    """Why a server-side request to url (the Home Assistant webhook) is refused, or None when it may go (#53):
    an http(s) url whose host is the caller, a LAN address, a local name, or a host name that resolves only to
    LAN addresses. resolver(host) -> [addresses] (default resolve(); blocking). Checked when the webhook is set
    and again before every post (the name may resolve elsewhere later)."""
    from urllib.parse import urlsplit
    text = str(url or "")
    if not text.startswith(("http://", "https://")):
        return "url must start with http:// or https://"
    try:
        host = urlsplit(text).hostname or ""
    except ValueError:
        return "invalid url"
    if not host:
        return "invalid url"
    if caller_ip and ip_of(host) is not None and ip_of(host) == ip_of(caller_ip):
        return None
    if ip_of(host) is not None:
        return None if lan_address(host) else "url must point to the local network"
    if local_name(host):
        return None
    addresses = (resolver or resolve)(host)
    if not addresses:
        return "url host name does not resolve"
    if not all(lan_address(a) for a in addresses):
        return "url must point to the local network"
    return None


def token_ok(expected, given):
    import hmac
    if not expected:
        return True
    return bool(given) and hmac.compare_digest(str(expected), str(given))


class RateLimiter(object):
    """At most `limit` requests per `window` seconds per caller address."""

    def __init__(self, limit=30, window=10.0):
        self.limit, self.window, self.seen = limit, window, {}

    def allow(self, who, now):
        times = [t for t in self.seen.get(who, ()) if now - t < self.window]
        ok = len(times) < self.limit
        if ok:
            times.append(now)
        self.seen[who] = times
        if len(self.seen) > 256:  # forget idle callers
            self.seen = {k: v for k, v in self.seen.items() if v and now - v[-1] < self.window}
        return ok


def exposed_without_token(allow, token, ip):
    """True when the API answers a caller outside the private network without a token (worth a warning)."""
    return allow == "any" and not token and not client_allowed(ip, "lan")
