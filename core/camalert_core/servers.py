# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Several go2rtc servers (#15).

The setting `server` stays the first (main) server; `more_servers` lists the others, comma or newline separated,
each `[prefix=]address`. Cameras of the main server keep their names. A server with a prefix shows its cameras as
`<prefix>.<stream>`; a server without one keeps the stream names unless an earlier server already has that name,
then the camera becomes `s<n>.<stream>` (n = position of the server, the main server is s1).

A camera name maps back to (server, stream) through the last camera list (`combine`). Without a list yet,
`resolve` takes `<prefix or sN>.<rest>` to that server and everything else to the main server, so names from
before #15 behave exactly as before.
"""
import re

from .urls import normalize_server

PREFIX = re.compile(r"^[a-z0-9_-]{1,16}$")
SEP = "."


class Server(object):
    def __init__(self, sid, url, prefix=None):
        self.id, self.url, self.prefix = sid, url, prefix

    def __eq__(self, other):
        return isinstance(other, Server) and (self.id, self.url, self.prefix) == (other.id, other.url, other.prefix)

    def __repr__(self):
        return "Server(%r, %r, %r)" % (self.id, self.url, self.prefix)


def parse_more(text):
    """(entries, problems) from the `more_servers` text: entries are (prefix or None, normalized url); problems
    are the parts that are not a valid entry (shown to the user, never fatal)."""
    entries, problems = [], []
    for part in re.split(r"[,\n;]+", text or ""):
        part = part.strip()
        if not part:
            continue
        prefix = None
        if "=" in part and "://" not in part.split("=", 1)[0]:
            prefix, part = part.split("=", 1)
            prefix = prefix.strip().lower()
            if not PREFIX.match(prefix) or re.match(r"^s\d+$", prefix):
                problems.append(prefix + "=" + part.strip())
                continue
        url = normalize_server(part)
        if not url:
            problems.append(part)
            continue
        entries.append((prefix, url))
    return entries, problems


def server_list(main, more_text=""):
    """The servers in order: the main server (if set and valid) as s1, then the valid `more_servers` entries.
    The same address twice counts once; a prefix that is used twice keeps only the first server."""
    out, seen, prefixes = [], set(), set()
    m = normalize_server(main)
    if m:
        out.append(Server("s1", m))
        seen.add(m)
    for prefix, url in parse_more(more_text)[0]:
        if url in seen or (prefix and prefix in prefixes):
            continue
        seen.add(url)
        if prefix:
            prefixes.add(prefix)
        out.append(Server("s%d" % (len(out) + 1), url, prefix))
    return out


def combine(per_server):
    """per_server: [(Server, [stream names], set of composite streams)] in server order (a server that did not
    answer is left out by the caller). Returns (names, composites, mapping): the camera names (sorted), the
    composite streams under their camera names, and {camera name: (server url, stream)}."""
    names, composites, mapping = [], set(), {}
    for srv, streams, comp in per_server:
        for stream in streams:
            if srv.prefix:
                name = srv.prefix + SEP + stream
            elif stream in mapping:
                name = srv.id + SEP + stream
            else:
                name = stream
            if name in mapping:  # s2.x may exist as a real stream name: keep the first
                continue
            mapping[name] = (srv.url, stream)
            names.append(name)
            if stream in (comp or ()):
                composites.add(name)
    return sorted(names), composites, mapping


def resolve(name, servers, mapping=None):
    """(server url, stream) for a camera name, or (None, name) without servers. A mapping entry for a server that
    is no longer configured is ignored (the settings changed since the last camera list)."""
    if not servers:
        return None, name
    if mapping and name in mapping and mapping[name][0] in [s.url for s in servers]:
        return mapping[name]
    if SEP in (name or ""):
        head, rest = name.split(SEP, 1)
        for srv in servers:
            if rest and head in (srv.prefix, srv.id) and srv.id != "s1":
                return srv.url, rest
    return servers[0].url, name


def multiple(servers):
    return len(servers) > 1


def name_for_stream(host, stream, mapping):
    """The camera name for a stream played from `host` (the reverse of resolve, for a channel that plays), or
    None. Only needed with several servers: on one server the stream is the camera name."""
    from .urls import server_host
    for name, (srv, st) in sorted((mapping or {}).items()):
        if st == stream and server_host(srv) == host:
            return name
    return None
