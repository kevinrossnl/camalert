# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Background service: HTTP API, MQTT, Foscam poller and the controller; restarts parts when settings change."""
import json

import xbmc

from . import __version__, kodiapi, mqtt, ptz, server
from .controller import Controller

RESTART_KEYS = {
    "server": ("http_port", "api_https"),
    "mqtt": ("mqtt_enabled", "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password", "mqtt_discovery", "mqtt_name",
             "frigate_enabled", "frigate_prefix"),
    "ptz": ("foscam_enabled",),
}


def changed_parts(old, new):
    return {part for part, keys in RESTART_KEYS.items() if any(old.get(k) != new.get(k) for k in keys)}


class Service(object):
    def __init__(self):
        self.ctl = Controller()
        self.ctl.listeners.append(mqtt.state_changed)
        self.settings = kodiapi.settings()
        self.monitor = kodiapi.Monitor(self.settings_changed)
        self.window_cmd = None

    def start_all(self):
        server.start()
        mqtt.start(self.ctl)
        ptz.start(self.ctl)

    def settings_changed(self):
        new = kodiapi.settings()
        parts = changed_parts(self.settings, new)
        dnd_changed = new["dnd"] != self.settings["dnd"]
        self.settings = new
        if "server" in parts:
            server.start()
        if "mqtt" in parts:
            mqtt.start(self.ctl)
        elif dnd_changed:
            mqtt.state_changed()
        if "ptz" in parts:
            ptz.start(self.ctl)
        if not new["enabled"]:
            self.ctl.hide()

    def script_commands(self):
        """Settings buttons (default.py) hand commands over via a window property."""
        from xbmcgui import Window
        w = Window(10000)
        cmd = w.getProperty("camalert.cmd")
        if not cmd:
            return
        w.clearProperty("camalert.cmd")
        try:
            c = json.loads(cmd)
        except ValueError:
            return
        what = c.get("do")
        if what == "show":
            self.ctl.show(c.get("cam"), None, None, "high")
        elif what == "mosaic":
            self.ctl.mosaic(None, 60)
        elif what == "tour":
            self.ctl.tour()
        elif what == "hide":
            self.ctl.hide()

    def run(self):
        kodiapi.log("version %s starting" % __version__)
        self.start_all()
        while not self.monitor.abortRequested():
            if self.monitor.waitForAbort(0.5):
                break
            self.script_commands()
        kodiapi.log("stopping")
        ptz.stop()
        mqtt.stop()
        server.stop()
        self.ctl.shutdown()


def run():
    Service().run()
