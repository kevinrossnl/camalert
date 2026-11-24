# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""UniFi Protect events (#9), polled from the consoles in the devices file (type unifi), without Home Assistant."""
from . import Trigger, TriggerSource, register
from ..devices import unifi

ORDER = {k: i for i, k in enumerate(unifi.KINDS)}  # ring first, motion last


@register
class UnifiSource(TriggerSource):
    """Settings: unifi_enabled, unifi_kinds ('ring,person,vehicle,animal,package,motion'; default ring,person),
    unifi_cameras (map 'protect_name=go2rtc_name|...'), unifi_priority (a ring is always at least high),
    optional unifi_mode / unifi_seconds, unifi_label (text for the title; None = no label)."""
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
        priority = s.get("unifi_priority") or "normal"
        if kind == "ring" and priority == "normal":
            priority = "high"
        return Trigger(camera, priority, "unifi", s.get("unifi_label") or None, None,
                       s.get("unifi_mode") or None, s.get("unifi_seconds") or None)

    @staticmethod
    def poll(device):
        """Events of the last minute on one console (blocking network call; run it in a thread). Raises
        DeviceError."""
        from ..devices.client import protect_state
        return protect_state(device)
