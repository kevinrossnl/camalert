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
from . import settingsio
from .helpable import HelpBase, help_actions, init_help
from .camalert_core import schema, settingsui
from .camalert_core.style import PRESET_LABELS, PRESETS, preset_changes
from .display import CAMERA_FILE, Controller, all_camera_names, direct_cameras, open_url, pillow_available
from .camalert_core.cameras import (display_name, format_map, format_titles, parse_cams, parse_map,
                                    parse_orientation, parse_refresh, parse_titles, title_for)
from .camalert_core.devices.config import DEVICES_FILE
from .camalert_core.present import go2rtc_problem
from .camalert_core.urls import go2rtc_state, normalize_server, streams_from_json, valid_port
from .services import add_to_bouquets, BOUQUET_FILE, bouquet_text

E2 = "/etc/enigma2/"


def fetch_streams(srv):
    return fetch_stream_info(srv)[0]


def fetch_stream_info(srv):
    """(camera names, composite streams among them) from go2rtc's /api/streams (#125)."""
    from .camalert_core.urls import stream_info_from_json
    with open_url(srv + "/api/streams", timeout=5) as r:
        return stream_info_from_json(r.read().decode("utf-8", "replace"))


PICKERS = ("titles", "orientation", "refresh")  # per-camera maps, edited with OK in choice lists
# triggers: Frigate, Foscam and UniFi Protect settings, each under its own sub-heading
TRIGGER_GROUPS = (("frigate", "Frigate"), ("foscam", "Foscam"), ("unifi", "UniFi Protect"))


def _section(section):
    names = {"general": _("General"), "display": _("Display"), "rules": _("Rules"), "triggers": _("Triggers"),
             "camera_control": _("Camera control"), "home_assistant": _("Home Assistant"), "api": _("API"),
             "channels": _("Channel list"), "log": _("Log and diagnostics")}
    return names.get(section, section)


def values(c):
    """{id: value} of every schema setting, for the core rules of the settings screens (#130)."""
    out = {}
    for s in schema.for_platform("enigma2"):
        el = getattr(c, s.key("enigma2"), None)
        if el is not None:
            out[s.id] = el.value
    return out


def visible(sid, c):
    """Whether a setting applies with the current values of the others (progressive disclosure, #130: the rules
    are in camalert_core.settingsui, the same on every player)."""
    return settingsui.applies(sid, values(c), "enigma2")


def section_title(section):
    return _section(section)


def apply_preset(c, name):
    """Sets the settings of a preset (#48) on the config section c; returns {key: value} that changed."""
    keys = [k for k in PRESETS.get(name, {}) if hasattr(c, k)]
    changes = preset_changes(name, dict((k, getattr(c, k).value) for k in keys), keys)
    for k, v in changes.items():
        getattr(c, k).value = v
    return changes

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

    def __init__(self, session, section=None):
        """section None = the first screen (basic settings + one line per section); otherwise that section (#130)."""
        from enigma import getDesktop
        self.skin = self.build_skin(getDesktop(0).size().width())
        Screen.__init__(self, session)
        self.skinName = ["CamAlertSetup", "Setup"]  # after Screen.__init__, which sets it to the class name
        init_help(self)
        self.section = section
        self.setTitle("CamAlert" if section is None else "CamAlert - %s" % _section(section))
        self.section_rows = {}
        self.help_texts = []
        self["description"] = Label("")
        self["footnote"] = Label("CamAlert %s" % __version__)
        ConfigListScreen.__init__(self, [], session=session, on_change=self.build)
        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save") if section is None else _("OK"))
        self["key_yellow"] = StaticText(_("Create channel list") if section is None else "")
        self["key_blue"] = StaticText(_("Test") if section is None else "")
        self["key_menu"] = StaticText("MENU")
        help_actions(self, "actions", "SetupActions", {
            "cancel": (self.cancel, _("Close without saving")), "save": (self.save, _("Save")),
            "ok": (self.ok, _("Choose a value or camera, or open a section"))}, -2)
        if section is None:
            help_actions(self, "colour_actions", "ColorActions", {
                "red": (self.cancel, _("Close without saving")), "green": (self.save, _("Save")),
                "yellow": (self.make_bouquet, _("Create channel list")),
                "blue": (self.test, _("Save and show the default camera"))}, -2)
        else:  # a section (#130): GREEN back to the first screen (Save there), BLUE more / fewer settings
            help_actions(self, "colour_actions", "ColorActions", {
                "red": (self.cancel, _("Undo the changes in this section")),
                "green": (self.save, _("Back to the first screen")),
                "blue": (self.toggle_expert, _("More settings / fewer settings"))}, -2)
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
        v = values(c)
        rows, group = [], None
        self.section_rows = {}
        if self.section is None:
            for s in settingsui.main_settings("enigma2", v):
                rows.append(self.item(s, c))
            rows.append(("-- %s --" % _("Sections"), ConfigNothing(), ""))
            for section in settingsui.sections("enigma2"):
                el = ConfigSelection(choices=[("x", self.summary(section, v))])
                self.section_rows[id(el)] = section
                rows.append((_section(section), el, _("OK opens the settings of this section.")))
            self.hidden = 0
            note = ""
        else:
            expert = bool(c.all_settings.value)
            shown = settingsui.section_settings(self.section, "enigma2", v, expert)
            if self.section == "triggers":  # Frigate, then Foscam, then UniFi Protect, each under its own heading
                def grp(s):
                    g = [n for n, (prefix, _l) in enumerate(TRIGGER_GROUPS) if s.id.startswith(prefix + "_")]
                    return g[0] if g else len(TRIGGER_GROUPS)
                shown = sorted(shown, key=grp)  # stable: schema order inside a group
            for s in shown:
                if self.section == "triggers":
                    g = [label for prefix, label in TRIGGER_GROUPS if s.id.startswith(prefix + "_")]
                    if g and g[0] != group:
                        group = g[0]
                        rows.append(("   %s" % group, ConfigNothing(), ""))
                rows.append(self.item(s, c))
            self.hidden = settingsui.hidden_expert(self.section, "enigma2", v)
            self["key_blue"].setText(_("Fewer settings") if expert else (_("More settings") if self.hidden else ""))
            note = ("   " + _("%d more settings with BLUE") % self.hidden) if self.hidden and not expert else ""
        self.help_texts = [r[2] for r in rows]
        self["config"].list = [getConfigListEntry(r[0], r[1]) for r in rows]
        self["footnote"].setText("CamAlert %s" % __version__ + note)

    def summary(self, section, v):
        """One line for a section on the first screen: what is on there, else how much differs from the default."""
        on, changed = settingsui.section_summary(section, "enigma2", v)
        parts = [_(label) for label in on]
        if changed:
            parts.append(_("%d changed") % changed)
        return ", ".join(parts) if parts else _("default")

    def open_section(self, section):
        self.session.openWithCallback(self.section_closed, CamAlertSetup, section)

    def section_closed(self, *_args):
        self.build()

    def toggle_expert(self):
        c = config.plugins.camalert
        if not (c.all_settings.value or self.hidden):
            return
        c.all_settings.value = not c.all_settings.value
        c.all_settings.save()
        self.build()

    def menu(self):
        from .camalert_core.report import TITLE as REPORT_TITLE
        choices = [(_("Diagnostics"), "diag"), (_(REPORT_TITLE), "report"), (_("Event list"), "events"),
                   (_("Start the wizard again"), "wizard"),
                   (_(PRESET_LABELS["simple"]), "simple"),
                   (_("Export settings"), "export"), (_("Import settings"), "import")]
        if settingsio.backups().latest() is not None:
            choices.append((_("Undo the last import"), "undo"))
        choices.append((_("Fewer settings") if config.plugins.camalert.all_settings.value else _("More settings"),
                        "expert"))  # #130: expert settings in the section screens
        self.session.openWithCallback(self.menu_chosen, ChoiceBox, title="CamAlert", list=choices)

    def menu_chosen(self, choice):
        from .diagnostics import DiagnosticsScreen, EventsScreen
        if not choice:
            return
        if choice[1] == "simple":  # #48: a preset only fills in settings; Save keeps them, Cancel undoes them
            apply_preset(config.plugins.camalert, "simple")
            self.build()
        elif choice[1] == "wizard":  # #120
            from .wizard import Wizard
            Wizard(self.session, on_close=self.build).start()
        elif choice[1] == "export":  # #7
            self.session.openWithCallback(self.export_chosen, ChoiceBox, title=_("Export settings"), list=[
                (_("Without passwords and access token"), False), (_("With passwords and access token"), True)])
        elif choice[1] == "import":
            path = settingsio.import_file()
            if path is None:
                self.session.open(MessageBox, _("No %s found on a USB stick, the hard disk or in /home/root.")
                                  % settingsio.FILE_NAME, MessageBox.TYPE_INFO)
                return
            self.import_path = path
            self.session.openWithCallback(self.import_confirmed, MessageBox, _(
                "Import the settings from %s?\nThe current settings are saved first, so you can undo this.") % path)
        elif choice[1] == "undo":
            self.session.openWithCallback(self.undo_confirmed, MessageBox, _(
                "Go back to the settings from before the last import?"))
        elif choice[1] == "expert":
            c = config.plugins.camalert
            c.all_settings.value = not c.all_settings.value
            c.all_settings.save()
            self.build()
        elif choice[1] == "report":  # #132
            from .diagnostics import ReportScreen
            self.session.open(ReportScreen)
        else:
            self.session.open(DiagnosticsScreen if choice[1] == "diag" else EventsScreen)

    def export_chosen(self, choice):
        if not choice:
            return
        try:
            path = settingsio.export(secrets=choice[1])
        except (IOError, OSError) as e:
            self.session.open(MessageBox, _("Could not save the settings: %s") % e, MessageBox.TYPE_ERROR)
            return
        self.session.open(MessageBox, _("Settings saved in %s") % path, MessageBox.TYPE_INFO)

    def import_confirmed(self, yes):
        if not yes:
            return
        try:
            report = settingsio.do_import(self.import_path)
        except settingsio.settingsfile.BadFile as e:
            self.session.open(MessageBox, _("This file cannot be imported (%s).") % _(str(e)), MessageBox.TYPE_ERROR)
            return
        except (IOError, OSError) as e:
            self.session.open(MessageBox, _("Could not read the settings: %s") % e, MessageBox.TYPE_ERROR)
            return
        self.settings_replaced(report)

    def undo_confirmed(self, yes):
        if not yes:
            return
        report = settingsio.undo()
        if report is not None:
            self.settings_replaced(report)

    def settings_replaced(self, report):
        """After an import or undo: restart what depends on the settings and show the new values (#7)."""
        server.start()
        mqtt.start()
        if Controller.instance:
            Controller.instance.refresh_names()
        self.build()
        text = _("%d settings changed.") % len(report["changed"])
        if report["problems"]:
            text += "\n" + _("Not imported (invalid value): %s") % ", ".join(report["problems"])
        self.session.open(MessageBox, text, MessageBox.TYPE_INFO)

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
        current = self["config"].getCurrent()
        if current and id(current[1]) in self.section_rows:  # #130: a section line on the first screen
            self.open_section(self.section_rows[id(current[1])])
        elif self["config"].getCurrent()[1] is getattr(self, "names_entry", None):
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
        if self.section is not None:  # #130: back to the first screen; its Save writes everything, Cancel undoes it
            self.close()
            return
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
        """Undoes every change, also those made in the choice lists (names, orientation, refresh, mosaic). In a
        section screen (#130) only the changes of that section."""
        c = config.plugins.camalert
        if self.section is None:
            for el in c.content.items.values():
                el.cancel()
        else:
            for s in schema.for_platform("enigma2"):
                if s.section == self.section and s.level not in ("internal", "basic"):
                    el = getattr(c, s.key("enigma2"), None)
                    if el is not None:
                        el.cancel()
        self.close()
