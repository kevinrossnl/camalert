# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""UniFi Protect events (#9), polled from the consoles in the devices file (type unifi), without Home Assistant.

The players (#70 Enigma2, #71 Kodi) run poll() in a thread every unifi_interval seconds, call check() with the
previous and the new answer and keep STATUS up to date for the diagnostics screen (status_lines()).
"""
import time as _time

from . import Trigger, TriggerSource, register
from ..devices import unifi
from ..i18n import N_
from ..obs.log import redact

ORDER = {k: i for i, k in enumerate(unifi.KINDS)}  # ring first, motion last
# label of each kind in the title and the event list (translated by the player, see labels())
KIND_LABELS = {"ring": N_("Doorbell"), "person": N_("Person"), "vehicle": N_("Vehicle"), "animal": N_("Animal"),
               "package": N_("Package"), "motion": N_("Motion")}


def labels(tr):
    """{kind: translated label} for the setting unifi_labels."""
    return {k: tr(v) for k, v in KIND_LABELS.items()}


@register
class UnifiSource(TriggerSource):
    """Settings: unifi_enabled, unifi_kinds ('ring,person,vehicle,animal,package,motion'; default ring,person),
    unifi_cameras (map 'protect_name=go2rtc_name|...'), unifi_priority (a ring is always at least high),
    optional unifi_mode ('log' = event list and log only) / unifi_seconds, unifi_rules (per kind
    'kind=priority/mode/camera|...', see devices.unifi.kind_rules), unifi_camera_rules (per camera
    'camera=priority/mode/seconds|...', wins over unifi_rules, see devices.unifi.camera_rules), unifi_labels ({kind: text} for the title,
    see labels()) or unifi_label (one text for every kind; None = no label)."""
    name = "unifi"
    transport = "poll"

    def devices(self, devices):
        """The devices this source polls (UniFi Protect consoles)."""
        return {n: d for n, d in devices.items() if d.get("type") == "unifi"}

    def check(self, name, previous, now):
        """Trigger for the most important new event since the previous poll, else None. The first poll after a
        start only remembers what is there (no old events on screen)."""
        if not previous or not now:
            return None
        seen = set(e.get("id") for e in previous.get("events") or [])
        kinds = unifi.wanted_kinds(self.settings.get("unifi_kinds"))
        names = unifi.camera_map(self.settings.get("unifi_cameras"))
        best = None
        for ev in now.get("events") or []:
            if ev.get("id") in seen:
                continue
            hit = unifi.match(ev, now.get("cams") or {}, kinds, names)
            if hit and (best is None or ORDER[hit[1]] < ORDER[best[1][1]]):
                best = (ev, hit)
        if best is None:
            return None
        ev, (camera, kind) = best
        s = self.settings
        rule_prio, rule_mode, rule_cam = unifi.kind_rules(s.get("unifi_rules")).get(kind, (None, None, None))
        cam_prio, cam_mode, cam_secs = unifi.camera_rules(s.get("unifi_camera_rules")).get(
            unifi.slug(camera), (None, None, None))
        # per camera first, then per event type, then the general settings (#9)
        priority = cam_prio or rule_prio or s.get("unifi_priority") or "normal"
        if kind == "ring" and priority == "normal":
            priority = "high"
        label = (s.get("unifi_labels") or {}).get(kind) or s.get("unifi_label") or None
        return Trigger(rule_cam or camera, priority, "unifi", label, None,
                       cam_mode or rule_mode or s.get("unifi_mode") or None,
                       cam_secs or s.get("unifi_seconds") or None)

    @staticmethod
    def poll(device):
        """Events of the last minute on one console (blocking network call; run it in a thread). Raises
        DeviceError."""
        from ..devices.client import protect_state
        return protect_state(device)


class PollStatus(object):
    """What the diagnostics screen shows about the UniFi Protect source: last check, last event, last error.
    Errors are stored redacted (never a password, token or cookie)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.last_poll = self.last_ok = self.error = self.last_event = None
        self.consoles = 0

    def ok(self, now=None):
        self.last_poll = self.last_ok = _time.time() if now is None else now
        self.error = None

    def failed(self, error, now=None):
        """Remembers an error; True when it is new (log it once, not at every poll)."""
        self.last_poll = _time.time() if now is None else now
        text = redact(str(error))[:200]
        new = text != self.error
        self.error = text
        return new

    def event(self, trig, now=None):
        self.last_event = {"time": _time.time() if now is None else now, "camera": trig.camera,
                           "label": trig.label, "priority": trig.priority, "mode": trig.mode}

    def lines(self, tr, when):
        """[(ok True/False/None, text)] for the diagnostics; when(ts) formats a time."""
        if not self.consoles:
            return [(False, tr(N_("UniFi Protect: no console of type unifi in the devices file")))]
        if self.last_poll is None:
            return [(None, tr(N_("UniFi Protect: not checked yet")))]
        out = []
        if self.error:
            out.append((False, tr(N_("UniFi Protect: %s")) % self.error))
        if self.last_ok:
            out.append((True, tr(N_("UniFi Protect: last check %s")) % when(self.last_ok)))
        e = self.last_event
        if e:
            what = e["camera"] + (" (%s)" % e["label"] if e["label"] else "")
            mode = " [%s]" % tr(N_("Log only")) if e["mode"] == "log" else ""
            out.append((True, tr(N_("UniFi Protect: last event %s, %s")) % (when(e["time"]), what) + mode))
        else:
            out.append((None, tr(N_("UniFi Protect: no event since the start"))))
        return out


STATUS = PollStatus()  # one per player process
