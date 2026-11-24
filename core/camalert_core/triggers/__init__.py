# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Trigger sources (#6): everything that makes a player show a camera without an API call.

A source has a name, a transport and turns its input into a Trigger:

    transport "mqtt"   topics() -> [topic], parse(topic, payload, now) -> Trigger or None     (Frigate)
    transport "poll"   check(name, previous, now) -> Trigger or None, poll(name, device)     (Foscam alarms)
    transport "webhook" parse(path, payload, now)                                              (later: UniFi, ...)

Sources only read a plain settings dict (the same keys on every player, see each source), so Enigma2 and Kodi
use the same code; the player does the network I/O in its own way (Twisted thread, Kodi thread) and calls
Controller.show() with the Trigger.

    for src in enabled_sources(settings, "mqtt"): topics += src.topics()
    trig = dispatch(sources, topic, payload)
"""
REGISTRY = {}


class Trigger(object):
    """What a source wants shown; None fields mean "the player's default"."""
    __slots__ = ("camera", "priority", "source", "label", "event_id", "mode", "seconds")

    def __init__(self, camera, priority="normal", source="api", label=None, event_id=None, mode=None, seconds=None):
        self.camera, self.priority, self.source, self.label = camera, priority, source, label
        self.event_id, self.mode, self.seconds = event_id, mode, seconds

    def show_args(self):
        """Arguments for Controller.show(stream, seconds, mode, priority, source, label, event_id)."""
        return (self.camera, self.seconds, self.mode, self.priority, self.source, self.label, self.event_id)

    def __eq__(self, other):
        return isinstance(other, Trigger) and self.show_args() == other.show_args()

    def __repr__(self):
        return "Trigger%r" % (self.show_args(),)


class TriggerSource(object):
    name = ""
    transport = ""

    def __init__(self, settings):
        self.settings = dict(settings or {})

    def enabled(self):
        return bool(self.settings.get("%s_enabled" % self.name))

    def topics(self):
        return []

    def parse(self, topic, payload, now=0.0):
        return None


def register(cls):
    """Class decorator: makes a source available by its name."""
    REGISTRY[cls.name] = cls
    return cls


def enabled_sources(settings, transport=None):
    """Instances of every registered source that is switched on in settings (optionally of one transport)."""
    out = []
    for name in sorted(REGISTRY):
        src = REGISTRY[name](settings)
        if src.enabled() and (transport is None or src.transport == transport):
            out.append(src)
    return out


def mqtt_topics(sources):
    topics = []
    for s in sources:
        topics += [t for t in s.topics() if t not in topics]
    return topics


def dispatch(sources, topic, payload, now=0.0):
    """(handled, Trigger or None) for an incoming MQTT message: handled = a source owns the topic."""
    for s in sources:
        if topic in s.topics():
            return True, s.parse(topic, payload, now)
    return False, None


from . import foscam, frigate  # noqa: E402,F401  (register the built-in sources)
