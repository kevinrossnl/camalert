# CamAlert - camera devices: Foscam alarm state and PTZ via ONVIF or Foscam CGI.
# Copyright (C) 2026 CamAlert developers. GPL v2.
# Plain Python (no Enigma2 imports): blocking calls, run them in a thread. Never log urls or passwords.
import os
import time
import urllib.error
import urllib.request

from .config import DEVICES_FILE, PTZ_VECTORS, device_base, parse_devices
from .foscam import foscam_alarm, foscam_ptz, foscam_url
from .onvif import (onvif_body, onvif_created, onvif_envelope, onvif_fault, onvif_profile_token, onvif_time,
                    onvif_xaddrs)

TIMEOUT = 4
MOVE_SECONDS = 0.5


class DeviceError(Exception):
    pass


def load_devices(path=DEVICES_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return parse_devices(f.read())
    except OSError:
        return {}


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # the url contains the password: never put it in the message
        raise DeviceError("camera not reachable (%s)" % type(e).__name__)


def foscam_state(dev):
    """True if the camera reports a motion or sound alarm right now."""
    return foscam_alarm(_get(foscam_url(dev, "getDevState")))


def foscam_command(dev, cmd):
    xml = _get(foscam_url(dev, cmd))
    if "<result>0</result>" not in xml:
        raise DeviceError("Foscam %s refused" % cmd)


class Onvif(object):
    """Minimal ONVIF PTZ client: finds the media/PTZ service and profile once, corrects for the camera clock."""

    def __init__(self, dev):
        self.dev = dev
        self.device_url = device_base(dev) + "/onvif/device_service"
        self.offset = 0
        self.xaddrs = None
        self.token = None

    def call(self, url, action, auth=True, **kw):
        body = onvif_body(action, **kw)
        if auth and self.dev.get("user"):
            env = onvif_envelope(body, self.dev["user"], self.dev.get("password", ""), os.urandom(16),
                                 onvif_created(time.time() + self.offset))
        else:
            env = onvif_envelope(body)
        req = urllib.request.Request(url, data=env.encode("utf-8"),
                                     headers={"Content-Type": 'application/soap+xml; charset=utf-8'})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                xml = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            xml = e.read().decode("utf-8", "replace")
            raise DeviceError("ONVIF %s: %s" % (action, onvif_fault(xml) or e.code))
        except Exception as e:
            raise DeviceError("ONVIF %s: camera not reachable (%s)" % (action, type(e).__name__))
        fault = onvif_fault(xml)
        if fault:
            raise DeviceError("ONVIF %s: %s" % (action, fault))
        return xml

    def prepare(self):
        if self.token:
            return
        try:
            t = onvif_time(self.call(self.device_url, "GetSystemDateAndTime", auth=False))
            if t:
                self.offset = t - time.time()
        except DeviceError:
            pass
        self.xaddrs = onvif_xaddrs(self.call(self.device_url, "GetCapabilities"))
        if "ptz" not in self.xaddrs:
            raise DeviceError("camera has no ONVIF PTZ service")
        self.token = onvif_profile_token(self.call(self.xaddrs.get("media", self.device_url), "GetProfiles"))
        if not self.token:
            raise DeviceError("no ONVIF media profile")

    def ptz(self, action, seconds=MOVE_SECONDS):
        self.prepare()
        url = self.xaddrs["ptz"]
        if action == "home":
            self.call(url, "GotoHomePosition", token=self.token)
        elif action == "stop":
            self.call(url, "Stop", token=self.token)
        else:
            self.call(url, "ContinuousMove", token=self.token, vector=PTZ_VECTORS[action])
            time.sleep(seconds)
            self.call(url, "Stop", token=self.token)


_onvif = {}


def ptz(dev, action, seconds=MOVE_SECONDS):
    """Moves the camera for `seconds` and stops (blocking). Raises DeviceError."""
    if dev["type"] == "foscam":
        start, stop = foscam_ptz(action)
        foscam_command(dev, start)
        if stop:
            time.sleep(seconds)
            foscam_command(dev, stop)
        return
    key = (dev["host"], dev["port"], dev.get("user"), dev.get("password"))
    client = _onvif.get(key)
    if client is None:
        client = _onvif[key] = Onvif(dev)
    try:
        client.ptz(action, seconds)
    except DeviceError:
        _onvif.pop(key, None)  # find services/profile again next time
        raise
