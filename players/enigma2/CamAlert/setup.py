# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Settings screen: everything a user needs without touching files."""
import os

from enigma import eDVBDB
from Screens.Screen import Screen
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry, ConfigNothing, ConfigSelection
from twisted.internet import threads

from . import _, __version__
from . import server
from . import mqtt
from .helpable import HelpBase, help_actions, init_help
from .camalert_core import schema
from .display import CAMERA_FILE, Controller, all_camera_names, direct_cameras, open_url, pillow_available
from .camalert_core.cameras import (display_name, format_map, format_titles, parse_cams, parse_map,
                                    parse_orientation, parse_refresh, parse_titles, title_for)
from .camalert_core.devices.config import DEVICES_FILE
from .camalert_core.present import go2rtc_problem
from .camalert_core.urls import go2rtc_state, normalize_server, streams_from_json, valid_port
from .services import add_to_bouquets, BOUQUET_FILE, bouquet_text

E2 = "/etc/enigma2/"


def fetch_streams(srv):
    with open_url(srv + "/api/streams", timeout=5) as r:
        return streams_from_json(r.read().decode("utf-8", "replace"))


LEVELS = {"basic": 0, "advanced": 1, "expert": 2}  # config.usage.setup_level: simple / intermediate / expert
PICKERS = ("titles", "orientation", "refresh")  # per-camera maps, edited with OK in choice lists
# triggers: Frigate, Foscam and UniFi Protect settings, each under its own sub-heading
TRIGGER_GROUPS = (("frigate", "Frigate"), ("foscam", "Foscam"), ("unifi", "UniFi Protect"))


def _section(section):
    names = {"general": _("General"), "display": _("Display"), "rules": _("Rules"), "triggers": _("Triggers"),
             "camera_control": _("Camera control"), "home_assistant": _("Home Assistant"), "api": _("API"),
             "channels": _("Channel list"), "log": _("Log and diagnostics")}
    return names.get(section, section)


def image_level():
    """0 / 1 / 2 = the image's setup level (simple / intermediate / expert); expert where the image has none."""
    try:
        return max(0, min(2, int(config.usage.setup_level.index)))
    except Exception:
        return 2


def visible(sid, c):
    """Whether a setting applies with the current values of the others (progressive disclosure)."""
    go2rtc, mode = c.source.value == "go2rtc", c.mode.value
    rules = {
        "server": go2rtc, "rtsp_port": go2rtc, "titles": go2rtc, "orientation": go2rtc, "refresh": go2rtc,
        "cooldown": go2rtc, "substreams": go2rtc,
        "verify_ssl": not go2rtc or c.server.value.strip().lower().startswith("https"),
        "position": mode == "photo", "size": mode == "photo", "window_keys": mode == "photo",
        "title_size": mode == "photo", "strip_layout": mode == "photo",
        "pause_tv": mode in ("photo", "notify"), "live_return": mode == "live", "live_volume": mode == "live",
        "from_time": c.limit_hours.value, "until_time": c.limit_hours.value,
        "frigate_enabled": c.mqtt_enabled.value,
    }
    if sid in rules:
        return bool(rules[sid])
    if sid.startswith("frigate_"):
        return bool(c.mqtt_enabled.value and c.frigate_enabled.value)
    if sid.startswith("foscam_") and sid != "foscam_enabled":
        return bool(c.foscam_enabled.value)
    if sid.startswith("unifi_") and sid != "unifi_enabled":
        return bool(c.unifi_enabled.value)
    if sid.startswith("mqtt_"):
        return sid == "mqtt_enabled" or bool(c.mqtt_enabled.value)
    return True


def ordered():
    """The Enigma2 settings in schema order; inside 'triggers' Frigate first, then Foscam, then UniFi Protect."""
    settings = [s for s in schema.for_platform("enigma2") if s.level != "internal"]

    def key(item):
        i, s = item
        group = [n for n, (prefix, _l) in enumerate(TRIGGER_GROUPS) if s.id.startswith(prefix + "_")]
        return (schema.SECTIONS.index(s.section), group[0] if s.section == "triggers" and group else 0, i)
    return [s for _i, s in sorted(enumerate(settings), key=key)]


class CamAlertSetup(ConfigListScreen, Screen, HelpBase):
    # Designed for 1920x1080 and scaled to the receiver's skin resolution (many skins are 1280x720). Used when
    # the skin has no "Setup" screen; otherwise the skin's own Setup layout is used (skinName).
    SKIN = """<screen name="CamAlertSetup" position="center,center" size="{W},{H}" title="CamAlert">
        <widget name="config" position="{m},{m}" size="{cw},{ch}" itemHeight="{ih}" font="Regular;{fs}" scrollbarMode="showOnDemand" />
        <widget name="description" position="{m},{hy}" size="{cw},{hh}" font="Regular;{hf}" foregroundColor="#aaaaaa" />
        <widget name="footnote" position="{m},{fy}" size="{cw},{fh}" font="Regular;{ff}" foregroundColor="#888888" halign="right" />
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
            W=v(1100), H=v(820), m=v(20), cw=v(1060), ch=v(588), ih=v(42), fs=v(30), hy=v(616), hh=v(96), hf=v(26),
            fy=v(714), fh=v(32), ff=v(22), ky=v(755), kw=v(250), kh=v(46), k0=v(20), k1=v(290), k2=v(560), k3=v(830))

    def __init__(self, session):
        from enigma import getDesktop
        self.skin = self.build_skin(getDesktop(0).size().width())
        Screen.__init__(self, session)
        self.skinName = ["CamAlertSetup", "Setup"]  # after Screen.__init__, which sets it to the class name
        init_help(self)
        self.setTitle("CamAlert")
        self.level = image_level()
        self.help_texts = []
        self["description"] = Label("")
        self["footnote"] = Label("CamAlert %s" % __version__)
        ConfigListScreen.__init__(self, [], session=session, on_change=self.build)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Create channel list"))
        self["key_blue"] = StaticText(_("Test"))
        self["key_menu"] = StaticText("MENU")
        help_actions(self, "actions", "SetupActions", {
            "cancel": (self.cancel, _("Close without saving")), "save": (self.save, _("Save")),
            "ok": (self.ok, _("Choose a value or camera"))}, -2)
        help_actions(self, "colour_actions", "ColorActions", {
            "red": (self.cancel, _("Close without saving")), "green": (self.save, _("Save")),
            "yellow": (self.make_bouquet, _("Create channel list")),
            "blue": (self.test, _("Save and show the default camera"))}, -2)
        help_actions(self, "menu_actions", "MenuActions", {
            "menu": (self.menu, _("Diagnostics, event list, all settings"))}, -2)
        self.build()
        self.onLayoutFinish.append(self.ask_server)
        self.onLayoutFinish.append(self.update_help)
        self["config"].onSelectionChanged.append(self.update_help)

    def item(self, s, c):
        """(label, config element, help) of one schema setting."""
        el = getattr(c, s.key("enigma2"))
        if s.id == "titles":
            n = len(parse_titles(c.titles.value))
            self.names_entry = el = ConfigSelection(choices=[("x", (_("%d own names") % n) if n else _("automatic"))])
        elif s.id == "orientation":
            n = len(parse_orientation(c.orientation.value))
            self.orientation_entry = el = ConfigSelection(choices=[("x", (_("%d cameras") % n) if n else _("normal"))])
        elif s.id == "refresh":
            n = len(parse_refresh(c.refresh.value))
            self.refresh_entry = el = ConfigSelection(choices=[("x", (_("%d cameras") % n) if n else _("as fast as possible"))])
        text = _(s.help) if s.help else ""
        if "%s" in text:
            text = text % (CAMERA_FILE if s.id == "source" else DEVICES_FILE)
        if s.id == "server":
            problem = go2rtc_problem(go2rtc_state(c.server.value), _)
            if problem:  # #73: no default address any more; the help line asks for it
                text = "%s. %s" % (problem, text)
        return _(s.label), el, text

    def build(self):
        c = config.plugins.camalert
        rows, section, group = [], None, None
        self.hidden = 0
        for s in ordered():
            if not visible(s.id, c):
                continue
            if LEVELS[s.level] > self.level:
                self.hidden += 1
                continue
            if s.section != section:
                section, group = s.section, None
                rows.append(("-- %s --" % _section(section), ConfigNothing(), ""))
            if s.section == "triggers":
                g = [label for prefix, label in TRIGGER_GROUPS if s.id.startswith(prefix + "_")]
                if g and g[0] != group:
                    group = g[0]
                    rows.append(("   %s" % group, ConfigNothing(), ""))
            rows.append(self.item(s, c))
        self.help_texts = [r[2] for r in rows]
        self["config"].list = [getConfigListEntry(r[0], r[1]) for r in rows]
        self["footnote"].setText("CamAlert %s" % __version__ + (
            "   " + (_("%d more settings via MENU") % self.hidden) if self.hidden else ""))

    def menu(self):
        choices = [(_("Diagnostics"), "diag"), (_("Event list"), "events"), (_("Start the wizard again"), "wizard")]
        if self.level < 2:
            choices.append((_("Show all settings"), "all"))
        elif image_level() < 2:
            choices.append((_("Show fewer settings"), "fewer"))
        self.session.openWithCallback(self.menu_chosen, ChoiceBox, title="CamAlert", list=choices)

    def menu_chosen(self, choice):
        from .diagnostics import DiagnosticsScreen, EventsScreen
        if not choice:
            return
        if choice[1] == "wizard":  # #120
            from .wizard import Wizard
            Wizard(self.session, on_close=self.build).start()
        elif choice[1] in ("all", "fewer"):
            self.level = 2 if choice[1] == "all" else image_level()
            self.build()
        else:
            self.session.open(DiagnosticsScreen if choice[1] == "diag" else EventsScreen)

    def ask_server(self):
        """#73: go2rtc mode without an address: start on the go2rtc address (its help line says it is not set)."""
        c = config.plugins.camalert
        if c.source.value != "go2rtc" or go2rtc_state(c.server.value) == "ok":
            return
        for i, entry in enumerate(self["config"].list):
            if len(entry) > 1 and entry[1] is c.server:
                move = getattr(self["config"], "setCurrentIndex", None) or getattr(self["config"], "moveToIndex")
                move(i)
                return

    def update_help(self):
        i = self["config"].getCurrentIndex()
        self["description"].setText(self.help_texts[i] if 0 <= i < len(self.help_texts) else "")

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
        """BLUE: asks, then saves the settings and shows the default camera for 15 seconds."""
        if not config.plugins.camalert.camera.value:
            self.session.open(MessageBox, _("Choose a default camera first."), MessageBox.TYPE_WARNING)
            return
        self.session.openWithCallback(self.test_confirmed, MessageBox,
                                      _("Save the settings and show the default camera now?"), MessageBox.TYPE_YESNO)

    def test_confirmed(self, yes):
        if not yes:
            return
        c = config.plugins.camalert
        self.save()
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
        else:
            server.announce()  # on/off, allowed callers or the name changed (#121)
        if mqtt_changed:
            mqtt.start()
        if Controller.instance:
            Controller.instance.refresh_names()
        if close:
            self.close()

    def cancel(self):
        """Undoes every change, also those made in the choice lists (names, orientation, refresh, mosaic)."""
        for el in config.plugins.camalert.content.items.values():
            el.cancel()
        self.close()
