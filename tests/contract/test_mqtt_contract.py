"""Both MQTT clients (Enigma2: Twisted protocol in e2fake; Kodi: socket thread) against an in-process broker,
checked against the MQTT contract table (mqtt_table.py, #31)."""
import json
import socket
import threading
import time
import unittest

import _paths
from contract import mqtt_table as T
from fakes.broker import Broker, topic_matches
from fakes.controller import RecordingController

CAMS = ["front_door", "garden"]
# (command name, player) -> issue
KNOWN = {}


def wait(pred, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.01)
    return False


class KodiClient(object):
    platform = "kodi"

    def __init__(self, port, discovery=True):
        from kodi import stubs
        self.store = stubs.install({"mqtt_enabled": "true", "mqtt_host": "127.0.0.1", "mqtt_port": str(port),
                                         "mqtt_discovery": "true" if discovery else "false", "mqtt_name": "CamAlert test",
                                         "frigate_enabled": "true"})
        _paths.kodi_package()
        self.mqtt = _paths.kodi_module("mqtt")
        self.mqtt.node_id = lambda: T.NODE
        src = _paths.kodi_module("sources")
        src.all_camera_names = lambda s=None: list(CAMS)
        src.camera_urls = lambda n, s=None: ("http://x/%s.mp4" % n, "http://x/%s.jpg" % n,
                                              n.replace("_", " ").capitalize())
        self.ctl = RecordingController()

    def start(self):
        self.mqtt.start(self.ctl)

    def pump(self):
        pass  # runs in its own thread

    def button(self, camera, button):
        self.mqtt.publish_button(camera, button)

    def stop(self):
        self.mqtt.stop()


class _Transport(object):
    def __init__(self, sock):
        self.sock = sock

    def write(self, data):
        self.sock.sendall(data)

    def loseConnection(self):
        self.sock.close()


class Enigma2Client(object):
    """The Twisted protocol, fed from a real socket by pump() in the test thread (deterministic)."""
    platform = "enigma2"

    def __init__(self, port, discovery=True):
        from enigma2.harness import e2fake
        self.e2fake = e2fake
        self.env = e2fake.install("openatv")
        c = self.env.config.plugins.camalert
        c.mqtt_enabled.value, c.mqtt_host.value, c.mqtt_port.value = True, "127.0.0.1", port
        c.mqtt_discovery.value, c.mqtt_name.value, c.frigate_enabled.value = discovery, "CamAlert test", True
        self.m = self.env.camalert.mqtt
        self.m.node_id = lambda: T.NODE
        self.m.all_camera_names = lambda: list(CAMS)
        self.m.camera_urls = lambda n: ("rtspt://x/%s" % n, "http://x/%s.jpg" % n, n.replace("_", " ").capitalize())
        self.ctl = RecordingController()
        self.env.camalert.display.Controller.instance = self.ctl
        self.port = port
        self.lock = threading.Lock()

    def start(self):
        self.m._factory = self.m.CamAlertMqttFactory()
        self.p = self.m.CamAlertMqtt()
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.sock.settimeout(0.05)
        self.p.makeConnection(_Transport(self.sock))
        self.p.connectionMade()

    def pump(self):
        """What the reactor does: deliver received bytes, run thread work and due callLater calls."""
        with self.lock:
            try:
                data = self.sock.recv(4096)
                if data:
                    self.p.dataReceived(data)
            except (socket.timeout, OSError):
                pass
            r = self.env.reactor
            for d in list(r.deferred):
                r.deferred.remove(d)
                d.fire(d.fn(*d.args))
            for call in list(r.calls):
                r.calls.remove(call)
                if not call.cancelled:
                    call.fn(*call.a, **call.kw)

    def button(self, camera, button):
        self.m.publish_button(camera, button)

    def stop(self):
        self.m.stop()
        self.sock.close()
        self.e2fake.uninstall()


def run_player(client_class):
    """Connects one player to a fresh broker, sends every command; returns (broker messages, calls per command,
    subscriptions, connect info)."""
    with Broker() as b:
        cl = client_class(b.port)
        cl.start()
        stop = threading.Event()

        def pumping():
            while not stop.is_set():
                cl.pump()
                time.sleep(0.005)
        pump = threading.Thread(target=pumping, daemon=True)
        pump.start()
        try:
            subs = b.wait_subscribed()
            b.wait_for(lambda m: m.topic.endswith("/config"))
            calls = {}
            for name, tmpl, payload, _expected in T.COMMANDS:
                before = len(cl.ctl.calls)
                b.publish(T.topic(tmpl), payload)
                wait(lambda: len(cl.ctl.calls) > before)
                calls[name] = cl.ctl.calls[before] if len(cl.ctl.calls) > before else None
            cl.button("garden", "red")
            b.wait_for(lambda m: m.topic.endswith("/button"))
            wait(lambda: sum(m.topic.endswith("/state") for m in b.messages) >= 3)
        finally:
            cl.stop()
            stop.set()
            pump.join(2)
        b.wait_for(lambda m: m.topic.endswith("/availability") and m.payload == b"offline")
        return list(b.messages), calls, subs, b.connects[0]


class TestMqttContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {c.platform: run_player(c) for c in (Enigma2Client, KodiClient)}

    def test_subscriptions(self):
        for platform, (_msgs, _calls, subs, _conn) in self.runs.items():
            self.assertEqual(sorted(subs), sorted(T.topic(t) for t in T.SUBSCRIBED), platform)

    def test_last_will(self):
        for platform, (_msgs, _calls, _subs, conn) in self.runs.items():
            topic, payload, retain = T.LAST_WILL
            self.assertEqual((conn["will_topic"], conn["will_payload"], conn["will_retain"]),
                             (T.topic(topic), payload, retain), platform)
            self.assertEqual(conn["client_id"], "camalert-" + T.NODE, platform)

    def test_published_topics_match_the_table(self):
        for platform, (msgs, _calls, _subs, _conn) in self.runs.items():
            ours = [m for m in msgs if m.client != "test"]
            self.assertTrue(ours, platform)
            for m in ours:
                rows = [r for r in T.PUBLISHED if topic_matches(T.topic(r[0]), m.topic)]
                self.assertTrue(rows, "%s: %s is not in the MQTT table" % (platform, m.topic))
                _t, retain, check = rows[0]
                self.assertEqual(m.retain, retain, "%s: retain of %s" % (platform, m.topic))
                self.assertTrue(check(m.payload), "%s: %s payload %r (%s)" % (platform, m.topic, m.payload,
                                                                              check.__name__))
            for tmpl, _r, _c in T.PUBLISHED:
                self.assertTrue(any(topic_matches(T.topic(tmpl), m.topic) for m in ours),
                                "%s never published %s" % (platform, tmpl))

    def test_commands(self):
        unexpected, stale = [], []
        for platform, (_msgs, calls, _subs, _conn) in self.runs.items():
            for name, _t, _p, expected in T.COMMANDS:
                differs = calls.get(name) != expected
                known = KNOWN.get((name, platform))
                if differs and not known:
                    unexpected.append("%s %s: %r, expected %r" % (platform, name, calls.get(name), expected))
                elif known and not differs:
                    stale.append("%s %s (%s)" % (platform, name, known))
        self.assertEqual(unexpected, [])
        self.assertEqual(stale, [], "fixed: remove from KNOWN")

    def test_discovery_is_the_same_on_every_player(self):
        found = {}
        for platform, (msgs, _calls, _subs, _conn) in self.runs.items():
            found[platform] = {}
            for m in msgs:
                if m.topic.startswith("homeassistant/"):
                    d = json.loads(m.payload)
                    for a, b in T.PLATFORM_FIELDS:
                        d[a].pop(b)
                    found[platform][m.topic] = d
        self.assertTrue(found["enigma2"])
        self.assertEqual(found["enigma2"], found["kodi"])


SEEDED = ["homeassistant/button/camalert_{node}/show_old_camera/config",
          "homeassistant/button/camalert_{node}/show_garden/config",
          "homeassistant/button/camalert_{node}/mosaic/config",
          "homeassistant/button/camalert_other/show_old_camera/config"]


def run_cleanup(client_class, discovery, expect):
    """#116: the broker holds retained discovery configs before the player connects; returns the topics the player
    cleared (empty retained payload) and the configs still retained afterwards."""
    with Broker() as b:
        for t in SEEDED:
            b.publish(T.topic(t), json.dumps({"name": "x"}), retain=True)
        cl = client_class(b.port, discovery=discovery)
        cl.start()
        stop = threading.Event()

        def pumping():
            while not stop.is_set():
                cl.pump()
                time.sleep(0.005)
        pump = threading.Thread(target=pumping, daemon=True)
        pump.start()

        def cleared():
            return sorted({m.topic for m in b.messages if m.client != "test" and m.retain and m.payload == b""})
        try:
            b.wait_subscribed()
            wait(lambda: cleared() == sorted(T.topic(t) for t in expect))
            time.sleep(0.5)  # nothing more is removed
        finally:
            cl.stop()
            stop.set()
            pump.join(2)
        return cleared(), sorted(t for t in b.retained if t.startswith("homeassistant/"))


class TestDiscoveryCleanup(unittest.TestCase):
    def test_stale_camera_button_is_removed(self):
        for client in (Enigma2Client, KodiClient):
            cleared, kept = run_cleanup(client, True, [SEEDED[0]])
            self.assertEqual(cleared, [T.topic(SEEDED[0])], client.platform)
            self.assertNotIn(T.topic(SEEDED[0]), kept, client.platform)
            for t in SEEDED[1:]:
                self.assertIn(T.topic(t), kept, client.platform)

    def test_discovery_off_removes_this_player_only(self):
        for client in (Enigma2Client, KodiClient):
            cleared, kept = run_cleanup(client, False, SEEDED[:3])
            self.assertEqual(cleared, sorted(T.topic(t) for t in SEEDED[:3]), client.platform)
            self.assertEqual(kept, [T.topic(SEEDED[3])], client.platform)


if __name__ == "__main__":
    unittest.main()
