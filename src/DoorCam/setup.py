# -*- coding: utf-8 -*-
# DoorCam - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 DoorCam developers. Licensed under the GNU GPL v2 (see LICENSE).
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
from .display import Controller, open_url
from .logic import (BOUQUET_FILE, add_to_bouquets, bouquet_text, display_name, normalize_server,
                    streams_from_json)

E2 = "/etc/enigma2/"


def fetch_streams(srv):
    with open_url(srv + "/api/streams", timeout=5) as r:
        return streams_from_json(r.read().decode("utf-8", "replace"))


class DoorCamSetup(ConfigListScreen, Screen):
    skin = """<screen name="DoorCamSetup" position="center,center" size="1100,700" title="DoorCam">
        <widget name="config" position="20,20" size="1060,520" itemHeight="40" font="Regular;28" scrollbarMode="showOnDemand" />
        <widget source="help" render="Label" position="20,550" size="1060,80" font="Regular;24" foregroundColor="#aaaaaa" />
        <widget source="key_red" render="Label" position="20,645" size="250,40" backgroundColor="#9f1313" font="Regular;24" halign="center" valign="center" />
        <widget source="key_green" render="Label" position="290,645" size="250,40" backgroundColor="#1f771f" font="Regular;24" halign="center" valign="center" />
        <widget source="key_yellow" render="Label" position="560,645" size="250,40" backgroundColor="#a08000" font="Regular;24" halign="center" valign="center" />
        <widget source="key_blue" render="Label" position="830,645" size="250,40" backgroundColor="#18188b" font="Regular;24" halign="center" valign="center" />
    </screen>"""

    def __init__(self, session):
        Screen.__init__(self, session)
        self.setTitle("DoorCam %s" % __version__)
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
        c = config.plugins.doorcam
        items = [
            (_("Enable DoorCam"), c.enabled, _("Turn the HTTP API and pop-ups on or off.")),
            (_("go2rtc address"), c.server, _("Address of your go2rtc server, e.g. http://192.168.1.10:1984")),
            (_("go2rtc RTSP port"), c.rtsp_port, _("Usually 8554. Used for live view and the camera list.")),
        ]
        if c.server.value.strip().lower().startswith("https"):
            items += [(_("Check go2rtc certificate"), c.verify_ssl,
                       _("Turn off for a self-signed certificate (only in your own network)."))]
        items += [
            (_("Default camera"), c.camera, _("Press OK to choose from the cameras in go2rtc.")),
            (_("Display mode"), c.mode, _("Photo window keeps watching TV; live switches the channel to the camera.")),
            (_("Duration (seconds)"), c.duration, _("How long the camera stays on screen.")),
        ]
        if c.mode.value == "photo":
            items += [(_("Window position"), c.position, ""), (_("Window size"), c.size, "")]
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
        items += [(_("Not during a recording"), c.skip_recording, _("Ignore requests while the receiver is recording."))]
        items += [
            (_("HTTP port"), c.http_port, _("Port of the DoorCam API on this receiver (default 8099).")),
            (_("Use HTTPS for the API"), c.api_https,
             _("Uses a self-signed certificate; callers must turn off certificate checking.")),
            (_("Allowed callers"), c.allow, _("'Local network only' is recommended.")),
            (_("Access token (optional)"), c.token, _("If set, callers must add ?token=... to every request.")),
            (_("Camera list name"), c.bouquet_name, _("Name of the channel list created with the yellow button.")),
        ]
        self.help_texts = [i[2] for i in items]
        self["config"].list = [getConfigListEntry(i[0], i[1]) for i in items]

    def update_help(self):
        i = self["config"].getCurrentIndex()
        self["help"].text = self.help_texts[i] if 0 <= i < len(self.help_texts) else ""

    def server(self):
        srv = normalize_server(config.plugins.doorcam.server.value)
        if not srv:
            self.session.open(MessageBox, _("Please enter a valid go2rtc address first."), MessageBox.TYPE_ERROR)
        return srv

    def ok(self):
        if self["config"].getCurrent()[1] is config.plugins.doorcam.camera:
            srv = self.server()
            if srv:
                threads.deferToThread(fetch_streams, srv).addCallbacks(self.choose_camera, self.fetch_failed)
        else:
            for name in ("keyOK", "keySelect", "keyText"):
                handler = getattr(self, name, None)
                if handler:
                    handler()
                    break

    def fetch_failed(self, err):
        self.session.open(MessageBox, _("Could not reach go2rtc:\n%s") % err.getErrorMessage(), MessageBox.TYPE_ERROR)

    def choose_camera(self, streams):
        if not streams:
            self.session.open(MessageBox, _("go2rtc has no cameras configured."), MessageBox.TYPE_WARNING)
            return
        self.session.openWithCallback(self.camera_chosen, ChoiceBox, title=_("Choose camera"),
                                      list=[(display_name(s), s) for s in streams])

    def camera_chosen(self, choice):
        if choice:
            config.plugins.doorcam.camera.value = choice[1]
            self["config"].invalidateCurrent()

    def make_bouquet(self):
        srv = self.server()
        if srv:
            threads.deferToThread(fetch_streams, srv).addCallbacks(self.write_bouquet, self.fetch_failed)

    def write_bouquet(self, streams):
        c = config.plugins.doorcam
        if not streams:
            self.session.open(MessageBox, _("go2rtc has no cameras configured."), MessageBox.TYPE_WARNING)
            return
        with open(E2 + BOUQUET_FILE + ".tmp", "w") as f:
            f.write(bouquet_text(c.bouquet_name.value or "Cameras", normalize_server(c.server.value), streams,
                                 int(c.rtsp_port.value)))
        os.replace(E2 + BOUQUET_FILE + ".tmp", E2 + BOUQUET_FILE)
        with open(E2 + "bouquets.tv") as f:
            old = f.read()
        new = add_to_bouquets(old)
        if new != old:
            with open(E2 + "bouquets.tv.tmp", "w") as f:
                f.write(new)
            os.replace(E2 + "bouquets.tv.tmp", E2 + "bouquets.tv")
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
        c = config.plugins.doorcam
        if not c.camera.value:
            self.session.open(MessageBox, _("Choose a default camera first."), MessageBox.TYPE_WARNING)
            return
        self.save(close=False)
        self.close()
        Controller.instance.show(c.camera.value, 15, c.mode.value)

    def save(self, close=True):
        port_changed = config.plugins.doorcam.http_port.isChanged() or config.plugins.doorcam.api_https.isChanged()
        for x in self["config"].list:
            x[1].save()
        config.plugins.doorcam.save()
        if port_changed:
            server.start()
        if close:
            self.close()

    def cancel(self):
        for x in self["config"].list:
            x[1].cancel()
        self.close()
