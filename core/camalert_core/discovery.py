# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Players announce themselves on the local network as ``_camalert._tcp.local.`` (DNS-SD over mDNS, #121), so Home
Assistant offers "New device found" without typing an address.

What is announced: the instance name (the player name), port and the TXT keys id, name, platform, version,
api_version and https (0/1). Never a token or anything else from the settings. Nothing is announced while the API is
off (setting "enabled"); with "allow" = lan or any the API answers callers on the local network, so both announce.

How: ``Advertiser.update(info)``. Where avahi-daemon runs and its service folder is writable (Enigma2 images run as
root), a service file there does the work (avahi reloads the folder by itself). Elsewhere (LibreELEC: /etc is read
only; Kodi on a desktop) a small responder in this module answers mDNS queries itself (stdlib only, one thread). Both
are best effort: a failure is logged once and never stops the player.
"""
import os
import re
import socket
import struct
import threading
import time

SERVICE_TYPE = "_camalert._tcp.local."
TXT_KEYS = ("id", "name", "platform", "version", "api_version", "https")
AVAHI_DIR = "/etc/avahi/services"
AVAHI_FILE = "camalert.service"
AVAHI_PIDS = ("/run/avahi-daemon/pid", "/var/run/avahi-daemon/pid")
MDNS_ADDR, MDNS_PORT = "224.0.0.251", 5353
TTL = 120  # seconds; host and SRV/TXT records (RFC 6762 suggests 120 for them)
PTR_TTL = 4500

A, PTR, TXT, SRV, ANY = 1, 12, 16, 33, 255
IN, FLUSH = 1, 0x8000
SERVICES = "_services._dns-sd._udp.local."


# --- what is announced (pure) ---------------------------------------------------------------------------------------
def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))).strip()


def _cut(text, limit):
    """text shortened to at most limit UTF-8 bytes, never in the middle of a character."""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    return raw[:limit].decode("utf-8", "ignore").rstrip()


def instance_name(name, node_id):
    """The DNS-SD instance name: the player name (one label, at most 63 bytes), else "CamAlert <id>"."""
    return _cut(_clean(name) or "CamAlert %s" % _clean(node_id), 63)


def host_label(node_id):
    """Own host name for the responder (camalert-<id>.local.): never the name avahi already uses for the device."""
    label = re.sub(r"[^a-z0-9-]", "-", str(node_id or "").lower()).strip("-")[:50] or "player"
    return "camalert-%s.local." % label


def txt_record(node_id, name, platform, version, api_version, https=False):
    """[(key, value)] in TXT_KEYS order. Values are text; https is "1" or "0"."""
    values = {"id": _clean(node_id), "name": _clean(name), "platform": _clean(platform), "version": _clean(version),
              "api_version": str(int(api_version)), "https": "1" if https else "0"}
    return [(k, values[k]) for k in TXT_KEYS]


def service_info(node_id, name, platform, version, api_version, port, https=False):
    """Everything an Advertiser needs, or None for a missing id."""
    if not _clean(node_id):
        return None
    return {"instance": instance_name(name, node_id), "host": host_label(node_id), "port": int(port),
            "txt": txt_record(node_id, name, platform, version, api_version, https)}


def should_advertise(settings):
    """Announce only while the API is on (both "allow" values answer the local network)."""
    return bool(settings.get("enabled")) and settings.get("allow", "lan") in ("lan", "any")


def _xml(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("'", "&apos;"))


def avahi_service(info):
    """The avahi service file for info."""
    lines = ["<?xml version=\"1.0\" standalone='no'?>",
             '<!DOCTYPE service-group SYSTEM "avahi-service.dtd">',
             "<!-- CamAlert (#121): written by the player, removed when its API is off -->",
             "<service-group>",
             "  <name>%s</name>" % _xml(info["instance"]),
             "  <service>",
             "    <type>%s</type>" % SERVICE_TYPE[:-len(".local.")],
             "    <port>%d</port>" % info["port"]]
    lines += ["    <txt-record>%s</txt-record>" % _xml("%s=%s" % kv) for kv in info["txt"]]
    lines += ["  </service>", "</service-group>", ""]
    return "\n".join(lines)


# --- DNS messages (pure) ---------------------------------------------------------------------------------------------
def _labels(name):
    """'a.b.local.' -> ['a', 'b', 'local']; the instance label of a service name may contain dots itself."""
    if name.endswith("." + SERVICE_TYPE):
        return [name[:-len(SERVICE_TYPE) - 1]] + SERVICE_TYPE.rstrip(".").split(".")
    return [x for x in name.rstrip(".").split(".") if x]


def encode_name(name):
    out = b""
    for label in _labels(name):
        raw = label.encode("utf-8")[:63]
        out += struct.pack("B", len(raw)) + raw
    return out + b"\x00"


def encode_txt(txt):
    out = b""
    for k, v in txt:
        raw = ("%s=%s" % (k, v)).encode("utf-8")[:255]
        out += struct.pack("B", len(raw)) + raw
    return out or b"\x00"


def _rr(name, rtype, ttl, data, unique):
    cls = IN | (FLUSH if unique else 0)
    return encode_name(name) + struct.pack("!HHIH", rtype, cls, ttl, len(data)) + data


def records(info, ip, ttl=None):
    """{(name lower-case, type): [record bytes]} of the service info, host address ip."""
    instance = "%s.%s" % (info["instance"], SERVICE_TYPE)
    t = TTL if ttl is None else ttl
    srv = struct.pack("!HHH", 0, 0, info["port"]) + encode_name(info["host"])
    out = {
        (SERVICES.lower(), PTR): [_rr(SERVICES, PTR, PTR_TTL if ttl is None else ttl, encode_name(SERVICE_TYPE), False)],
        (SERVICE_TYPE.lower(), PTR): [_rr(SERVICE_TYPE, PTR, PTR_TTL if ttl is None else ttl, encode_name(instance),
                                          False)],
        (instance.lower(), SRV): [_rr(instance, SRV, t, srv, True)],
        (instance.lower(), TXT): [_rr(instance, TXT, t, encode_txt(info["txt"]), True)],
    }
    if ip:
        out[(info["host"].lower(), A)] = [_rr(info["host"], A, t, socket.inet_aton(ip), True)]
    return out


def message(answers, msg_id=0, questions=b"", qdcount=0):
    """A response (QR, AA) with these answer records."""
    return struct.pack("!HHHHHH", msg_id, 0x8400, qdcount, len(answers), 0, 0) + questions + b"".join(answers)


def announcement(info, ip, goodbye=False):
    """Unsolicited response with every record (TTL 0 = goodbye, when the API goes off)."""
    recs = records(info, ip, 0 if goodbye else None)
    return message([r for key in sorted(recs) for r in recs[key]])


def _read_name(data, pos, depth=0):
    """(name lower-case with trailing dot, position after it) of a possibly compressed name."""
    labels = []
    while True:
        if pos >= len(data) or depth > 20:
            raise ValueError("bad name")
        n = data[pos]
        if n == 0:
            return ".".join(labels).lower() + ".", pos + 1
        if n & 0xC0 == 0xC0:
            if pos + 1 >= len(data):
                raise ValueError("bad pointer")
            ptr = ((n & 0x3F) << 8) | data[pos + 1]
            rest, _ = _read_name(data, ptr, depth + 1)
            labels.append(rest[:-1])
            return ".".join(x for x in labels if x).lower() + ".", pos + 2
        labels.append(data[pos + 1:pos + 1 + n].decode("utf-8", "replace"))
        pos += 1 + n


def parse_query(data):
    """(id, [(name, type)], raw question section) of a query; None for an answer or rubbish."""
    try:
        msg_id, flags, qd = struct.unpack("!HHH", data[:6])
        if flags & 0x8000 or qd == 0:
            return None
        pos, out = 12, []
        for _ in range(qd):
            name, pos = _read_name(data, pos)
            qtype, _qclass = struct.unpack("!HH", data[pos:pos + 4])
            pos += 4
            out.append((name, qtype))
        return msg_id, out, data[12:pos]
    except (ValueError, struct.error, IndexError):
        return None


def answers_for(questions, info, ip):
    """The records that answer these questions ([] when none is about this player)."""
    recs = records(info, ip)
    instance = ("%s.%s" % (info["instance"], SERVICE_TYPE)).lower()
    out = []
    for name, qtype in questions:
        keys = []
        if name == SERVICE_TYPE.lower() and qtype in (PTR, ANY):
            keys = [(name, PTR), (instance, SRV), (instance, TXT), (info["host"].lower(), A)]
        elif name == SERVICES.lower() and qtype in (PTR, ANY):
            keys = [(name, PTR)]
        elif name == instance and qtype in (SRV, TXT, ANY):
            keys = [(instance, SRV), (instance, TXT), (info["host"].lower(), A)] if qtype != TXT else [(instance, TXT)]
        elif name == info["host"].lower() and qtype in (A, ANY):
            keys = [(name, A)]
        for k in keys:
            for r in recs.get(k, []):
                if r not in out:
                    out.append(r)
    return out


def local_ip():
    """The address this device uses on the local network ('' when there is none)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((MDNS_ADDR, MDNS_PORT))  # no packet is sent: only picks the outgoing interface
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


# --- the responder (one thread) --------------------------------------------------------------------------------------
class Responder(object):
    """Answers mDNS queries for one service (shares port 5353 with other mDNS stacks via SO_REUSEADDR/PORT)."""

    def __init__(self, log=None, ip=local_ip, sock_factory=None, clock=time.time):
        self.log, self.ip, self.clock = log or (lambda m, level="normal": None), ip, clock
        self.sock_factory = sock_factory or self._socket
        self.info, self.sock, self.thread = None, None, None
        self.lock = threading.Lock()
        self.last = {}  # answer bytes -> time it was last multicast (at most once a second, RFC 6762 6.)

    @staticmethod
    def _socket():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        s.bind(("", MDNS_PORT))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                     socket.inet_aton(MDNS_ADDR) + socket.inet_aton("0.0.0.0"))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.settimeout(1.0)
        return s

    @property
    def running(self):
        return self.sock is not None

    def start(self, info):
        with self.lock:
            same = self.running and info == self.info
            self.info = info
            if not self.running:
                try:
                    self.sock = self.sock_factory()
                except OSError as e:
                    self.log("network announcement not possible: %s" % e, "error")
                    return False
                self.thread = threading.Thread(target=self._loop, args=(self.sock,), name="camalert-mdns")
                self.thread.daemon = True
                self.thread.start()
        if not same:
            self.announce()
        return True

    def announce(self, goodbye=False):
        info, sock = self.info, self.sock
        if info is None or sock is None:
            return
        try:
            sock.sendto(announcement(info, self.ip(), goodbye), (MDNS_ADDR, MDNS_PORT))
        except OSError as e:
            self.log("network announcement failed: %s" % e, "verbose")

    def stop(self):
        with self.lock:
            if not self.running:
                return
            self.announce(goodbye=True)
            sock, self.sock, self.info = self.sock, None, None
        try:
            sock.close()
        except OSError:
            pass

    def handle(self, data, addr):
        """The reply to one packet: (bytes, address) or None."""
        info = self.info
        q = parse_query(data) if info is not None else None
        if q is None:
            return None
        msg_id, questions, raw = q
        ans = answers_for(questions, info, self.ip())
        if not ans:
            return None
        if addr[1] != MDNS_PORT:  # legacy unicast query (e.g. dig -p 5353): answer the asker, with its id
            return message(ans, msg_id, raw, len(questions)), addr
        packet = message(ans)
        now = self.clock()
        if now - self.last.get(packet, 0) < 1.0:
            return None
        self.last = {packet: now}
        return packet, (MDNS_ADDR, MDNS_PORT)

    def _loop(self, sock):
        while self.sock is sock:
            try:
                data, addr = sock.recvfrom(9000)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                reply = self.handle(data, addr)
                if reply is not None:
                    sock.sendto(reply[0], reply[1])
            except Exception as e:  # noqa: BLE001 - never let the thread die
                self.log("network announcement: %s" % e, "verbose")


# --- choosing avahi or the responder ---------------------------------------------------------------------------------
def avahi_running(pids=AVAHI_PIDS):
    return any(os.path.exists(p) for p in pids)


def allowed():
    """False when CAMALERT_NO_ANNOUNCE is set (the test suite sets it: tests never announce on a real network)."""
    return not os.environ.get("CAMALERT_NO_ANNOUNCE")


class Advertiser(object):
    """update(info) announces info (None: stops announcing); stop() before the player goes."""

    def __init__(self, log=None, avahi_dir=AVAHI_DIR, running=avahi_running, responder=None, enabled=allowed):
        self.log = log or (lambda m, level="normal": None)
        self.avahi_dir, self.avahi_running, self.enabled = avahi_dir, running, enabled
        self.responder = responder or Responder(self.log)
        self.info, self.how = None, None

    @property
    def path(self):
        return os.path.join(self.avahi_dir, AVAHI_FILE)

    def avahi_usable(self):
        return bool(self.avahi_dir) and os.path.isdir(self.avahi_dir) and os.access(self.avahi_dir, os.W_OK) and \
            self.avahi_running()

    def _remove_file(self):
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
        except OSError as e:
            self.log("could not remove %s: %s" % (self.path, e), "error")

    def _write_file(self, info):
        text = avahi_service(info)
        try:
            with open(self.path, encoding="utf-8") as f:
                if f.read() == text:
                    return True
        except OSError:
            pass
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(self.path + ".tmp", self.path)
            return True
        except OSError as e:
            self.log("could not write %s: %s" % (self.path, e), "error")
            return False

    def update(self, info):
        try:
            if info is None or not self.enabled():
                self.stop()
                return None
            if self.avahi_usable() and self._write_file(info):
                self.responder.stop()
                how = "avahi"
            else:
                self._remove_file() if self.how == "avahi" else None
                how = "responder" if self.responder.start(info) else None
            if how != self.how or info != self.info:
                self.log("announced on the network as %s (%s)" % (info["instance"], how) if how else
                         "not announced on the network", "verbose" if how == self.how else "normal")
            self.info, self.how = info, how
            return how
        except Exception as e:  # noqa: BLE001 - discovery must never break the player
            self.log("network announcement failed: %s" % e, "error")
            return None

    def stop(self):
        if self.how == "avahi" or (self.avahi_dir and os.path.exists(self.path)):
            self._remove_file()
        self.responder.stop()
        if self.how is not None:
            self.log("no longer announced on the network", "verbose")
        self.info, self.how = None, None
