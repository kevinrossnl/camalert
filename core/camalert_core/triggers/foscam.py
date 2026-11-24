# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Foscam motion / sound alarms, polled from the cameras in the devices file."""
from . import Trigger, TriggerSource, register
from ..devices.foscam import alarm_edge


@register
class FoscamSource(TriggerSource):
    """Settings: foscam_enabled, foscam_priority, optional foscam_mode / foscam_seconds, foscam_label (text for
    the title, e.g. the translated word 'Motion'; None = no label)."""
    name = "foscam"
    transport = "poll"

    def devices(self, devices):
        """The devices this source polls (Foscam ones)."""
        return {n: d for n, d in devices.items() if d.get("type") == "foscam"}

    def check(self, name, previous, now):
        """Trigger when an alarm starts (not on every poll while it lasts), else None."""
        if not alarm_edge(previous, now):
            return None
        s = self.settings
        return Trigger(name, s.get("foscam_priority") or "normal", "foscam", s.get("foscam_label") or None, None,
                       s.get("foscam_mode") or None, s.get("foscam_seconds") or None)

    @staticmethod
    def poll(device):
        """Alarm state of one camera now (blocking network call; run it in a thread). Raises DeviceError."""
        from ..devices.client import foscam_state
        return foscam_state(device)
