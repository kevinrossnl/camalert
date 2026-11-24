# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Camera control (PTZ via ONVIF or Foscam CGI) and the Foscam motion/sound poller, using the shared devices.py.
devices.conf (add-on data folder), one camera per line:  name|onvif|host:port|user|password  or  name|foscam|...
Credentials are never logged."""
import os
import queue
import threading
import time

from . import devices, kodiapi
from .klogic import with_default_login
from .logic import alarm_edge

EXAMPLE = """# CamAlert camera control (PTZ) and Foscam alarms. One camera per line:
#   name|type|host:port|user|password
# name = CamAlert camera name, type = onvif or foscam. Empty user/password = the add-on settings.
# front_door|onvif|192.0.2.10:80|admin|secret
# garden|foscam|192.0.2.11:88|admin|secret
"""


def device_file():
    return os.path.join(kodiapi.profile_dir(), "devices.conf")


def ensure_example():
    p = device_file()
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(EXAMPLE)
        os.chmod(p, 0o600)
    return p


def all_devices(s=None):
    s = s or kodiapi.settings()
    return with_default_login(devices.load_devices(device_file()), s["ptz_user"], s["ptz_password"])


class Ptz(object):
    """Camera control for one camera; key presses are queued and run one after the other in a thread."""

    def __init__(self, name):
        self.name = name
        self.dev = all_devices().get(name)
        self.q = queue.Queue()
        self.worker = None

    def available(self):
        return self.dev is not None

    def do(self, action):
        if not self.dev or action not in ("up", "down", "left", "right", "zoom_in", "zoom_out", "home"):
            return
        if self.q.qsize() < 3:
            self.q.put(action)
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._run, daemon=True)
            self.worker.start()

    def _run(self):
        while True:
            try:
                action = self.q.get(timeout=1)
            except queue.Empty:
                return
            try:
                devices.ptz(self.dev, action)
            except Exception as e:  # DeviceError messages never contain urls or passwords
                kodiapi.log("PTZ %s %s: %s" % (self.name, action, e))

    def stop(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break


class FoscamPoller(threading.Thread):
    """Asks every Foscam camera in devices.conf for its alarm state; shows the camera when an alarm starts."""

    def __init__(self, ctl):
        threading.Thread.__init__(self, name="camalert-foscam", daemon=True)
        self.ctl = ctl
        self.stopping = threading.Event()
        self.state = {}

    def run(self):
        while not self.stopping.is_set():
            s = kodiapi.settings()
            for name, d in all_devices(s).items():
                if d["type"] != "foscam" or self.stopping.is_set():
                    continue
                try:
                    now = devices.foscam_state(d)
                except Exception as e:
                    kodiapi.log("Foscam %s: %s" % (name, e))
                    continue
                if alarm_edge(self.state.get(name), now):
                    kodiapi.log("Foscam alarm on %s" % name)
                    self.ctl.show(name, s["foscam_seconds"], s["foscam_mode"], s["foscam_priority"])
                self.state[name] = now
            self.stopping.wait(s["foscam_interval"])

    def stop(self):
        self.stopping.set()


_poller = None


def start(ctl):
    global _poller
    stop()
    if kodiapi.settings()["foscam_enabled"]:
        _poller = FoscamPoller(ctl)
        _poller.start()


def stop():
    global _poller
    if _poller is not None:
        _poller.stop()
        _poller = None
