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
from .camalert_core.mqtt.topics import discovery, mqtt_command
from .camalert_core.rules import clamp_seconds
from .camalert_core.triggers.frigate import frigate_event, frigate_stream, frigate_title
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


def frigate_topic(prefix):
    return "%s/events" % ((prefix or "frigate").strip().strip("/") or "frigate")


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
        if s["frigate_enabled"]:
            topics.append(frigate_topic(s["frigate_prefix"]))
        self.send(mqtt_subscribe(1, topics))
        self.publish("availability", "online", retain=True)
        self.publish_state()
        if s["mqtt_discovery"]:
            threading.Thread(target=self.announce, daemon=True).start()

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
            if s["frigate_enabled"] and topic == frigate_topic(s["frigate_prefix"]):
                self.frigate(payload, s)
                return
            action = topic[len(self.prefix):] if topic.startswith(self.prefix) else ""
            if action == "hide":
                self.ctl.hide()
            elif action == "mosaic":
                self.ctl.mosaic(payload.decode("utf-8", "replace").strip() or None, 60)
            elif action == "show":
                cmd = mqtt_command(payload)
                sec = clamp_seconds(cmd.get("sec")) if cmd.get("sec") else None
                self.ctl.show(cmd.get("cam"), sec, cmd.get("mode"), cmd.get("priority"), "mqtt", cmd.get("label"))
            elif action == "dnd/set":
                self.ctl.set_dnd(payload.decode("utf-8", "replace").strip().upper() in ("ON", "1", "TRUE"))
        except Exception as e:
            kodiapi.log("MQTT command failed: %s" % e)
        time.sleep(0.5)
        self.publish_state()

    def frigate(self, payload, s):
        event = frigate_event(payload)
        stream = frigate_stream(event, s["frigate_labels"], s["frigate_map"])
        if not stream:
            return
        now = time.time()
        if now - self.frigate_seen.get(stream, 0) < 5:  # 'update' events come in bursts
            return
        self.frigate_seen[stream] = now
        kodiapi.log("Frigate detection on %s" % stream)
        self.ctl.show(stream, s["frigate_seconds"], s["frigate_mode"], s["frigate_priority"], "frigate",
                      frigate_title(event), event["id"])

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
