"""Minimal in-process MQTT 3.1.1 broker for tests (#31), built on the shared codec (logic.mqtt_*).

    with Broker() as b:            # listens on 127.0.0.1:<free port>
        b.port
        b.wait_for(lambda m: m.topic.endswith("/state"))
        b.publish("camalert/x/show", b"garden")   # as another client would
        b.messages                 # every PUBLISH the broker received: Message(topic, payload, retain, client)

Supports CONNECT (user/password, last will with retain), SUBSCRIBE (+ and # wildcards, retained messages
are delivered), PUBLISH QoS 0, PINGREQ, DISCONNECT. A connection that drops without DISCONNECT publishes its
last will. Deterministic and fast: no real broker, no network outside 127.0.0.1.
"""
import socket
import threading
import time

import _paths

_paths.shared()
import logic  # noqa: E402

CONNACK_OK = b"\x20\x02\x00\x00"
PINGRESP = b"\xd0\x00"


class Message(object):
    def __init__(self, topic, payload, retain, client):
        self.topic, self.payload, self.retain, self.client = topic, payload, retain, client

    @property
    def text(self):
        return self.payload.decode("utf-8", "replace")

    def __repr__(self):
        return "Message(%r, %r, retain=%r, client=%r)" % (self.topic, self.payload[:60], self.retain, self.client)


def topic_matches(pattern, topic):
    p, t = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p):
        if part == "#":
            return True
        if i >= len(t) or (part != "+" and part != t[i]):
            return False
    return len(p) == len(t)


def _read_str(body, i):
    n = int.from_bytes(body[i:i + 2], "big")
    return body[i + 2:i + 2 + n], i + 2 + n


def parse_connect(body):
    """CONNECT body -> dict(client_id, user, password, will_topic, will_payload, will_retain, keepalive)."""
    name, i = _read_str(body, 0)
    if name != b"MQTT" or body[i] != 4:
        raise ValueError("not MQTT 3.1.1")
    flags, keepalive = body[i + 1], int.from_bytes(body[i + 2:i + 4], "big")
    i += 4
    cid, i = _read_str(body, i)
    out = {"client_id": cid.decode(), "keepalive": keepalive, "user": None, "password": None, "will_topic": None,
           "will_payload": None, "will_retain": bool(flags & 0x20)}
    if flags & 0x04:
        wt, i = _read_str(body, i)
        wp, i = _read_str(body, i)
        out["will_topic"], out["will_payload"] = wt.decode(), wp
    if flags & 0x80:
        u, i = _read_str(body, i)
        out["user"] = u.decode()
    if flags & 0x40:
        pw, i = _read_str(body, i)
        out["password"] = pw.decode()
    return out


class _Conn(object):
    def __init__(self, broker, sock):
        self.broker, self.sock = broker, sock
        self.client_id, self.will, self.subs, self.clean = None, None, [], False
        self.lock = threading.Lock()

    def send(self, data):
        with self.lock:
            try:
                self.sock.sendall(data)
            except OSError:
                pass

    def run(self):
        buf = b""
        try:
            while not self.broker.stopping:
                try:
                    data = self.sock.recv(4096)
                except socket.timeout:
                    continue
                if not data:
                    break
                packets, buf = logic.mqtt_split(buf + data)
                for kind, flags, body in packets:
                    self.packet(kind, flags, body)
                    if kind == 14:  # DISCONNECT
                        self.clean = True
                        return
        except OSError:
            pass
        finally:
            self.broker.gone(self)

    def packet(self, kind, flags, body):
        b = self.broker
        if kind == 1:
            info = parse_connect(body)
            self.client_id = info["client_id"]
            b.connects.append(info)
            if info["will_topic"]:
                self.will = (info["will_topic"], info["will_payload"], info["will_retain"])
            self.send(CONNACK_OK if b.accept(info) else b"\x20\x02\x00\x05")
        elif kind == 3:
            topic, payload = logic.mqtt_parse_publish(flags, body)
            b.route(topic, payload, bool(flags & 0x01), self.client_id)
        elif kind == 8:
            pid, i, topics = body[:2], 2, []
            while i < len(body):
                t, i = _read_str(body, i)
                i += 1  # requested QoS
                topics.append(t.decode())
            self.subs += topics
            b.subscriptions.append((self.client_id, topics))
            self.send(b"\x90" + logic._mqtt_len(2 + len(topics)) + pid + b"\x00" * len(topics))
            for t, (payload, _c) in sorted(b.retained.items()):
                if any(topic_matches(s, t) for s in topics):
                    self.send(logic.mqtt_publish(t, payload, True))
        elif kind == 12:
            self.send(PINGRESP)


class Broker(object):
    def __init__(self, user=None, password=None):
        self.user, self.password = user, password
        self.messages, self.connects, self.subscriptions = [], [], []
        self.retained = {}
        self.conns = []
        self.lock = threading.Condition()
        self.stopping = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.thread = threading.Thread(target=self._accept, name="fake-broker", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def stop(self):
        self.stopping = True
        for c in list(self.conns):
            try:
                c.sock.close()
            except OSError:
                pass
        self.sock.close()

    def accept(self, info):
        return self.user is None or (info["user"] == self.user and info["password"] == self.password)

    def _accept(self):
        while not self.stopping:
            try:
                s, _addr = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            s.settimeout(0.2)
            c = _Conn(self, s)
            self.conns.append(c)
            threading.Thread(target=c.run, daemon=True).start()

    def route(self, topic, payload, retain, client):
        with self.lock:
            self.messages.append(Message(topic, payload, retain, client))
            if retain:
                if payload:
                    self.retained[topic] = (payload, client)
                else:
                    self.retained.pop(topic, None)
            self.lock.notify_all()
        for c in list(self.conns):
            if any(topic_matches(s, topic) for s in c.subs):
                c.send(logic.mqtt_publish(topic, payload, False))

    def gone(self, conn):
        if conn in self.conns:
            self.conns.remove(conn)
        if conn.will and not conn.clean and not self.stopping:
            self.route(conn.will[0], conn.will[1], conn.will[2], conn.client_id)

    def publish(self, topic, payload, retain=False):
        """Publish as another client (e.g. Home Assistant or Frigate)."""
        self.route(topic, payload.encode() if isinstance(payload, str) else payload, retain, "test")

    def wait_for(self, pred, timeout=5.0):
        """First message matching pred (waits for it), or raise AssertionError."""
        end = time.time() + timeout
        with self.lock:
            while True:
                for m in self.messages:
                    if pred(m):
                        return m
                left = end - time.time()
                if left <= 0:
                    raise AssertionError("no matching MQTT message; got %r" % self.messages[-10:])
                self.lock.wait(left)

    def wait_subscribed(self, client_prefix="camalert-", timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            for cid, topics in self.subscriptions:
                if cid and cid.startswith(client_prefix):
                    return topics
            time.sleep(0.01)
        raise AssertionError("client did not subscribe")
