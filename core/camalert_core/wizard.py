# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The first-start wizard (#120), the same on every player: when it starts, where to look for go2rtc, the search
itself (in threads, with a time limit) and the order of the steps. The players only draw the screens.

    should_start(settings)      first start: wizard_done off, go2rtc not set and not in direct mode
    candidates(own_ip, ...)     homeassistant.local, the Home Assistant host if known, then the own /24
    scan(candidates, probe)     probe each address in threads; [(server, cameras)] in candidate order
    probe(server)               cameras of a go2rtc /api/streams answer (helper streams left out), or None
    steps(direct)               go2rtc, camera, test, done (direct mode: no camera step, no go2rtc address)

Never call scan() or probe() on a UI thread: they wait for the network.
"""
import json
import socket
import threading
import time
from urllib.request import urlopen

from .urls import go2rtc_state, normalize_server, server_host, streams_from_json

PORT = 1984
HA_NAME = "homeassistant.local"
TIMEOUT = 0.8         # seconds per address
WORKERS = 32          # parallel probes
BUDGET = 10.0         # seconds for the whole search; slower answers are not waited for
STEPS = ("go2rtc", "camera", "test", "done")
DIRECT_STEPS = ("go2rtc", "test", "done")  # direct mode: the cameras come from the camera file


def should_start(settings):
    """True when the wizard opens by itself: not done before, no go2rtc address and not in direct mode (an
    existing installation with an address never sees it)."""
    if settings.get("wizard_done"):
        return False
    if settings.get("source", "go2rtc") == "direct":
        return False
    return go2rtc_state(settings.get("server", "")) == "not_set"


def steps(direct=False):
    return DIRECT_STEPS if direct else STEPS


def next_step(step, direct=False):
    """The step after step, or None after the last one."""
    order = steps(direct)
    i = order.index(step) if step in order else -1
    return order[i + 1] if 0 <= i < len(order) - 1 else None


def own_ip(make_socket=socket.socket):
    """The player's own LAN address (no packet is sent), or None."""
    s = make_socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # TEST-NET-1: only picks the outgoing interface
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") or ip == "0.0.0.0" else ip
    except OSError:
        return None
    finally:
        s.close()


def ha_host(settings):
    """The Home Assistant host if the player knows it: the MQTT broker or the webhook address."""
    for key in ("ha_webhook", "mqtt_host"):
        value = (settings.get(key) or "").strip()
        if not value:
            continue
        host = server_host(value if "://" in value else "http://" + value)
        if host:
            return host
    return None


def _server(host, port=PORT):
    return "http://%s:%d" % ("[%s]" % host if ":" in host else host, port)


def candidates(own=None, ha=None, port=PORT):
    """go2rtc addresses to try, most likely first: homeassistant.local, the Home Assistant host, then every other
    address of the own /24 (IPv4 only). No duplicates; the player itself is included (go2rtc may run on it)."""
    out = [_server(HA_NAME, port)]
    if ha:
        out.append(_server(ha, port))
    parts = (own or "").split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        net = ".".join(parts[:3])
        out += [_server("%s.%d" % (net, i), port) for i in range(1, 255)]
    seen, unique = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def cameras_from(text):
    """Camera names from a go2rtc /api/streams answer; None when it is not one (another service on the port)."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return streams_from_json(text)


def probe(server, timeout=TIMEOUT, opener=urlopen):
    """The cameras of the go2rtc at server, or None if nothing answers like go2rtc there."""
    try:
        with opener(server + "/api/streams", timeout=timeout) as r:
            return cameras_from(r.read(512 * 1024).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - refused, timed out, not HTTP: not go2rtc
        return None


def scan(addresses, prober=probe, workers=WORKERS, budget=BUDGET, clock=time.time, stop=None):
    """Probes the addresses in parallel threads and returns [(server, cameras)] of every go2rtc found, in the order
    of addresses. Returns after budget seconds at the latest (late answers are dropped) or when stop is set."""
    addresses = list(addresses)
    found = {}
    lock = threading.Lock()
    queue = list(enumerate(addresses))
    deadline = clock() + budget
    stop = stop or threading.Event()

    def work():
        while not stop.is_set():
            with lock:
                if not queue or clock() > deadline:
                    return
                i, server = queue.pop(0)
            cams = prober(server)
            if cams is not None:
                with lock:
                    found[i] = (server, cams)

    threads = [threading.Thread(target=work, name="camalert-wizard-%d" % n) for n in range(min(workers, len(queue)) or 0)]
    for t in threads:
        t.daemon = True
        t.start()
    for t in threads:
        t.join(max(0.0, deadline - clock()))
    with lock:
        return [found[i] for i in sorted(found)]


def unique_servers(found):
    """[(server, cameras)] with one entry per go2rtc: homeassistant.local and its own address are the same go2rtc
    when they list the same cameras; the named one is kept."""
    out, seen = [], set()
    for server, cams in found:
        key = tuple(cams)
        if key in seen and cams:
            continue
        seen.add(key)
        out.append((server, cams))
    return out


def server_from_input(text):
    """A typed address as a go2rtc server ('192.168.1.10' becomes http://192.168.1.10:1984), or None."""
    text = (text or "").strip()
    if text.endswith("://"):
        return None  # a scheme only ('http://')
    return normalize_server(text)  # no port: 1984 (https: 443)


def result(server=None, camera=None, direct=False):
    """The settings the wizard saves at the end (also when the user stops early: it does not open again)."""
    out = {"wizard_done": True}
    if direct:
        out["source"] = "direct"
    elif server:
        out["source"], out["server"] = "go2rtc", server
    if camera:
        out["camera"] = camera
    return out


def add_text(name, ip, port):
    """(player name, address) for the last screen: how to add this player in Home Assistant."""
    return name or "CamAlert", "%s:%s" % (ip or "?", port)
