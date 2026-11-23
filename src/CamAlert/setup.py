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
from Components.config import config, configfile, getConfigListEntry, ConfigSelection
from twisted.internet import threads

from . import _, __version__
from . import server
from . import mqtt
from .display import CAMERA_FILE, Controller, all_camera_names, direct_cameras, open_url, pillow_available
from .logic import (DEVICES_FILE, format_map, parse_map, parse_orientation, parse_refresh, valid_port, format_titles, parse_titles, title_for, BOUQUET_FILE, add_to_bouquets, bouquet_text, display_name, normalize_server, parse_cams,
                    streams_from_json)

E2 = "/etc/enigma2/"


def fetch_streams(srv):
    with open_url(srv + "/api/streams", timeout=5) as r:
        return streams_from_json(r.read().decode("utf-8", "replace"))


class CamAlertSetup(ConfigListScreen, Screen):
    # Designed for 1920x1080 and scaled to the receiver's skin resolution (many skins are 1280x720).
    SKIN = """<screen name="CamAlertSetup" position="center,center" size="{W},{H}" title="CamAlert">
        <widget name="config" position="{m},{m}" size="{cw},{ch}" itemHeight="{ih}" font="Regular;{fs}" scrollbarMode="showOnDemand" />
        <widget source="help" render="Label" position="{m},{hy}" size="{cw},{hh}" font="Regular;{hf}" foregroundColor="#aaaaaa" />
        <widget name="HelpWindow" position="0,0" size="1,1" zPosition="1" transparent="1" alphatest="on" />
        <widget source="VKeyIcon" render="Pixmap" position="0,0" size="1,1" conditional="VKeyIcon"><convert type="ConditionalShowHide" /></widget>
        <widget source="key_red" render="Label" position="{k0},{ky}" size="{kw},{kh}" backgroundColor="#9f1313" font="Regular;{hf}" halign="center" valign="center" />
        <widget source="key_green" render="Label" position="{k1},{ky}" size="{kw},{kh}" backgroundColor="#1f771f" font="Regular;{hf}" halign="center" valign="center" />
        <widget source="key_yellow" render="Label" position="{k2},{ky}" size="{kw},{kh}" backgroundColor="#a08000" font="Regular;{hf}" halign="center" valign="center" />
        <widget source="key_blue" render="Label" position="{k3},{ky}" size="{kw},{kh}" backgroundColor="#18188b" font="Regular;{hf}" halign="center" valign="center" />
    </screen>"""

    @staticmethod
    def build_skin(screen_w):
        f = screen_w / 1920.0

        def v(x):
            return int(round(x * f))
        return CamAlertSetup.SKIN.format(
            W=v(1100), H=v(820), m=v(20), cw=v(1060), ch=v(600), ih=v(42), fs=v(30), hy=v(630), hh=v(100), hf=v(26),
            ky=v(755), kw=v(250), kh=v(46), k0=v(20), k1=v(290), k2=v(560), k3=v(830))

    def __init__(self, session):
        from enigma import getDesktop
        self.skin = self.build_skin(getDesktop(0).size().width())
        Screen.__init__(self, session)
        self.setTitle("CamAlert %s   (%s)" % (__version__, _("MENU = diagnostics / events")))
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Camera list"))
        self["key_blue"] = StaticText(_("Test"))
        self["help"] = StaticText("")
        ConfigListScreen.__init__(self, [], session=session, on_change=self.build)
        self["actions"] = ActionMap(["SetupActions", "ColorActions"], {
            "cancel": self.cancel, "red": self.cancel, "green": self.save, "save": self.save,
            "ok": self.ok, "yellow": self.make_bouquet, "blue": self.test}, -2)
        self["menu_actions"] = ActionMap(["MenuActions"], {"menu": self.menu}, -2)
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
        ]
        if c.source.value == "go2rtc":
            n = len(parse_titles(c.titles.value))
            self.names_entry = ConfigSelection(choices=[("x", (_("%d own names") % n) if n else _("automatic"))])
            items += [(_("Camera names"), self.names_entry, _("Press OK to give a camera its own name (empty = automatic)."))]
        items += [
            (_("Display mode"), c.mode, _("Photo window keeps watching TV; live switches the channel to the camera.")),
            (_("Duration (seconds)"), c.duration, _("How long the camera stays on screen.")),
        ]
        if c.mode.value == "photo":
            items += [(_("Window position"), c.position, ""), (_("Window size"), c.size, ""),
                      (_("Remote control in photo window"), c.window_keys,
                       _("OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too.")),
                      (_("Title size"), c.title_size, ""),
                      (_("Layout with several cameras"), c.strip_layout,
                       _("A request with 2-4 cameras shows them together in one corner window."))]
        if c.mode.value in ("photo", "notify"):
            items += [(_("Pause TV meanwhile"), c.pause_tv,
                       _("Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift."))]
        if c.mode.value == "live":
            items += [(_("Return to previous channel"), c.live_return,
                       _("Switch back to what you were watching when the time is up.")),
                      (_("Volume during live view (%)"), c.live_volume,
                       _("Percentage of the current volume while the camera is shown. 100 = unchanged."))]
        if c.source.value == "go2rtc":
            n_o = len(parse_orientation(c.orientation.value))
            n_r = len(parse_refresh(c.refresh.value))
            self.orientation_entry = ConfigSelection(choices=[("x", (_("%d cameras") % n_o) if n_o else _("normal"))])
            self.refresh_entry = ConfigSelection(choices=[("x", (_("%d cameras") % n_r) if n_r else _("as fast as possible"))])
            items += [(_("Turn or mirror image"), self.orientation_entry,
                       _("Press OK to turn a camera that hangs upside down (needs python3-pillow).")),
                      (_("Refresh interval"), self.refresh_entry,
                       _("Press OK to fetch a camera's photos less often (seconds), e.g. for a slow camera."))]
        items += [(_("Do not disturb"), c.dnd, _("Blocks requests with normal priority. Also via the API, MQTT and Home Assistant.")),
                  (_("Do not disturb blocks"), c.dnd_level, "")]
        items += [(_("Only between certain times"), c.limit_hours, _("Ignore requests outside the chosen times."))]
        if c.limit_hours.value:
            items += [(_("From"), c.from_time, ""), (_("Until"), c.until_time, _("May pass midnight, e.g. 07:00 to 23:00."))]
        items += [(_("Not during a recording"), c.skip_recording, _("Ignore requests while the receiver is recording.")),
                  (_("Not while playing a recording or video"), c.skip_media,
                   _("Ignore normal requests while you watch a recording or a video file.")),
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
            (_("Update camera list automatically"), c.auto_bouquet,
             _("Checks every 30 minutes for new or removed cameras and updates the channel list.")),
            (_("Camera list position"), c.bouquet_position, _("Where the camera list appears among your channel lists.")),
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
                (_("Frigate events"), c.frigate_enabled,
                 _("Shows the camera when Frigate detects something (via MQTT, without Home Assistant).")),
            ]
            if c.frigate_enabled.value:
                items += [
                    (_("Frigate MQTT prefix"), c.frigate_prefix, _("Usually 'frigate'.")),
                    (_("Frigate objects"), c.frigate_labels, _("Comma separated, e.g. person,car. Empty = all objects.")),
                    (_("Frigate camera names"), c.frigate_map,
                     _("Only if the names differ from go2rtc: frigate=go2rtc|other=other_stream")),
                    (_("Frigate priority"), c.frigate_priority, ""),
                    (_("Frigate address (for clips)"), c.frigate_url,
                     _("Optional, e.g. http://192.168.1.10:5000 - lets you play the clip of an event from the event list.")),
                ]
        items += [
            (_("Colour keys to Home Assistant"), c.ha_buttons,
             _("While a camera is on screen the colour keys send an event to Home Assistant (e.g. open the gate).")),
            (_("PTZ key"), c.ptz_key,
             _("For cameras with PTZ in %s: this key switches PTZ mode on (arrows, CH+/CH-, OK = home).") % DEVICES_FILE),
            (_("Foscam motion alarms"), c.foscam_poll,
             _("Asks Foscam cameras from %s every 2 seconds for a motion or sound alarm.") % DEVICES_FILE),
            (_("Foscam priority"), c.device_priority, ""),
            (_("Event snapshots folder"), c.event_folder, _("Small photos of the last 20 events (default /tmp/camalert_events).")),
            (_("Log level"), c.log_level, _("camalert.log in /home/root/logs (or /tmp). Passwords and tokens are never logged.")),
            (_("Remote syslog (host:port)"), c.log_syslog, _("Optional: also send the log via UDP (RFC 5424), e.g. to Loki/Alloy.")),
            (_("Check for updates"), c.update_check, _("Looks once a day on GitHub for a new version and shows a message.")),
        ]
        self.help_texts = [i[2] for i in items]
        self["config"].list = [getConfigListEntry(i[0], i[1]) for i in items]

    def menu(self):
        self.session.openWithCallback(self.menu_chosen, ChoiceBox, title="CamAlert",
                                      list=[(_("Diagnostics"), "diag"), (_("Event list"), "events")])

    def menu_chosen(self, choice):
        from .diagnostics import DiagnosticsScreen, EventsScreen
        if choice:
            self.session.open(DiagnosticsScreen if choice[1] == "diag" else EventsScreen)

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
        if self["config"].getCurrent()[1] is getattr(self, "names_entry", None):
            if self.server():
                threads.deferToThread(all_camera_names).addCallbacks(self.choose_title_camera, self.fetch_failed)
        elif self["config"].getCurrent()[1] is getattr(self, "orientation_entry", None):
            if self.server():
                self.map_setting = "orientation"
                threads.deferToThread(all_camera_names).addCallbacks(self.choose_map_camera, self.fetch_failed)
        elif self["config"].getCurrent()[1] is getattr(self, "refresh_entry", None):
            if self.server():
                self.map_setting = "refresh"
                threads.deferToThread(all_camera_names).addCallbacks(self.choose_map_camera, self.fetch_failed)
        elif self["config"].getCurrent()[1] is config.plugins.camalert.mosaic:
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

    def map_values(self):
        """Choices for the per-camera setting being edited: [(label, value)], value "" = default."""
        if self.map_setting == "orientation":
            return [(_("normal"), ""), (_("mirror (left/right)"), "mirror"), (_("upside down (flip)"), "flip"),
                    (_("turned 180 degrees"), "rot180")]
        return [(_("as fast as possible"), "")] + [(_("every %s seconds") % v, v) for v in ("1", "2", "5", "10", "30", "60")]

    def choose_map_camera(self, streams):
        if not streams:
            return
        setting = getattr(config.plugins.camalert, self.map_setting)
        current = parse_map(setting.value)
        labels = dict((v, l) for l, v in self.map_values())
        self.session.openWithCallback(self.map_camera_chosen, ChoiceBox, title=_("Choose camera"),
                                      list=[("%s  ->  %s" % (self.titles().get(s, display_name(s)),
                                                             labels.get(current.get(s, ""), current.get(s, ""))), s)
                                            for s in streams])

    def map_camera_chosen(self, choice):
        if not choice:
            return
        self.map_camera = choice[1]
        self.session.openWithCallback(self.map_value_chosen, ChoiceBox, title=choice[0], list=self.map_values())

    def map_value_chosen(self, choice):
        if choice is None:
            return
        setting = getattr(config.plugins.camalert, self.map_setting)
        current = parse_map(setting.value)
        if choice[1]:
            current[self.map_camera] = choice[1]
        else:
            current.pop(self.map_camera, None)
        setting.value = format_map(current)
        if self.map_setting == "orientation" and choice[1] and not pillow_available():
            self.session.open(MessageBox, _("Install python3-pillow to turn or mirror images:\nopkg install python3-pillow"),
                              MessageBox.TYPE_INFO)
        self.build()

    def fetch_failed(self, err):
        self.session.open(MessageBox, _("Could not reach go2rtc:\n%s") % err.getErrorMessage(), MessageBox.TYPE_ERROR)

    def titles(self):
        if config.plugins.camalert.source.value == "direct":
            return {cam["name"]: cam["title"] for cam in direct_cameras()}
        return parse_titles(config.plugins.camalert.titles.value)

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

    def choose_title_camera(self, streams):
        if not streams:
            return
        titles = parse_titles(config.plugins.camalert.titles.value)
        self.session.openWithCallback(self.title_camera_chosen, ChoiceBox, title=_("Camera names"),
                                      list=[("%s  ->  %s" % (s, title_for(s, titles)), s) for s in streams])

    def title_camera_chosen(self, choice):
        if not choice:
            return
        from Screens.VirtualKeyBoard import VirtualKeyBoard
        self.title_camera = choice[1]
        current = parse_titles(config.plugins.camalert.titles.value).get(choice[1], "")
        self.session.openWithCallback(self.title_typed, VirtualKeyBoard,
                                      title=_("Name for %s (empty = automatic)") % choice[1], text=current)

    def title_typed(self, text):
        if text is None:
            return
        titles = parse_titles(config.plugins.camalert.titles.value)
        if text.strip():
            titles[self.title_camera] = text.strip()
        else:
            titles.pop(self.title_camera, None)
        config.plugins.camalert.titles.value = format_titles(titles)
        self.build()

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
            from . import bouquet
            bouquet.update(True, self.bouquet_done, self.bouquet_failed)

    def bouquet_done(self, changed, count):
        if not count:
            self.session.open(MessageBox, _("go2rtc has no cameras configured."), MessageBox.TYPE_WARNING)
            return
        if config.plugins.camalert.mqtt_enabled.value and config.plugins.camalert.mqtt_discovery.value:
            mqtt.announce()
        self.session.open(MessageBox, _("Channel list '%s' with %d cameras created.") % (
            config.plugins.camalert.bouquet_name.value, count), MessageBox.TYPE_INFO, timeout=5)

    def bouquet_failed(self, message):
        self.session.open(MessageBox, _("Could not reach go2rtc:\n%s") % message, MessageBox.TYPE_ERROR)

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
        config.plugins.camalert.titles.save()
        config.plugins.camalert.save()
        configfile.save()  # write /etc/enigma2/settings now, not only at shutdown
        if port_changed:
            server.start()
        if mqtt_changed:
            mqtt.start()
        if Controller.instance:
            Controller.instance.refresh_names()
        if close:
            self.close()

    def cancel(self):
        for x in self["config"].list:
            x[1].cancel()
        config.plugins.camalert.titles.cancel()
        self.close()
