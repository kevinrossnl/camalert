# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Settings screen: everything a user needs without touching files."""
import os

from enigma import eDVBDB
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Sources.StaticText import StaticText
from Components.config import config, getConfigListEntry
from twisted.internet import threads

from . import _, __version__
from . import server
from . import mqtt
from .display import CAMERA_FILE, Controller, all_camera_names, direct_cameras, open_url
from .logic import (BOUQUET_FILE, add_to_bouquets, bouquet_text, display_name, normalize_server, parse_cams,
                    streams_from_json)

E2 = "/etc/enigma2/"


def fetch_streams(srv):
    with open_url(srv + "/api/streams", timeout=5) as r:
        return streams_from_json(r.read().decode("utf-8", "replace"))


class CamAlertSetup(ConfigListScreen, Screen):
    skin = """<screen name="CamAlertSetup" position="center,center" size="1100,700" title="CamAlert">
        <widget name="config" position="20,20" size="1060,520" itemHeight="40" font="Regular;28" scrollbarMode="showOnDemand" />
        <widget source="help" render="Label" position="20,550" size="1060,80" font="Regular;24" foregroundColor="#aaaaaa" />
        <widget source="key_red" render="Label" position="20,645" size="250,40" backgroundColor="#9f1313" font="Regular;24" halign="center" valign="center" />
        <widget source="key_green" render="Label" position="290,645" size="250,40" backgroundColor="#1f771f" font="Regular;24" halign="center" valign="center" />
        <widget source="key_yellow" render="Label" position="560,645" size="250,40" backgroundColor="#a08000" font="Regular;24" halign="center" valign="center" />
        <widget source="key_blue" render="Label" position="830,645" size="250,40" backgroundColor="#18188b" font="Regular;24" halign="center" valign="center" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle("CamAlert %s" % __version__)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Camera list"))
        self["key_blue"] = StaticText(_("Test"))
        self["help"] = StaticText("")
        ConfigListScreen.__init__(self, [], session=session, on_change=self.build)
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "cancel": self.cancel, "red": self.cancel, "green": self.save, "save": self.save,
            "ok": self.ok, "yellow": self.make_bouquet, "blue": self.test}, -2)
        self.build()
        self.onLayoutFinish.append(self.update_help)
        self["config"].onSelectionChanged.append(self.update_help)

    def build(self):
        c = config.plugins.camalert
        items = [
            (_("Enable CamAlert"), c.enabled, _("Turn the HTTP API and pop-ups on or off.")),
            (_("Cameras via"), c.source, _("go2rtc is recommended. Without go2rtc, list your cameras in %s") % CAMERA_FILE),
        ]
        if c.source.value == "go2rtc":
            items += [
                (_("go2rtc address"), c.server, _("Address of your go2rtc server, e.g. http://192.168.1.10:1984")),
                (_("go2rtc RTSP port"), c.rtsp_port, _("Usually 8554. Used for live view and the camera list.")),
            ]
        if c.source.value == "direct" or c.server.value.strip().lower().startswith("https"):
            items += [(_("Check certificates"), c.verify_ssl,
                       _("Turn off for a self-signed certificate (only in your own network)."))]
        items += [
            (_("Default camera"), c.camera, _("Press OK to choose from the cameras in go2rtc.")),
            (_("Display mode"), c.mode, _("Photo window keeps watching TV; live switches the channel to the camera.")),
            (_("Duration (seconds)"), c.duration, _("How long the camera stays on screen.")),
        ]
        if c.mode.value == "photo":
            items += [(_("Window position"), c.position, ""), (_("Window size"), c.size, ""),
                      (_("Remote control in photo window"), c.window_keys,
                       _("OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too."))]
        if c.mode.value in ("photo", "notify"):
            items += [(_("Pause TV meanwhile"), c.pause_tv,
                       _("Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift."))]
        if c.mode.value == "live":
            items += [(_("Return to previous channel"), c.live_return,
                       _("Switch back to what you were watching when the time is up.")),
                      (_("Volume during live view (%)"), c.live_volume,
                       _("Percentage of the current volume while the camera is shown. 100 = unchanged."))]
        items += [(_("Only between certain times"), c.limit_hours, _("Ignore requests outside the chosen times."))]
        if c.limit_hours.value:
            items += [(_("From"), c.from_time, ""), (_("Until"), c.until_time, _("May pass midnight, e.g. 07:00 to 23:00."))]
        items += [(_("Not during a recording"), c.skip_recording, _("Ignore requests while the receiver is recording.")),
                  (_("Wake receiver on alarm"), c.alarm_wake,
                   _("Requests with priority 'alarm' switch the receiver (and TV via HDMI-CEC) on.")),
                  (_("Tour: seconds per camera"), c.tour_interval, "")]
        items += [
            (_("HTTP port"), c.http_port, _("Port of the CamAlert API on this receiver (default 8099).")),
            (_("Use HTTPS for the API"), c.api_https,
             _("Uses a self-signed certificate; callers must turn off certificate checking.")),
            (_("Allowed callers"), c.allow, _("'Local network only' is recommended.")),
            (_("Access token (optional)"), c.token, _("If set, callers must add ?token=... to every request.")),
            (_("Camera list name"), c.bouquet_name, _("Name of the channel list created with the yellow button.")),
            (_("Mosaic cameras"), c.mosaic, _("Press OK to choose up to 9 cameras for the mosaic. Empty = all.")),
            (_("MQTT (Home Assistant without YAML)"), c.mqtt_enabled,
             _("Connects to your MQTT broker; with discovery the receiver appears in Home Assistant automatically.")),
        ]
        if c.mqtt_enabled.value:
            items += [
                (_("MQTT broker address"), c.mqtt_host, _("IP address or name of the MQTT broker, e.g. 192.168.1.10")),
                (_("MQTT port"), c.mqtt_port, _("Usually 1883.")),
                (_("MQTT user"), c.mqtt_user, ""),
                (_("MQTT password"), c.mqtt_password, ""),
                (_("Home Assistant discovery"), c.mqtt_discovery, _("Creates a device with a button per camera in Home Assistant.")),
                (_("Name in Home Assistant"), c.mqtt_name, _("Empty = CamAlert + the receiver's host name.")),
            ]
        self.help_texts = [i[2] for i in items]
        self["config"].list = [getConfigListEntry(i[0], i[1]) for i in items]

    def update_help(self):
        i = self["config"].getCurrentIndex()
        self["help"].text = self.help_texts[i] if 0 <= i < len(self.help_texts) else ""

    def server(self):
        """Checks the camera source; returns True if cameras can be listed."""
        c = config.plugins.camalert
        if c.source.value == "direct":
            if not direct_cameras():
                self.session.open(MessageBox, _("No cameras found in %s.\nSee the guide for the format.") % CAMERA_FILE,
                                  MessageBox.TYPE_ERROR)
                return False
            return True
        if not normalize_server(c.server.value):
            self.session.open(MessageBox, _("Please enter a valid go2rtc address first."), MessageBox.TYPE_ERROR)
            return False
        return True

    def ok(self):
        if self["config"].getCurrent()[1] is config.plugins.camalert.mosaic:
            if self.server():
                threads.deferToThread(all_camera_names).addCallbacks(self.choose_mosaic, self.fetch_failed)
        elif self["config"].getCurrent()[1] is config.plugins.camalert.camera:
            if self.server():
                threads.deferToThread(all_camera_names).addCallbacks(self.choose_camera, self.fetch_failed)
        else:
            for name in ("keyOK", "keySelect", "keyText"):
                handler = getattr(self, name, None)
                if handler:
                    handler()
                    break

    def fetch_failed(self, err):
        self.session.open(MessageBox, _("Could not reach go2rtc:\n%s") % err.getErrorMessage(), MessageBox.TYPE_ERROR)

    def titles(self):
        if config.plugins.camalert.source.value == "direct":
            return {cam["name"]: cam["title"] for cam in direct_cameras()}
        return {}

    def choose_camera(self, streams):
        if not streams:
            self.session.open(MessageBox, _("go2rtc has no cameras configured."), MessageBox.TYPE_WARNING)
            return
        self.session.openWithCallback(self.camera_chosen, ChoiceBox, title=_("Choose camera"),
                                      list=[(self.titles().get(s, display_name(s)), s) for s in streams])

    def camera_chosen(self, choice):
        if choice:
            config.plugins.camalert.camera.value = choice[1]
            self["config"].invalidateCurrent()

    def choose_mosaic(self, streams):
        self.mosaic_pick = [s for s in parse_cams(config.plugins.camalert.mosaic.value) if s in streams]
        self.mosaic_all = streams
        self.pick_next()

    def pick_next(self):
        rest = [s for s in self.mosaic_all if s not in self.mosaic_pick]
        if not rest or len(self.mosaic_pick) >= 9:
            return self.mosaic_done(None)
        title = _("Choose camera") + " %d/9  (%s)" % (len(self.mosaic_pick) + 1, ", ".join(display_name(s) for s in self.mosaic_pick) or "-")
        choices = [(_("Done"), None)] + [(display_name(s), s) for s in rest]
        if self.mosaic_pick:
            choices.insert(1, (_("Start again"), "__reset"))
        self.session.openWithCallback(self.mosaic_chosen, ChoiceBox, title=title, list=choices)

    def mosaic_chosen(self, choice):
        if choice is None or choice[1] is None:
            return self.mosaic_done(None)
        if choice[1] == "__reset":
            self.mosaic_pick = []
        else:
            self.mosaic_pick.append(choice[1])
        self.pick_next()

    def mosaic_done(self, _unused):
        config.plugins.camalert.mosaic.value = ",".join(self.mosaic_pick)
        self["config"].invalidateCurrent()

    def make_bouquet(self):
        if self.server():
            threads.deferToThread(all_camera_names).addCallbacks(self.write_bouquet, self.fetch_failed)

    def write_bouquet(self, streams):
        c = config.plugins.camalert
        if not streams:
            self.session.open(MessageBox, _("go2rtc has no cameras configured."), MessageBox.TYPE_WARNING)
            return
        os.makedirs(E2, exist_ok=True)
        with open(E2 + BOUQUET_FILE + ".tmp", "w") as f:
            direct = direct_cameras() if c.source.value == "direct" else None
            f.write(bouquet_text(c.bouquet_name.value or "Cameras", normalize_server(c.server.value), streams,
                                 int(c.rtsp_port.value), cameras=direct))
        os.replace(E2 + BOUQUET_FILE + ".tmp", E2 + BOUQUET_FILE)
        with open(E2 + "bouquets.tv") as f:
            old = f.read()
        new = add_to_bouquets(old)
        if new != old:
            with open(E2 + "bouquets.tv.tmp", "w") as f:
                f.write(new)
            os.replace(E2 + "bouquets.tv.tmp", E2 + "bouquets.tv")
        if config.plugins.camalert.mqtt_enabled.value and config.plugins.camalert.mqtt_discovery.value:
            mqtt.announce()
        db = eDVBDB.getInstance()
        db.reloadBouquets()
        try:
            from Screens.InfoBar import InfoBar
            InfoBar.instance.servicelist.reloadBouquets() if InfoBar.instance else None
        except Exception:
            pass
        self.session.open(MessageBox, _("Channel list '%s' with %d cameras created.") % (c.bouquet_name.value, len(streams)),
                          MessageBox.TYPE_INFO, timeout=5)

    def test(self):
        c = config.plugins.camalert
        if not c.camera.value:
            self.session.open(MessageBox, _("Choose a default camera first."), MessageBox.TYPE_WARNING)
            return
        self.save(close=False)
        self.close()
        Controller.instance.show(c.camera.value, 15, c.mode.value)

    def save(self, close=True):
        c = config.plugins.camalert
        port_changed = c.http_port.isChanged() or c.api_https.isChanged()
        mqtt_changed = any(x.isChanged() for x in (c.mqtt_enabled, c.mqtt_host, c.mqtt_port, c.mqtt_user, c.mqtt_password,
                                                   c.mqtt_discovery, c.mqtt_name, c.source, c.server))
        for x in self["config"].list:
            x[1].save()
        config.plugins.camalert.save()
        if port_changed:
            server.start()
        if mqtt_changed:
            mqtt.start()
        if close:
            self.close()

    def cancel(self):
        for x in self["config"].list:
            x[1].cancel()
        self.close()
