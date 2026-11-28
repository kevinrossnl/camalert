# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""MQTT client (3.1.1, QoS 0) with Home Assistant discovery and the Frigate trigger; same topics as Enigma2:

    camalert/<node>/show | mosaic | hide | dnd/set     commands
    camalert/<node>/state | dnd | availability         published (retained)
    <frigate prefix>/events                            Frigate detections (optional)
"""
import json
import socket
import threading
import time

from . import kodiapi, sources
from .camalert_core.keymap import button_event
from .camalert_core.mqtt.codec import (mqtt_connect, MQTT_DISCONNECT, mqtt_parse_publish, MQTT_PING, mqtt_publish,
                                       mqtt_split, mqtt_subscribe)
from .camalert_core.mqtt.topics import discovery, discovery_filter, DiscoveryCleaner, mqtt_command, mqtt_hide
from .camalert_core.rules import has_seconds, show_seconds
from .camalert_core.triggers import dispatch, enabled_sources, mqtt_topics
from .camalert_core.urls import valid_port
from .server import node_id, node_name

_client = None


def kodi_discovery(node, name, cams):
    """Discovery of the shared logic, with model 'Kodi'."""
    out = []
    for topic, payload in discovery(node, name, cams):
        d = json.loads(payload)
        d["device"]["model"] = "Kodi"
        out.append((topic, json.dumps(d, sort_keys=True)))
    return out


def trigger_settings(s):
    """Settings of the trigger sources (#6): the Kodi settings already use their keys; Frigate 'update' events
    come in bursts, so Kodi ignores repeats within 5 seconds."""
    return dict(s, frigate_debounce=5)


class Client(threading.Thread):
    def __init__(self, ctl):
        threading.Thread.__init__(self, name="camalert-mqtt", daemon=True)
        self.ctl = ctl
        self.node = node_id()
        self.prefix = "camalert/%s/" % self.node
        self.sock = None
        self.wlock = threading.Lock()
        self.stopping = threading.Event()
        self.frigate_seen = {}
        self.up = False
        self.cleaner = DiscoveryCleaner(self.node)

    # --- io --------------------------------------------------------------------------------------------------
    def send(self, data):
        with self.wlock:
            if self.sock is not None:
                try:
                    self.sock.sendall(data)
                except OSError:
                    pass

    def publish(self, sub, payload, retain=False):
        self.send(mqtt_publish(self.prefix + sub, payload, retain))

    def run(self):
        delay = 2
        while not self.stopping.is_set():
            s = kodiapi.settings()
            try:
                self.session(s)
                delay = 2
            except (OSError, ValueError) as e:
                kodiapi.log("MQTT connection failed: %s" % e)
            self.up = False
            with self.wlock:
                if self.sock is not None:
                    try:
                        self.sock.close()
                    except OSError:
                        pass
                    self.sock = None
            self.stopping.wait(delay)
            delay = min(120, delay * 2)

    def session(self, s):
        sock = socket.create_connection((s["mqtt_host"].strip(), valid_port(s["mqtt_port"], 1883)), timeout=10)
        sock.settimeout(1)
        with self.wlock:
            self.sock = sock
        self.send(mqtt_connect("camalert-" + self.node, s["mqtt_user"] or None, s["mqtt_password"] or None,
                               self.prefix + "availability"))
        buf, last_ping = b"", time.time()
        while not self.stopping.is_set():
            try:
                data = sock.recv(4096)
                if not data:
                    raise OSError("closed by broker")
                packets, buf = mqtt_split(buf + data)
                for kind, flags, body in packets:
                    if kind == 2:
                        if len(body) > 1 and body[1] != 0:
                            raise OSError("refused, code %d" % body[1])
                        self.connected(s)
                    elif kind == 3:
                        topic, payload = mqtt_parse_publish(flags, body)
                        if self.cleaner.ours(topic):  # a retained discovery config of this player (#116)
                            self.clear(self.cleaner.seen(topic, payload))
                            continue
                        threading.Thread(target=self.command, args=(topic, payload), daemon=True).start()
            except socket.timeout:
                pass
            if time.time() - last_ping > 30:
                self.send(MQTT_PING)
                last_ping = time.time()

    def connected(self, s):
        self.up = True
        kodiapi.log("MQTT connected as %s" % self.node)
        topics = [self.prefix + t for t in ("show", "mosaic", "hide", "dnd/set")]
        topics += mqtt_topics(enabled_sources(trigger_settings(s), "mqtt"))  # Frigate etc. (#6)
        self.cleaner = DiscoveryCleaner(self.node)
        if not s["mqtt_discovery"]:
            self.cleaner.disabled()  # every discovery config of this player goes (#116)
        topics.append(discovery_filter(self.node))
        self.send(mqtt_subscribe(1, topics))
        self.publish("availability", "online", retain=True)
        self.publish_state()
        if s["mqtt_discovery"]:
            threading.Thread(target=self.announce, daemon=True).start()

    def clear(self, topics):
        """Removes stale Home Assistant discovery configs: an empty retained payload (#116)."""
        for topic in topics:
            self.send(mqtt_publish(topic, b"", True))
            kodiapi.log("MQTT discovery removed %s" % topic)

    def announce(self):
        s = kodiapi.settings()
        try:
            cams = []
            for n in sources.all_camera_names(s):
                u = sources.camera_urls(n, s)
                cams.append((n, u[2] if u else n))
        except Exception as e:
            kodiapi.log("MQTT discovery failed: %s" % e)
            return
        self.clear(self.cleaner.known([n for n, _t in cams]))
        for topic, payload in kodi_discovery(self.node, node_name(s), cams):
            self.send(mqtt_publish(topic, payload, True))
        kodiapi.log("MQTT discovery sent for %d cameras" % len(cams))

    def publish_state(self):
        st = self.ctl.status() if self.ctl else {}
        self.publish("state", st.get("window") or st.get("live") or "none", retain=True)
        self.publish("dnd", "ON" if st.get("dnd") else "OFF", retain=True)

    def command(self, topic, payload):
        s = kodiapi.settings()
        if not s["enabled"] or self.ctl is None:
            return
        try:
            sources = enabled_sources(trigger_settings(s), "mqtt")
            for src in sources:
                if hasattr(src, "seen"):
                    src.seen = self.frigate_seen  # keep the debounce state between messages
            handled, trig = dispatch(sources, topic, payload, time.time())
            if handled:
                if trig:
                    kodiapi.log("%s detection on %s" % (trig.source.capitalize(), trig.camera))
                    self.ctl.show(*trig.show_args())
                return
            action = topic[len(self.prefix):] if topic.startswith(self.prefix) else ""
            if action == "hide":
                wid = mqtt_hide(payload)  # #87: {"id": ...} closes only that window
                self.ctl.hide(window_id=wid) if wid else self.ctl.hide()
            elif action == "mosaic":
                self.ctl.mosaic(payload.decode("utf-8", "replace").strip() or None, 60)
            elif action == "show":
                cmd = mqtt_command(payload)
                sec = show_seconds(cmd.get("sec")) if has_seconds(cmd.get("sec")) else None  # 0: until hide (#81)
                extra = {"window_id": cmd["id"]} if cmd.get("id") else {}  # #87
                self.ctl.show(cmd.get("cam"), sec, cmd.get("mode"), cmd.get("priority"), "mqtt", cmd.get("label"),
                              **extra)
            elif action == "dnd/set":
                self.ctl.set_dnd(payload.decode("utf-8", "replace").strip().upper() in ("ON", "1", "TRUE"))
        except Exception as e:
            kodiapi.log("MQTT command failed: %s" % e)
        time.sleep(0.5)
        self.publish_state()

    def stop(self):
        self.stopping.set()
        self.publish("availability", "offline", retain=True)
        self.send(MQTT_DISCONNECT)


def connected():
    return bool(_client is not None and _client.up)


def publish_button(camera, button):
    """camalert/<id>/button: Home Assistant event entity (from discovery)."""
    if _client is not None and _client.up:
        _client.publish("button", button_event(_client.node, camera, button))


def state_changed():
    if _client is not None:
        _client.publish_state()


def start(ctl):
    global _client
    stop()
    s = kodiapi.settings()
    if not s["mqtt_enabled"] or not s["mqtt_host"].strip():
        return
    _client = Client(ctl)
    _client.start()


def stop():
    global _client
    if _client is not None:
        _client.stop()
        _client = None
