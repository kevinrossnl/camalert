# CamAlert - diagnostics screen and event list on the TV.
# Copyright (C) 2026 CamAlert developers. GPL v2.
import os
import platform
import socket
import time

from enigma import ePicLoad, eServiceReference, getDesktop
from Screens.Screen import Screen
from Components.Label import Label
from Components.MenuList import MenuList
from Components.Pixmap import Pixmap
from Components.ScrollLabel import ScrollLabel
from Components.Sources.StaticText import StaticText
from Components.config import config
from twisted.internet import threads

from . import _, __version__
from .helpable import HelpBase, help_actions, init_help
from .camalert_core.obs.camlog import LOG
from .display import Controller, all_camera_names, camera_urls, devices, log, open_url
from .camalert_core import present
from .camalert_core.events import diag_line
from .camalert_core.obs.log import redact
from .camalert_core.triggers.frigate import frigate_clip_url
from .camalert_core.triggers.unifi import STATUS as UNIFI_STATUS
from .camalert_core.urls import go2rtc_state, valid_port


def _skin(name, f, extra):
    w, h = int(1500 * f), int(900 * f)
    return ('<screen name="%s" position="center,center" size="%d,%d" title="CamAlert">%s'
            '<widget source="key_red" render="Label" position="%d,%d" size="%d,%d" font="Regular;%d" backgroundColor="#9f1313" halign="center" valign="center" />'
            '<widget name="key_green" position="%d,%d" size="%d,%d" font="Regular;%d" backgroundColor="#1f771f" halign="center" valign="center" />'
            '</screen>' % (name, w, h, extra, int(20 * f), h - int(60 * f), int(300 * f), int(46 * f), int(26 * f),
                           int(340 * f), h - int(60 * f), int(300 * f), int(46 * f), int(26 * f)))


def collect():
    """Runs in a thread: list of check lines."""
    c = config.plugins.camalert
    ctl = Controller.instance
    lines = [diag_line(True, "CamAlert %s, Python %s, %s" % (__version__, platform.python_version(), _image()))]
    names = []
    if c.source.value == "go2rtc":
        problem = present.go2rtc_problem(go2rtc_state(c.server.value), _)
        t = time.time()
        if problem:  # not set or invalid: say so, contact nothing (#73)
            lines.append(diag_line(False, problem))
        else:
            try:
                names = all_camera_names()
                lines.append(diag_line(True, _("go2rtc reachable (%d cameras, %d ms)") % (len(names), (time.time() - t) * 1000)))
            except Exception as e:
                lines.append(diag_line(False, _("go2rtc not reachable: %s") % redact(e)))
    else:
        try:
            names = all_camera_names()
        except Exception:
            names = []
    for n in names[:12]:
        urls = camera_urls(n)
        if not urls or not urls[1]:
            lines.append(diag_line(None, _("%s: no snapshot address (live only)") % n))
            continue
        t = time.time()
        try:
            with open_url(urls[1].replace("width=640", "width=160"), timeout=8) as r:
                size = len(r.read())
            lines.append(diag_line(size > 1000, _("%s: snapshot %d ms") % (n, (time.time() - t) * 1000)))
        except Exception as e:
            lines.append(diag_line(False, _("%s: snapshot failed (%s)") % (n, type(e).__name__)))
    port = valid_port(c.http_port.value, 8099)
    try:
        socket.create_connection(("127.0.0.1", port), 2).close()
        lines.append(diag_line(True, _("API listening on port %d") % port))
    except OSError:
        lines.append(diag_line(False, _("API not listening on port %d") % port))
    if c.mqtt_enabled.value:
        from . import mqtt
        lines.append(diag_line(mqtt.connected(), _("MQTT connected") if mqtt.connected() else _("MQTT not connected")))
    if ctl and ctl.last_caller:
        at, host, source = ctl.last_caller
        lines.append(diag_line(True, _("Last API call %s from %s (%s)") % (present.event_time(at, ui_language()), host,
                                                                         "Home Assistant" if source == "ha" else source)))
    else:
        lines.append(diag_line(None, _("No API call since the last start")))
    devs = devices.load_devices()
    if devs:
        lines.append(diag_line(True, _("Devices file: %s") % ", ".join("%s (%s)" % (n, d["type"]) for n, d in sorted(devs.items()))))
    if c.unifi_enabled.value:  # UniFi Protect source (#70): last check, last event, last error (redacted)
        for ok, text in UNIFI_STATUS.lines(_, lambda ts: present.event_time(ts, ui_language())):
            lines.append(diag_line(ok, text))
    from .display import WARM  # #111: ready cameras and their last picture
    for ok, text in WARM.lines(_):
        lines.append(diag_line(ok, text))
    if c.dnd.value:
        lines.append(diag_line(None, _("Do not disturb is on")))
    lines.append(diag_line(LOG.path is not None or c.log_level.value == "off",
                           _("Log: %s") % (LOG.path or _("off"))))
    return lines


def ui_language():
    """Language of the receiver menus ('nl_NL'), for the date format of the event list."""
    try:
        from Components.Language import language
        return language.getLanguage()
    except Exception:
        return None


def _image():
    try:
        info = dict(l.strip().split("=", 1) for l in open("/etc/image-version") if "=" in l)
        return "%s %s" % (info.get("distro", "?"), info.get("imageversion", info.get("version", "")))
    except Exception:
        return platform.platform()


class DiagnosticsScreen(Screen, HelpBase):
    def __init__(self, session):
        f = getDesktop(0).size().width() / 1920.0
        self.skin = _skin("CamAlertDiagnostics", f,
                          '<widget name="text" position="%d,%d" size="%d,%d" font="Regular;%d" />'
                          % (int(20 * f), int(20 * f), int(1460 * f), int(800 * f), int(26 * f)))
        Screen.__init__(self, session)
        init_help(self)
        self.setTitle(_("CamAlert diagnostics"))
        self["text"] = ScrollLabel(_("Checking..."))
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = Label(_("Check again"))
        close, up, down = (self.close, _("Close")), (self["text"].pageUp, _("Scroll")), (self["text"].pageDown, _("Scroll"))
        help_actions(self, "actions", "OkCancelActions", {"cancel": close, "ok": close}, -1)
        help_actions(self, "colour_actions", "ColorActions", {"red": close, "green": (self.run, _("Check again"))}, -1)
        help_actions(self, "direction_actions", "DirectionActions", {"up": up, "down": down, "left": up, "right": down}, -1)
        self.onLayoutFinish.append(self.run)

    def run(self):
        self["text"].setText(_("Checking..."))
        threads.deferToThread(collect).addCallbacks(self.done, lambda e: self.done([diag_line(False, str(e.value))]))

    def done(self, lines):
        log_lines = LOG.tail(40)
        text = "\n".join(lines)
        if log_lines:
            text += "\n\n" + _("Last log lines:") + "\n" + "\n".join(log_lines)
        self["text"].setText(text)


class EventsScreen(Screen, HelpBase):
    """The last 20 requests: time, camera, who/what, source, priority and what CamAlert did; with snapshot."""

    def __init__(self, session):
        f = getDesktop(0).size().width() / 1920.0
        self.f = f
        self.skin = _skin("CamAlertEvents", f,
                          '<widget name="list" position="%d,%d" size="%d,%d" font="Regular;%d" itemHeight="%d" scrollbarMode="showOnDemand" />'
                          '<widget name="photo" position="%d,%d" size="%d,%d" alphatest="off" />'
                          '<widget name="info" position="%d,%d" size="%d,%d" font="Regular;%d" />'
                          % (int(20 * f), int(20 * f), int(900 * f), int(800 * f), int(24 * f), int(38 * f),
                             int(940 * f), int(20 * f), int(540 * f), int(304 * f),
                             int(940 * f), int(340 * f), int(540 * f), int(460 * f), int(24 * f)))
        Screen.__init__(self, session)
        init_help(self)
        self.setTitle(_("CamAlert events"))
        self.events = list(Controller.instance.events) if Controller.instance else []
        self["list"] = MenuList([(present.event_line(e, _), i) for i, e in enumerate(self.events)]
                                or [(_("No events yet"), -1)])
        self["photo"] = Pixmap()
        self["info"] = Label("")
        self["key_red"] = StaticText(_("Close"))
        # a Label (not StaticText) so the empty green button can be hidden (#56); selected() shows it for clips
        self["key_green"] = Label(_("Play clip"))
        self["key_green"].hide()
        help_actions(self, "actions", "OkCancelActions", {
            "cancel": (self.close, _("Close")), "ok": (self.show_camera, _("Show this camera"))}, -1)
        help_actions(self, "colour_actions", "ColorActions", {
            "red": (self.close, _("Close")), "green": (self.play_clip, _("Play clip"))}, -1)
        self.picload = ePicLoad()
        self["list"].onSelectionChanged.append(self.selected)
        self.onLayoutFinish.append(self.selected)

    def current(self):
        sel = self["list"].getCurrent()
        return self.events[sel[1]] if sel and sel[1] >= 0 else None

    def clip_url(self, e):
        return frigate_clip_url(config.plugins.camalert.frigate_url.value, e.get("frigate_id") if e else None)

    def selected(self):
        e = self.current()
        if self.clip_url(e):  # GREEN only where there is a clip to play (#56)
            self["key_green"].show()
        else:
            self["key_green"].hide()
        if not e:
            return
        self["info"].setText("\n".join("%s: %s" % row for row in present.event_details(e, _, ui_language())))
        path = e.get("snapshot")
        if path and os.path.exists(path):
            self.picload.setPara((int(540 * self.f), int(304 * self.f), 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(path, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self["photo"].instance.setPixmap(ptr)
                    return
        self["photo"].instance.setPixmap(None)

    def show_camera(self):
        e = self.current()
        if e and Controller.instance:
            self.close()
            Controller.instance.show(e["camera"], None, None, "high", "menu")

    def play_clip(self):
        e = self.current()
        url = self.clip_url(e)
        if not url:
            return
        log("playing Frigate clip of event", e["frigate_id"])
        try:
            from Screens.InfoBar import MoviePlayer
            ref = eServiceReference(4097, 0, url)
            ref.setName("%s %s" % (e["camera"], e.get("label") or ""))
            self.session.open(MoviePlayer, ref)
        except Exception as ex:
            log("clip playback failed:", ex)


REPORT_QR = "/tmp/camalert-report-qr.png"


def _build_report():
    """(report, issue url, qr png path): in a thread (the camera list may need the network)."""
    from .server import BACKEND
    from .camalert_core import qr, report
    rep, url = report.make(BACKEND)
    with open(REPORT_QR, "wb") as f:
        f.write(qr.png(qr.encode(url, "M"), scale=6, border=4))
    return rep, url


class ReportScreen(Screen, HelpBase):
    """Report a problem (#132): a summary, a QR code that opens a pre-filled GitHub issue on a phone, and GREEN to
    save the full report (without secrets) next to the settings export."""

    def __init__(self, session):
        from .camalert_core import report
        f = self.f = getDesktop(0).size().width() / 1920.0
        self.skin = _skin("CamAlertReport", f,
                          '<widget name="text" position="%d,%d" size="%d,%d" font="Regular;%d" />'
                          '<widget name="qr" position="%d,%d" size="%d,%d" alphatest="on" />'
                          % (int(20 * f), int(20 * f), int(860 * f), int(800 * f), int(26 * f),
                             int(920 * f), int(40 * f), int(540 * f), int(540 * f)))
        Screen.__init__(self, session)
        init_help(self)
        self.setTitle(_(report.TITLE))
        self.report = None
        self["text"] = ScrollLabel(_("Checking..."))
        self["qr"] = Pixmap()
        self["key_red"] = StaticText(_("Close"))
        self["key_green"] = Label(_(report.SAVE))
        self.picload = ePicLoad()
        close, up, down = (self.close, _("Close")), (self["text"].pageUp, _("Scroll")), (self["text"].pageDown, _("Scroll"))
        help_actions(self, "actions", "OkCancelActions", {"cancel": close, "ok": close}, -1)
        help_actions(self, "colour_actions", "ColorActions", {"red": close, "green": (self.save, _(report.SAVE))}, -1)
        help_actions(self, "direction_actions", "DirectionActions", {"up": up, "down": down, "left": up, "right": down}, -1)
        self.onLayoutFinish.append(self.run)

    def run(self):
        threads.deferToThread(_build_report).addCallbacks(self.done, lambda e: self["text"].setText(str(e.value)))

    def done(self, result):
        from .camalert_core import report
        self.report = result[0]
        self["text"].setText("\n".join([_(report.HELP), ""] + report.summary(self.report)))
        size = int(540 * self.f)
        self.picload.setPara((size, size, 1, 1, False, 1, "#ffffffff"))
        if self.picload.startDecode(REPORT_QR, 0, 0, False) == 0:
            ptr = self.picload.getData()
            if ptr is not None:
                self["qr"].instance.setPixmap(ptr)

    def save(self):
        from Screens.MessageBox import MessageBox
        from .camalert_core import report
        from .settingsio import export_dir
        if self.report is None:
            return
        path = os.path.join(export_dir(), report.FILE_NAME)
        try:
            with open(path, "w") as f:
                f.write(report.text(self.report))
        except (IOError, OSError) as e:
            self.session.open(MessageBox, _(report.SAVE_FAILED) % e, MessageBox.TYPE_ERROR)
            return
        self.session.open(MessageBox, _(report.SAVED) % path, MessageBox.TYPE_INFO)
