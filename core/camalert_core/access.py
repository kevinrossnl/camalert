# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Who may call the API: address allowlist, token check, rate limit."""

import ipaddress


def client_allowed(ip, allow="lan"):
    """'lan' allows private, loopback and link-local addresses only; 'any' allows everything."""
    if allow == "any":
        return True
    try:
        a = ipaddress.ip_address((ip or "").replace("::ffff:", ""))
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local


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
