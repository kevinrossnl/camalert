# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Minimal MQTT client (3.1.1, QoS 0) with Home Assistant discovery.

Topics (node = receiver id):
    camalert/<node>/show      payload: camera name, or JSON {"cam": ..., "sec": ..., "mode": ..., "priority": ...}
    camalert/<node>/mosaic    payload: empty or "cam1,cam2,..."
    camalert/<node>/hide
    camalert/<node>/state     published: camera on screen, or "none"
    camalert/<node>/availability  online / offline (retained, last will)
"""
import socket

from twisted.internet import reactor, task, threads
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from Components.config import config

from .display import Controller, all_camera_names, camera_urls, log, trigger_settings
from .camalert_core.cameras import slug
from .camalert_core.keymap import button_event
from .camalert_core.mqtt.codec import (mqtt_connect, MQTT_DISCONNECT, mqtt_parse_publish, MQTT_PING, mqtt_publish,
                                       mqtt_split, mqtt_subscribe)
from .camalert_core.mqtt.topics import discovery, mqtt_command
from .camalert_core.rules import clamp_seconds
from .camalert_core.triggers import dispatch, enabled_sources, mqtt_topics
from .camalert_core.urls import valid_port

_connector = None
_factory = None


def node_id():
    """Stable id of this receiver: MAC address of the first network card, else the host name."""
    for dev in ("eth0", "wlan0"):
        try:
            with open("/sys/class/net/%s/address" % dev) as f:
                mac = f.read().strip().replace(":", "")
                if mac and mac != "000000000000":
                    return mac
        except OSError:
            pass
    return slug(socket.gethostname()) or "receiver"


def node_name():
    c = config.plugins.camalert
    return c.mqtt_name.value.strip() or "CamAlert %s" % socket.gethostname()


class CamAlertMqtt(Protocol):
    def __init__(self):
        self.buffer = b""
        self.node = node_id()
        self.prefix = "camalert/%s/" % self.node
        self.pinger = None

    def connectionMade(self):
        c = config.plugins.camalert
        self.transport.write(mqtt_connect("camalert-" + self.node, c.mqtt_user.value or None,
                                          c.mqtt_password.value or None, self.prefix + "availability"))

    def dataReceived(self, data):
        packets, self.buffer = mqtt_split(self.buffer + data)
        for kind, flags, body in packets:
            if kind == 2:  # CONNACK
                if len(body) > 1 and body[1] != 0:
                    log("MQTT connection refused, code", body[1])
                    self.transport.loseConnection()
                    return
                self.connected_ok()
            elif kind == 3:  # PUBLISH
                topic, payload = mqtt_parse_publish(flags, body)
                self.command(topic, payload)

    def connected_ok(self):
        log("MQTT connected as", self.node)
        _factory.resetDelay()
        _factory.protocol_instance = self
        topics = [self.prefix + "show", self.prefix + "mosaic", self.prefix + "hide", self.prefix + "dnd/set"]
        c = config.plugins.camalert
        topics += mqtt_topics(enabled_sources(trigger_settings(), "mqtt"))  # Frigate etc. (#6)
        self.transport.write(mqtt_subscribe(1, topics))
        self.publish("availability", "online", retain=True)
        self.publish_state()
        self.pinger = task.LoopingCall(lambda: self.transport.write(MQTT_PING))
        self.pinger.start(30, now=False)
        if config.plugins.camalert.mqtt_discovery.value:
            announce()

    def connectionLost(self, reason):
        if self.pinger and self.pinger.running:
            self.pinger.stop()
        if _factory is not None and getattr(_factory, "protocol_instance", None) is self:
            _factory.protocol_instance = None

    def publish(self, sub, payload, retain=False):
        self.transport.write(mqtt_publish(self.prefix + sub, payload, retain))

    def publish_raw(self, topic, payload, retain=True):
        self.transport.write(mqtt_publish(topic, payload, retain))

    def publish_state(self):
        st = Controller.instance.status() if Controller.instance else {}
        self.publish("state", st.get("window") or st.get("live") or "none", retain=True)
        self.publish("dnd", "ON" if config.plugins.camalert.dnd.value else "OFF", retain=True)

    def command(self, topic, payload):
        c = config.plugins.camalert
        ctl = Controller.instance
        if not c.enabled.value or ctl is None:
            return
        handled, trig = dispatch(enabled_sources(trigger_settings(), "mqtt"), topic, payload)
        if handled:  # a trigger source (Frigate, ...) owns this topic
            if trig:
                ctl.show(*trig.show_args())
                reactor.callLater(0.5, self.publish_state)
            return
        action = topic.rsplit("/", 1)[-1]
        if topic.endswith("/dnd/set"):
            ctl.set_dnd(payload.decode("utf-8", "replace").strip().upper() in ("ON", "1", "TRUE"))
            reactor.callLater(0.2, self.publish_state)
            return
        try:
            if action == "hide":
                ctl.hide()
            elif action == "mosaic":
                text = payload.decode("utf-8", "replace").strip()
                ctl.mosaic(text or None, 60)
            elif action == "show":
                cmd = mqtt_command(payload)
                sec = clamp_seconds(cmd.get("sec")) if cmd.get("sec") else None
                ctl.show(cmd.get("cam"), sec, cmd.get("mode"), cmd.get("priority"), "mqtt", cmd.get("label"))
        except Exception as e:
            log("MQTT command failed:", e)
        reactor.callLater(0.5, self.publish_state)


class CamAlertMqttFactory(ReconnectingClientFactory):
    protocol = CamAlertMqtt
    maxDelay = 120
    protocol_instance = None

    def clientConnectionFailed(self, connector, reason):
        log("MQTT connection failed:", reason.getErrorMessage())
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def clientConnectionLost(self, connector, reason):
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)


def announce():
    """(Re)publishes Home Assistant discovery for all cameras (camera list may need the network: thread)."""
    def names():
        result = []
        for n in all_camera_names():
            urls = camera_urls(n)
            result.append((n, urls[2] if urls else n))
        return result

    def send(cams):
        p = _factory.protocol_instance if _factory else None
        if p is None:
            return
        for topic, payload in discovery(p.node, node_name(), cams):
            p.publish_raw(topic, payload)
        log("MQTT discovery sent for", len(cams), "cameras")

    threads.deferToThread(names).addCallbacks(send, lambda e: log("MQTT discovery failed:", e.getErrorMessage()))


def state_changed():
    p = _factory.protocol_instance if _factory else None
    if p is not None:
        p.publish_state()


def publish_button(camera, button):
    p = _factory.protocol_instance if _factory else None
    if p is not None:
        p.publish("button", button_event(node_id(), camera, button))


def connected():
    return bool(_factory and _factory.protocol_instance)


def start():
    global _connector, _factory
    stop()
    c = config.plugins.camalert
    if not c.mqtt_enabled.value or not c.mqtt_host.value.strip():
        return
    _factory = CamAlertMqttFactory()
    _connector = reactor.connectTCP(c.mqtt_host.value.strip(), valid_port(c.mqtt_port.value, 1883), _factory, timeout=10)


def stop():
    global _connector, _factory
    if _factory is not None:
        _factory.stopTrying()
        p = _factory.protocol_instance
        if p is not None:
            try:
                p.publish("availability", "offline", retain=True)
                p.transport.write(MQTT_DISCONNECT)
            except Exception:
                pass
    if _connector is not None:
        _connector.disconnect()
    _connector = _factory = None
