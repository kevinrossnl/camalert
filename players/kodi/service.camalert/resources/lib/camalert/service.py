# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Background service: HTTP API, MQTT, Foscam and UniFi Protect pollers and the controller; restarts parts when settings change."""
import json

import xbmc

from . import __version__, kodiapi, mqtt, ptz, server, sources
from .controller import Controller

RESTART_KEYS = {
    "server": ("http_port", "api_https"),
    "mqtt": ("mqtt_enabled", "mqtt_host", "mqtt_port", "mqtt_user", "mqtt_password", "mqtt_discovery", "mqtt_name",
             "frigate_enabled", "frigate_prefix"),
    "ptz": ("foscam_enabled", "unifi_enabled"),
}


def unifi_state():
    """The UniFi Protect poll status for the diagnostics dialog (#71); errors are already redacted."""
    from .camalert_core.triggers.unifi import STATUS
    return {k: getattr(STATUS, k) for k in ("last_poll", "last_ok", "error", "last_event", "consoles")}


def changed_parts(old, new):
    return {part for part, keys in RESTART_KEYS.items() if any(old.get(k) != new.get(k) for k in keys)}


class Service(object):
    def __init__(self):
        kodiapi.migrate_settings()  # before anything reads the settings (#39)
        self.ctl = Controller()
        self.ctl.listeners.append(mqtt.state_changed)
        self.settings = kodiapi.settings()
        self.monitor = kodiapi.Monitor(self.settings_changed)
        self.window_cmd = None

    def configure_log(self, s):
        kodiapi.camlog().configure(s["log_level"], s["log_syslog"])

    def start_all(self):
        self.configure_log(self.settings)
        problem = sources.go2rtc_problem(self.settings)
        if problem:  # #73: no default address; say it once, contact nothing
            kodiapi.log("go2rtc address not set or not valid: no cameras until it is set", "error")
            kodiapi.notify("CamAlert", problem, ms=10000)
        server.start()
        mqtt.start(self.ctl)
        ptz.start(self.ctl)

    def settings_changed(self):
        new = kodiapi.settings()
        parts = changed_parts(self.settings, new)
        dnd_changed = new["dnd"] != self.settings["dnd"]
        self.settings = new
        self.configure_log(new)
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
            self.ctl.show(c.get("cam"), None, None, "high", "menu")
        elif what == "mosaic":
            self.ctl.mosaic(None, 60)
        elif what == "tour":
            self.ctl.tour()
        elif what == "hide":
            self.ctl.hide()
        elif what == "state":  # for the diagnostics and event list dialogs (they run in another interpreter)
            from xbmcgui import Window
            from . import mqtt
            Window(10000).setProperty("camalert.state", json.dumps({
                "events": self.ctl.events, "last_caller": self.ctl.last_caller, "mqtt": mqtt.connected(),
                "log": kodiapi.camlog().path, "time": c.get("time"), "unifi": unifi_state()}))
        elif what == "play":
            self.ctl.play_clip(c.get("url"), c.get("title"))

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
