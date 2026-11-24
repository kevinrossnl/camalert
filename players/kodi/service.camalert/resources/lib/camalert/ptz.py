# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Camera control (PTZ via ONVIF or Foscam CGI), the Foscam motion/sound poller and the UniFi Protect poller (#71),
using the shared devices.py. devices.conf (add-on data folder), one line per camera or console:
name|onvif|host:port|user|password, name|foscam|..., name|unifi|host:443|user|password. Credentials are never logged."""
import os
import queue
import threading
import time

from . import kodiapi
from .camalert_core.devices import client as devices
from .klogic import with_default_login
from .camalert_core.triggers.foscam import FoscamSource
from .camalert_core.triggers.unifi import STATUS as UNIFI_STATUS, UnifiSource, labels as unifi_labels

EXAMPLE = """# CamAlert camera control (PTZ), Foscam alarms and UniFi Protect events. One camera per line:
#   name|type|host:port|user|password
# name = CamAlert camera name, type = onvif, foscam or unifi (a UniFi Protect console, View Only user).
# Empty user/password = the add-on settings (not for unifi).
# front_door|onvif|192.0.2.10:80|admin|secret
# garden|foscam|192.0.2.11:88|admin|secret
# protect|unifi|192.0.2.1:443|camalert|secret
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
    """Every line of devices.conf; cameras get the add-on's default login, UniFi consoles never (#71)."""
    s = s or kodiapi.settings()
    devs = devices.load_devices(device_file())
    out = with_default_login({n: d for n, d in devs.items() if d.get("type") != "unifi"}, s["ptz_user"],
                             s["ptz_password"])
    out.update((n, d) for n, d in devs.items() if d.get("type") == "unifi")
    return out


def ptz_devices(s=None):
    """Devices with camera control: UniFi Protect consoles are not cameras (#71)."""
    return {n: d for n, d in all_devices(s).items() if d.get("type") != "unifi"}


class Ptz(object):
    """Camera control for one camera; key presses are queued and run one after the other in a thread."""

    def __init__(self, name):
        self.name = name
        self.dev = ptz_devices().get(name)
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
            source = FoscamSource(s)  # (#6) Kodi shows no label; Enigma2 shows "Motion" (#39)
            for name, d in source.devices(all_devices(s)).items():
                if self.stopping.is_set():
                    continue
                try:
                    now = source.poll(d)
                except Exception as e:
                    kodiapi.log("Foscam %s: %s" % (name, e))
                    continue
                trig = source.check(name, self.state.get(name), now)
                if trig:
                    kodiapi.log("Foscam alarm on %s" % name)
                    self.ctl.show(*trig.show_args())
                self.state[name] = now
            self.stopping.wait(s["foscam_interval"])

    def stop(self):
        self.stopping.set()


def unifi_interval(s):
    """UniFi Protect check interval in seconds (2-60, default 5)."""
    try:
        return max(2, min(60, int(s.get("unifi_interval"))))
    except (TypeError, ValueError):
        return 5


class UnifiPoller(threading.Thread):
    """UniFi Protect consoles in devices.conf (#71): one poll per console every unifi_interval seconds in this
    thread (never in Kodi's GUI thread). The first answer after a start or an error only sets the baseline (no old
    events on screen); errors are logged once (redacted) and shown in the diagnostics (UNIFI_STATUS)."""

    def __init__(self, ctl):
        threading.Thread.__init__(self, name="camalert-unifi", daemon=True)
        self.ctl = ctl
        self.stopping = threading.Event()
        self.state = {}  # console name -> last answer, None = first poll / after an error

    def settings(self):
        s = dict(kodiapi.settings())
        s["unifi_labels"] = unifi_labels(kodiapi.core_tr())
        return s

    def once(self):
        s = self.settings()
        source = UnifiSource(s)
        if not s.get("enabled", True) or not source.enabled():
            self.state = {}
            UNIFI_STATUS.reset()
            return s
        devices.secure_file(device_file())  # it holds the console password: owner only (0600)
        consoles = source.devices(all_devices(s))
        UNIFI_STATUS.consoles = len(consoles)
        for name, dev in sorted(consoles.items()):
            if self.stopping.is_set():
                break
            if name not in self.state:
                kodiapi.log("UniFi Protect: polling console %s every %d s" % (name, unifi_interval(s)))
            previous = self.state.get(name)
            try:
                now = source.poll(dev)
            except Exception as e:  # DeviceError messages never contain passwords; redacted anyway
                self.state[name] = None
                if UNIFI_STATUS.failed(e):
                    kodiapi.log("UniFi Protect %s: %s" % (name, UNIFI_STATUS.error), "error")
                continue
            if self.stopping.is_set():  # switched off meanwhile: drop the late answer
                break
            self.state[name] = now
            UNIFI_STATUS.ok()
            trig = source.check(name, previous, now)
            if trig:
                UNIFI_STATUS.event(trig)
                self.ctl.show(*trig.show_args())
        return s

    def run(self):
        while not self.stopping.is_set():
            try:
                s = self.once()
            except Exception as e:  # never let the poller die silently
                kodiapi.log("UniFi Protect: %s" % e, "error")
                s = {}
            self.stopping.wait(unifi_interval(s))

    def stop(self):
        self.stopping.set()


_poller = None
_unifi = None


def start(ctl):
    global _poller, _unifi
    stop()
    s = kodiapi.settings()
    if s["foscam_enabled"]:
        _poller = FoscamPoller(ctl)
        _poller.start()
    if s["unifi_enabled"]:
        _unifi = UnifiPoller(ctl)
        _unifi.start()


def stop():
    global _poller, _unifi
    if _poller is not None:
        _poller.stop()
        _poller = None
    if _unifi is not None:
        _unifi.stop()
        _unifi = None
        kodiapi.log("UniFi Protect: stopped")
    UNIFI_STATUS.reset()
