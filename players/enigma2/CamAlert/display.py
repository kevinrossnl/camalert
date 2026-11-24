# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The three ways to show a camera: photo window, switch to live stream, notification."""
import os
import ssl
import urllib.request

import time

from enigma import eActionMap, eTimer, ePicLoad, getDesktop, eServiceReference, eDVBVolumecontrol
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import config
from Tools import Notifications
from twisted.internet import reactor, threads

from . import _, __version__
from .camalert_core.obs.camlog import LOG
from .camalert_core.devices import client as devices
from Components.ActionMap import ActionMap

from .camalert_core.access import url_target
from .camalert_core.cameras import (display_name, known_camera, live_stream_name, neighbour, parse_camera_file,
                                    parse_cams, parse_orientation, parse_refresh, parse_titles, refresh_delay, slug,
                                    title_for)
from .camalert_core import present
from .camalert_core.events import add_event, event_title
from .camalert_core.keymap import button_event
from .camalert_core.layout import grid, strip_geometry, title_font, window_geometry
from .camalert_core.obs.log import redact
from .camalert_core.obs.metrics import metrics_text
from .camalert_core.triggers.foscam import FoscamSource
from .camalert_core.rules import (blocked_by_rules, clock_tuple, cooldown_seconds, decide, dnd_blocks, in_cooldown,
                                  in_time_window, lowered_volume, pick_mode, pick_priority, should_pause)
from .camalert_core.update import latest_tag, newer_version, UPDATE_INTERVAL
from .camalert_core.urls import normalize_server, rtsp_url, snapshot_url, split_credentials, tcp_url, valid_port
from .keys import action_map_args, button_for, key_action, ptz_key
from .services import chime_command, github_repo, is_media_ref, service_ref, stream_from_ref

PHOTO = "/tmp/camalert.jpg"
# ◀ ▶ ▲ ▼ in key hints: skin fonts rarely have them, Enigma2 draws them with its fallback font (openATV, OpenPLi:
# /usr/share/fonts/fallback.font). Without that font the hints use < > ^ v.
GLYPHS = os.path.exists("/usr/share/fonts/fallback.font")


def hint(context, stream=None, without=()):
    """Translated key hint of a CamAlert screen, from the core key map (#41). without: hint labels to leave out."""
    c = config.plugins.camalert
    ctl = Controller.instance
    has_ptz = bool(stream) and ctl is not None and ctl.has_ptz(stream)
    text = present.key_hint("enigma2", context, _, ptz_key=c.ptz_key.value, has_ptz=has_ptz, glyphs=GLYPHS)
    skip = [" = " + _(label) for label in without]
    return present.SEPARATOR.join(p for p in text.split(present.SEPARATOR) if not any(p.endswith(s) for s in skip))


def window_hint(stream):
    return hint("window", stream)


def with_hint(title, text):
    return title + (present.SEPARATOR + text if text else "")


def log(*args, **kw):
    """Debug log of Enigma2 + camalert.log. level: error / normal / verbose (default: error if it failed)."""
    text = " ".join(str(a) for a in args)
    level = kw.get("level") or ("error" if "failed" in text or "error" in text.lower() else "normal")
    print("[CamAlert]", redact(text))
    LOG.write(level, text)
    if level == "error":
        STATS["errors"] += 1


CAMERA_FILE = "/etc/enigma2/camalert_cameras.conf"
STATS = {"errors": 0, "requests": {}, "started": time.time(), "last_event": 0, "unreachable": 0}


def open_url(url, timeout=8):
    """urlopen that honours the 'check certificate' setting and supports user:password@ (basic and digest)."""
    url, user, password = split_credentials(url)
    handlers = []
    if url.startswith("https://") and not config.plugins.camalert.verify_ssl.value:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    if user is not None:
        mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        mgr.add_password(None, url, user, password)
        handlers += [urllib.request.HTTPBasicAuthHandler(mgr), urllib.request.HTTPDigestAuthHandler(mgr)]
    return urllib.request.build_opener(*handlers).open(url, timeout=timeout)


def direct_cameras():
    """Cameras from the camera file (direct mode), or [] if the file is missing."""
    try:
        with open(CAMERA_FILE, encoding="utf-8") as f:
            return parse_camera_file(f.read())
    except OSError:
        return []


def camera_urls(name):
    """(live url, snapshot url or None, title) for a camera in the current mode; None if unknown."""
    c = config.plugins.camalert
    if c.source.value == "direct":
        for cam in direct_cameras():
            if cam["name"] == name:
                return tcp_url(cam["rtsp"]), cam["snapshot"], cam["title"]
        return None
    server = normalize_server(c.server.value)
    if not server:
        return None
    title = title_for(name, parse_titles(c.titles.value))
    return (rtsp_url(server, live_stream_name(name, c.substreams.value), valid_port(c.rtsp_port.value, 8554)),
            snapshot_url(server, name), title)


def trigger_settings():
    """The settings of the trigger sources (#6), with the keys camalert_core.triggers expects."""
    c = config.plugins.camalert
    return {"frigate_enabled": c.frigate_enabled.value, "frigate_prefix": c.frigate_prefix.value,
            "frigate_labels": c.frigate_labels.value, "frigate_map": c.frigate_map.value,
            "frigate_priority": c.frigate_priority.value, "frigate_mode": c.frigate_mode.value,
            "frigate_seconds": int(c.frigate_seconds.value),
            "foscam_enabled": c.foscam_enabled.value, "foscam_priority": c.foscam_priority.value,
            "foscam_mode": c.foscam_mode.value, "foscam_seconds": int(c.foscam_seconds.value),
            "foscam_label": _("Motion")}


def chime_wanted(setting, priority):
    """Doorbell chime: 'off', 'high' (doorbell and alarm) or 'all' requests (schema version 2, #39)."""
    return setting == "all" or (setting == "high" and priority in ("high", "alarm"))


def all_camera_names():
    """Camera names in the current mode (go2rtc mode needs a network call; call from a thread)."""
    if config.plugins.camalert.source.value == "direct":
        return [cam["name"] for cam in direct_cameras()]
    from .setup import fetch_streams
    return fetch_streams(normalize_server(config.plugins.camalert.server.value))


try:  # optional: python3-pillow turns/mirrors snapshots of cameras that hang upside down
    from PIL import Image
except Exception:  # pragma: no cover - not installed on every receiver
    Image = None


def pillow_available():
    return Image is not None


def orientation_for(name):
    return parse_orientation(config.plugins.camalert.orientation.value).get(name)


def delay_for(name, minimum=0.2):
    return refresh_delay(name, parse_refresh(config.plugins.camalert.refresh.value), minimum)


def _download(url, path=PHOTO, orientation=None):
    with open_url(url) as r:
        data = r.read()
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    if orientation and Image is not None:
        try:
            op = {"mirror": Image.FLIP_LEFT_RIGHT, "flip": Image.FLIP_TOP_BOTTOM, "rot180": Image.ROTATE_180}[orientation]
            with Image.open(path + ".tmp") as im:
                im.transpose(op).save(path + ".tmp", "JPEG", quality=85)
        except Exception as e:
            log("orientation failed:", e)
    os.replace(path + ".tmp", path)
    return path


class Tile(object):
    """One camera in the mosaic: keeps fetching snapshots into its own pixmap widget."""

    def __init__(self, screen, key, stream, url, size):
        self.screen, self.key, self.stream, self.url, self.size = screen, key, stream, url, size
        self.path = "/tmp/camalert_%s.jpg" % key
        self.picload = ePicLoad()
        self.busy = False

    def fetch(self):
        if not getattr(self.screen, "active", False) or self.busy or not self.url:
            return
        self.busy = True
        threads.deferToThread(_download, self.url, self.path, orientation_for(self.stream)).addCallbacks(
            self.loaded, self.failed)

    def loaded(self, _path):
        self.busy = False
        if not getattr(self.screen, "active", False) or not self.url:
            return
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(self.path, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self.screen[self.key].instance.setPixmap(ptr)
        except Exception as e:
            log("mosaic tile failed:", e)
        reactor.callLater(delay_for(self.stream, 0.3), self.fetch)

    def failed(self, err):
        self.busy = False
        if getattr(self.screen, "active", False):
            reactor.callLater(3, self.fetch)


class MosaicScreen(Screen):
    """Full-screen grid with up to 9 cameras (photo mode). Closes with EXIT/OK or after `seconds` (0 = stay open)."""

    def __init__(self, session, cams, seconds=0):
        """cams: list of (name, title, snapshot url)."""
        size = getDesktop(0).size()
        sw, sh = size.width(), size.height()
        tiles = grid(len(cams), sw, sh - int(50 * sw / 1920.0))
        f = sw / 1920.0
        top = int(50 * f)
        parts = ['<screen name="CamAlertMosaic" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#000000">' % (sw, sh),
                 '<widget name="title" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#000000" />'
                 % (int(20 * f), int(8 * f), sw - int(40 * f), int(36 * f), int(28 * f))]
        for i, (x, y, w, h) in enumerate(tiles):
            parts.append('<widget name="tile%d" position="%d,%d" size="%d,%d" alphatest="off" />' % (i, x, y + top, w, h))
            parts.append('<widget name="label%d" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" zPosition="2" />'
                         % (i, x + int(8 * f), y + top + int(8 * f), w // 2, int(34 * f), int(24 * f)))
        parts.append("</screen>")
        self.skin = "".join(parts)
        Screen.__init__(self, session)
        self["title"] = Label(_("Cameras") + present.SEPARATOR + hint("mosaic"))
        self.tiles = []
        for i, ((name, title, url), (x, y, w, h)) in enumerate(zip(cams, tiles)):
            self["tile%d" % i] = Pixmap()
            self["label%d" % i] = Label(" " + title + " ")
            url = url.replace("width=640", "width=%d" % min(960, w)) if "/api/frame.jpeg" in url else url
            self.tiles.append(Tile(self, "tile%d" % i, name, url, (w, h)))
        self["actions"] = ActionMap(*action_map_args("mosaic", {"close": self.close}), prio=-1)
        self.active = False
        self.timer = eTimer()
        self.timer.callback.append(self.close)
        self.seconds = seconds
        self.onShown.append(self.started)
        self.onClose.append(self.stopped)

    def started(self):
        if self.active:
            return
        self.active = True
        for t in self.tiles:
            t.fetch()
        if self.seconds:
            self.timer.start(self.seconds * 1000, True)

    def stopped(self):
        self.active = False
        self.timer.stop()


class PhotoWindow(Screen):
    """Small always-on-top window that keeps fetching a fresh snapshot from go2rtc (about one every 1-2 s)."""

    def __init__(self, session, stream, url, title=None, keys=False):
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t = window_geometry(c.position.value, c.size.value, size.width(), size.height(), c.title_size.value)
        f = size.width() / 1920.0
        self.skin = """<screen name="CamAlertPhoto" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">
            <eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />
            <widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" zPosition="2" />
            <widget name="photo" position="0,%d" size="%d,%d" alphatest="off" zPosition="1" />
        </screen>""" % (x, y, w, h + t, w, h + t, int(10 * f), w - int(20 * f), t, title_font(c.title_size.value, size.width()), t, w, h)
        Screen.__init__(self, session)
        self.stream, self.url, self.size = stream, url, (w, h)
        self.base_title = title or display_name(stream)
        self.title_text = with_hint(self.base_title, window_hint(stream) if keys else "")
        self["title"] = Label(self.title_text)
        self["photo"] = Pixmap()
        self.picload = ePicLoad()
        self.busy = self.active = False
        self.failures = 0
        self.close_timer = eTimer()
        self.close_timer.callback.append(self.stop)

    def start(self, seconds):
        self.active = True
        self.show()
        self.close_timer.start(seconds * 1000, True)
        self.fetch()

    def extend(self, seconds):
        self.close_timer.start(seconds * 1000, True)

    def fetch(self):
        if not getattr(self, "active", False) or self.busy:
            return
        self.busy = True
        threads.deferToThread(_download, self.url, PHOTO, orientation_for(self.stream)).addCallbacks(
            self.loaded, self.failed)

    def loaded(self, _result):
        self.busy = False
        if not getattr(self, "active", False):  # window closed meanwhile (Enigma2 clears closed screens)
            return
        if self.failures >= 2:
            self["title"].setText(self.title_text)
        self.failures = 0
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(PHOTO, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self["photo"].instance.setPixmap(ptr)
        except Exception as e:
            log("showing photo failed:", e)
        reactor.callLater(delay_for(self.stream), self.fetch)

    def failed(self, err):
        self.busy = False
        self.failures += 1
        if self.failures == 1:
            log("snapshot failed:", err.getErrorMessage())
        if not getattr(self, "active", False):
            return
        if self.failures == 2:  # show it instead of a black or frozen window
            STATS["unreachable"] += 1
            self["title"].setText(_("%s - camera not reachable") % self.base_title)
        reactor.callLater(2, self.fetch)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.hide()
        Controller.instance.window_closed(self)


class StripWindow(Screen):
    """One corner window with 2-4 cameras (below each other, next to each other or 2 x 2); TV stays visible."""

    def __init__(self, session, cams, keys=False, label=None):
        """cams: list of (name, title, snapshot url)."""
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t, tiles = strip_geometry(len(cams), c.strip_layout.value, c.position.value, c.size.value,
                                              size.width(), size.height())
        f = size.width() / 1920.0
        parts = ['<screen name="CamAlertStrip" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">' % (x, y, w, h + t),
                 '<eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />' % (w, h + t),
                 '<widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" zPosition="2" />'
                 % (int(10 * f), w - int(20 * f), t, min(title_font(c.title_size.value, size.width()), int(t * 0.8)))]
        for i, (tx, ty, tw, th) in enumerate(tiles):
            parts.append('<widget name="tile%d" position="%d,%d" size="%d,%d" alphatest="off" zPosition="1" />' % (i, tx, ty, tw, th))
            parts.append('<widget name="label%d" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" zPosition="3" />'
                         % (i, tx + int(6 * f), ty + int(6 * f), tw // 2, int(30 * f), int(22 * f)))
        parts.append("</screen>")
        self.skin = "".join(parts)
        Screen.__init__(self, session)
        self.names = [n for n, _t, _u in cams]
        self.stream = ",".join(self.names)
        self["title"] = Label(with_hint(event_title("  ·  ".join(t for _n, t, _u in cams), label),
                                        hint("window", self.names[0], without=("other camera",)) if keys else ""))
        self.tiles = []
        for i, ((name, title, url), (tx, ty, tw, th)) in enumerate(zip(cams, tiles)):
            self["tile%d" % i] = Pixmap()
            self["label%d" % i] = Label(" " + title + " ")
            url = url.replace("width=640", "width=%d" % min(960, tw)) if "/api/frame.jpeg" in url else url
            self.tiles.append(Tile(self, "tile%d" % i, name, url, (tw, th)))
        self.active = False
        self.close_timer = eTimer()
        self.close_timer.callback.append(self.stop)

    def start(self, seconds):
        self.active = True
        self.show()
        self.close_timer.start(seconds * 1000, True)
        for t in self.tiles:
            t.fetch()

    def extend(self, seconds):
        self.close_timer.start(seconds * 1000, True)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.hide()
        Controller.instance.window_closed(self)


def free_bytes(folder):
    try:
        st = os.statvfs(folder)
        return st.f_bavail * st.f_frsize
    except OSError:
        return 0


def metrics():
    """Prometheus metrics for /camalert/metrics."""
    ctl = Controller.instance
    st = ctl.status() if ctl else {}
    return metrics_text({
        "requests_total": ("counter", "Show requests by result", dict(STATS["requests"]) or {"show": 0}),
        "errors_total": ("counter", "Errors logged", STATS["errors"]),
        "unreachable_total": ("counter", "Times a camera was not reachable in the photo window", STATS["unreachable"]),
        "last_event_timestamp_seconds": ("gauge", "Time of the last request", STATS["last_event"]),
        "uptime_seconds": ("gauge", "Seconds since CamAlert started", time.time() - STATS["started"]),
        "on_screen": ("gauge", "1 while a camera is on screen", 1 if st.get("window") or st.get("live") else 0),
        "dnd": ("gauge", "Do not disturb on", 1 if st.get("dnd") else 0),
        "events": ("gauge", "Events in the event list", len(ctl.events) if ctl else 0),
    }, {"version": __version__})


def event_folder():
    folder = config.plugins.camalert.event_folder.value.strip() or "/tmp/camalert_events"
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = "/tmp"
    return folder


class PtzOverlay(Screen):
    """Small hint at the top of the screen while PTZ mode is on (does not take the remote)."""

    def __init__(self, session, text):
        size = getDesktop(0).size()
        f = size.width() / 1920.0
        w, h = int(1100 * f), int(56 * f)
        self.skin = ('<screen name="CamAlertPtz" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#202020" zPosition="12">'
                     '<widget name="text" position="0,0" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
                     'foregroundColor="#ffcc00" backgroundColor="#202020" /></screen>'
                     % ((size.width() - w) // 2, size.height() - h - int(60 * f), w, h, w, h, int(28 * f)))
        Screen.__init__(self, session)
        self["text"] = Label(text)


class GlobalKeys(object):
    """Always active, but only acts while a camera is on screen: colour keys go to Home Assistant (event), the PTZ
    key toggles PTZ mode for cameras with PTZ; in PTZ mode arrows move, CH+/CH- zoom, OK = home, EXIT = done."""

    def __init__(self):
        self.swallow = set()
        eActionMap.getInstance().bindAction("", -0x7FFFFFFF, self.key)

    def remove(self):
        try:
            eActionMap.getInstance().unbindAction("", self.key)
        except Exception:
            pass

    def key(self, code, flag):
        try:
            return self._key(code, flag)
        except Exception as e:
            log("key handling failed:", e)
            return 0

    def _key(self, code, flag):
        ctl = Controller.instance
        if ctl is None:
            return 0
        if code in self.swallow:
            if flag == 1:
                self.swallow.discard(code)
            elif flag == 2 and ctl.ptz_stream and ptz_key(code) in ("up", "down", "left", "right", "zoom_in", "zoom_out"):
                ctl.ptz_move(ptz_key(code))  # key held: keep moving
            return 1
        if flag != 0:
            return 0
        c = config.plugins.camalert
        if ctl.ptz_stream:
            action = ptz_key(code)
            if action == "pass":
                return 0  # volume keys
            if action is None and button_for(code, c.ptz_key.value, True) == "ptz":
                action = "leave"  # the configured PTZ key; other colour keys no longer leave (YELLOW did, #42)
            if action is None:
                return 1  # everything else is ignored in PTZ mode
            self.swallow.add(code)
            if action == "leave":
                reactor.callLater(0, ctl.leave_ptz)
            else:
                ctl.ptz_move(action)
            return 1
        cam, consume = ctl.camera_on_screen()
        if not cam:
            return 0
        what = button_for(code, c.ptz_key.value, ctl.has_ptz(cam), c.ha_buttons.value)
        if what is None:
            return 0
        if what == "ptz":
            self.swallow.add(code)
            reactor.callLater(0, ctl.enter_ptz, cam)
            return 1
        ctl.send_button(cam, what)
        if consume:
            self.swallow.add(code)
            return 1
        return 0


class KeyHook(object):
    """Catches the remote while the photo window is open (only when the user is just watching TV).
    OK = live, LEFT/RIGHT = other camera, EXIT = close; volume keys pass; any other key closes the window and
    then does its normal job (zapping, numbers, menu)."""

    def __init__(self):
        self.swallow = set()
        eActionMap.getInstance().bindAction("", -0x7FFFFFFE, self.key)  # after GlobalKeys (PTZ / colour keys)

    def remove(self):
        try:
            eActionMap.getInstance().unbindAction("", self.key)
        except Exception:
            pass

    def key(self, code, flag):
        if code in self.swallow:  # release / repeat of a key we handled
            if flag == 1:
                self.swallow.discard(code)
            return 1
        if flag != 0:
            return 0
        action = key_action(code)
        ctl = Controller.instance
        if action == "pass":
            return 0
        if action == "close_pass":
            reactor.callLater(0, ctl.hide)
            return 0
        self.swallow.add(code)
        if action == "close":
            reactor.callLater(0, ctl.hide)
        elif action == "live":
            stream = ctl.window.stream.split(",")[0] if ctl.window else None
            if stream:
                reactor.callLater(0, ctl.window_to_live, stream)
        elif not isinstance(ctl.window, StripWindow):
            ctl.other_camera(-1 if action == "prev" else 1)
        return 1


class TourScreen(Screen):
    """Full-screen camera tour: shows one camera after the other. LEFT/RIGHT = previous/next, OK = hold,
    GREEN = live, EXIT = close."""

    def __init__(self, session, cams, interval):
        size = getDesktop(0).size()
        sw, sh = size.width(), size.height()
        f = sw / 1920.0
        self.skin = """<screen name="CamAlertTour" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#000000">
            <widget name="tile0" position="0,0" size="%d,%d" alphatest="off" />
            <widget name="title" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" zPosition="2" />
        </screen>""" % (sw, sh, sw, sh, int(30 * f), int(20 * f), sw - int(60 * f), int(46 * f), int(30 * f))
        Screen.__init__(self, session)
        self.cams, self.index, self.hold, self.interval = cams, 0, False, interval
        self["tile0"] = Pixmap()
        self["title"] = Label("")
        self.active = False
        self.tile = None
        self.timer = eTimer()
        self.timer.callback.append(lambda: self.step(1, auto=True))
        self["actions"] = ActionMap(*action_map_args("tour", {
            "hold": self.toggle_hold, "close": self.close, "prev": lambda: self.step(-1), "next": lambda: self.step(1),
            "live": self.live}), prio=-1)
        self.onShown.append(self.started)
        self.onClose.append(self.stopped)

    def current_camera(self):
        return self.cams[self.index][0] if self.cams else None

    def started(self):
        if not self.active:
            self.active = True
            self.load()

    def stopped(self):
        self.active = False
        self.timer.stop()

    def load(self):
        name, title, url = self.cams[self.index]
        self["title"].setText(" %s " % with_hint(present.tour_status(title, self.index + 1, len(self.cams), self.hold, _),
                                                  hint("tour", name)))
        size = getDesktop(0).size()
        url = url.replace("width=640", "width=1280") if "/api/frame.jpeg" in url else url
        self.tile = Tile(self, "tile0", name, url, (size.width(), size.height()))
        self.tile.fetch()
        if not self.hold:
            self.timer.start(self.interval * 1000, True)

    def step(self, delta, auto=False):
        if auto and self.hold:
            return
        self.timer.stop()
        if self.tile:
            self.tile.url = None
        self.index = (self.index + delta) % len(self.cams)
        self.load()

    def toggle_hold(self):
        self.hold = not self.hold
        self.timer.stop()
        self.load()

    def live(self):
        name = self.cams[self.index][0]
        self.close()
        Controller.instance.show(name, None, "live", "high")


def _notify():
    try:
        from . import mqtt
        mqtt.state_changed()
    except Exception:
        pass


class Controller(object):
    """Keeps track of what is on screen and handles show/hide requests."""
    instance = None

    def __init__(self, session):
        Controller.instance = self
        self.session = session
        self.window = None
        self.live_stream = None
        self.previous_ref = None
        self.live_timer = eTimer()
        self.live_timer.callback.append(self.end_live)
        self._names = []
        self._names_at = 0
        reactor.callLater(20, self.refresh_names)
        self.paused = False
        self.saved_volume = None
        self.keys = None
        self.notify_timer = eTimer()
        self.notify_timer.callback.append(self.resume_tv)
        self.events = []
        self.last_shown = {}
        self.reason = ""
        self.label = None
        self.last_caller = None  # (time, address, source) of the last API call
        self.devices = {}
        self.devices_mtime = None
        self.alarms = {}
        self.ptz_stream = None
        self.ptz_hook = None
        self.ptz_overlay = None
        self.poll_timer = eTimer()
        self.poll_timer.callback.append(self.poll_devices)
        self.poll_seconds = self.poll_interval()
        self.poll_timer.start(self.poll_seconds * 1000, False)
        self.button_hook = GlobalKeys()
        c = config.plugins.camalert
        LOG.configure(c.log_level.value, c.log_syslog.value)
        c.log_level.addNotifier(lambda _e: LOG.configure(c.log_level.value, c.log_syslog.value), initial_call=False)
        c.log_syslog.addNotifier(lambda _e: LOG.configure(c.log_level.value, c.log_syslog.value), initial_call=False)
        log("CamAlert %s started" % __version__)
        self.update_timer = eTimer()
        self.update_timer.callback.append(self.check_update)
        self.update_timer.start(180 * 1000, True)

    # --- helpers -------------------------------------------------------------------------------------------
    def server(self):
        return normalize_server(config.plugins.camalert.server.value)

    def current_stream(self):
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if not ref:
            return None
        direct = config.plugins.camalert.source.value == "direct"
        return stream_from_ref(ref.toString(), direct_cameras() if direct else None)

    def playing_media(self):
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        return bool(ref) and is_media_ref(ref.toString())

    def playing(self, setting):
        """Whether 'Not while playing' applies now: 'video' = a recording or video file plays, 'all' = anything
        plays (also a TV channel; a camera channel does not count)."""
        if setting == "video":
            return self.playing_media()
        if setting == "all":
            ref = self.session.nav.getCurrentlyPlayingServiceReference()
            return bool(ref) and self.current_stream() is None
        return False

    @staticmethod
    def poll_interval():
        """Foscam check interval in seconds (1-60, default 2)."""
        try:
            return max(1, min(60, int(config.plugins.camalert.foscam_interval.value)))
        except (TypeError, ValueError):
            return 2

    def blocked(self, priority, what):
        """Receiver rules: do not disturb, active hours, recording, media playback. Logs and returns True if blocked."""
        c = config.plugins.camalert
        if dnd_blocks(priority, c.dnd.value, c.dnd_level.value):
            self.reason = present.reason("dnd")
            return True
        t = time.localtime()
        in_hours = in_time_window((t.tm_hour, t.tm_min), clock_tuple(c.from_time.value), clock_tuple(c.until_time.value))
        recording, media = bool(self.session.nav.getRecordings()), self.playing(c.skip_playing.value)
        if blocked_by_rules(priority, c.limit_hours.value, in_hours, c.skip_recording.value, recording,
                            c.skip_playing.value != "off", media):
            self.reason = present.reason("outside_hours" if c.limit_hours.value and not in_hours else
                                         "recording" if c.skip_recording.value and recording else "playing")
            return True
        return False

    def set_dnd(self, on):
        c = config.plugins.camalert
        c.dnd.value = bool(on)
        c.dnd.save()
        try:
            from Components.config import configfile
            configfile.save()
        except Exception:
            pass
        log("do not disturb", "on" if on else "off")
        reactor.callLater(0.1, _notify)

    # --- public ----------------------------------------------------------------------------------------------
    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        """Handles a show request and logs it (source, decision and reason) in camalert.log and the event list."""
        self.reason, self.label = "", (label or "").strip()[:40] or None
        cam = stream or config.plugins.camalert.camera.value
        wait = cooldown_seconds(cam, config.plugins.camalert.cooldown.value)
        on_screen = (self.window.stream if self.window else None) == cam
        try:
            if not on_screen and pick_priority(priority) != "alarm" and in_cooldown(self.last_shown.get(cam), time.time(), wait):
                self.reason, result = present.reason("cooldown", wait), "ignore"
            else:
                result = self._show(stream, seconds, mode, priority)
        finally:
            self.label = None
        if result == "show":
            self.last_shown[cam] = time.time()
        STATS["requests"][result] = STATS["requests"].get(result, 0) + 1
        STATS["last_event"] = time.time()
        log("request from %s: camera=%s priority=%s mode=%s label=%s -> %s%s"
            % (source, cam, pick_priority(priority), mode or "-", label or "-", result,
               (" (%s)" % self.reason) if self.reason else ""), level="error" if result == "error" else "normal")
        self.record_event(cam, label, source, pick_priority(priority), result, self.reason, event_id)
        if result == "show" and chime_wanted(config.plugins.camalert.chime.value, pick_priority(priority)):
            self.chime()
        return result

    def chime(self):
        path = os.path.join(os.path.dirname(__file__), "chime.wav")
        if not os.path.exists(path):
            return
        try:
            import subprocess
            subprocess.Popen(chime_command(path), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("chime", level="verbose")
        except OSError as e:
            log("chime failed:", e)

    def record_event(self, cam, label, source, priority, action, reason, event_id=None):
        ev = {"time": time.time(), "camera": cam, "label": label or "", "source": source, "priority": priority,
              "action": action, "reason": reason, "snapshot": None, "frigate_id": event_id}
        for old in add_event(self.events, ev):
            if old.get("snapshot"):
                try:
                    os.remove(old["snapshot"])
                except OSError:
                    pass
        first = (cam or "").split(",")[0]
        urls = camera_urls(first) if first and action in ("show", "extend", "wake") else None
        if urls and urls[1] and free_bytes(event_folder()) > 8 * 1024 * 1024:  # low storage: no snapshots
            folder = event_folder()
            path = os.path.join(folder, "%d_%s.jpg" % (int(ev["time"]), slug(first)))
            url = urls[1].replace("width=640", "width=320")

            def saved(_p):
                ev["snapshot"] = path
            threads.deferToThread(_download, url, path, orientation_for(first)).addCallbacks(
                saved, lambda e: log("event snapshot failed:", e.getErrorMessage(), level="verbose"))

    def _show(self, stream=None, seconds=None, mode=None, priority=None):
        from Screens import Standby
        c = config.plugins.camalert
        priority = pick_priority(priority)
        if Standby.inStandby is not None:
            if priority == "alarm" and c.alarm_wake.value:
                log("alarm: waking the receiver")
                try:
                    Standby.inStandby.Power()
                except Exception as e:
                    log("wake failed:", e)
                    return "ignore"
                reactor.callLater(6, self.show, stream, seconds, mode, priority, "wake")
                self.reason = present.reason("woken")
                return "wake"
            self.reason = present.reason("standby")
            return "ignore"
        inStandby = None
        cams = parse_cams(stream)
        if len(cams) > 1:
            if self.blocked(priority, ",".join(cams)):
                return "ignore"
            if len(cams) <= 4 and pick_mode(mode, c.mode.value) in ("photo", "strip") or mode == "strip":
                return self.strip(cams[:4], seconds or int(c.duration.value))
            return self.mosaic(cams, seconds or int(c.duration.value))
        stream = stream or c.camera.value
        if not stream:
            log("no camera given and no default camera set")
            self.reason = present.reason("no_camera")
            return "error"
        fresh = time.time() - self._names_at < 60
        if not known_camera(stream, self._names if fresh else []):
            self.reason = present.reason("unknown_camera")
            return "error"
        if not fresh:
            self.refresh_names()  # camera list older than a minute: refresh it in the background
        seconds = seconds or int(c.duration.value)
        mode = pick_mode(mode, c.mode.value)
        urls = camera_urls(stream)
        if not urls:
            self.reason = present.reason("no_address")
            return "error"
        live_url, snap_url, title = urls
        title = event_title(title, self.label)
        if mode == "photo" and not snap_url:
            mode = "live"  # camera has no snapshot address (direct mode)
        if self.blocked(priority, stream):
            return "ignore"
        window_stream = self.window.stream if self.window else (self.live_stream if mode == "live" else None)
        action = decide(inStandby is not None, self.current_stream() if self.live_stream is None else None,
                        window_stream, stream)
        log("request", stream, seconds, mode, "->", action, level="verbose")
        reactor.callLater(0.5, _notify)
        if action == "ignore":
            self.reason = present.reason("on_screen")
            return action
        pause = action == "show" and not self.paused and \
            should_pause(c.pause_tv.value, mode, self.current_stream() is not None)
        if mode == "photo":
            if action == "extend":
                self.window.extend(seconds)
            else:
                self.hide(resume=False)  # replace an open window, keep a running pause
                if pause:
                    self.pause_tv()
                keys = c.window_keys.value and self._tv_on_top()
                self.window = self.session.instantiateDialog(PhotoWindow, stream, snap_url, title, keys)
                self.window.start(seconds)
                if keys:
                    self.close_keys()
                    self.keys = KeyHook()
        elif mode == "live":
            if action == "show":
                if self.live_stream is None:
                    cur = self.session.nav.getCurrentlyPlayingServiceOrGroup()
                    self.previous_ref = cur.toString() if cur else None
                self.session.nav.playService(eServiceReference(service_ref(live_url, title)))
                self.live_stream = stream
                if priority != "alarm":
                    self.lower_volume(int(c.live_volume.value))
            self.live_timer.start(seconds * 1000, True)
        else:
            if pause:
                self.pause_tv()
            Notifications.AddPopup(_("Camera: %s") % title, MessageBox.TYPE_INFO, seconds,
                                   id="CamAlert")
            if self.paused:
                self.notify_timer.start(seconds * 1000, True)
        return action

    def strip(self, names, seconds):
        """2-4 cameras in one corner window (photo mode); falls back to the mosaic without snapshots."""
        cams = [(n, u[2], u[1]) for n, u in ((n, camera_urls(n)) for n in names) if u and u[1]]
        if len(cams) < 2:
            return self.show(cams[0][0], seconds, "photo", "high") if cams else "error"
        key = ",".join(n for n, _t, _u in cams)
        if self.window is not None and self.window.stream == key:
            self.window.extend(seconds)
            return "extend"
        self.hide(resume=False)
        keys = config.plugins.camalert.window_keys.value and self._tv_on_top()
        self.window = self.session.instantiateDialog(StripWindow, cams, keys, self.label)
        self.window.start(seconds)
        if keys:
            self.close_keys()
            self.keys = KeyHook()
        reactor.callLater(0.5, _notify)
        log("strip", key, seconds)
        return "show"

    def _streams(self, streams, then):
        """Resolves the camera list (argument, 'mosaic cameras' setting, or all cameras via a thread) and calls
        then(list). Returns 'show' or 'error'."""
        if isinstance(streams, str):
            streams = parse_cams(streams)
        streams = streams or parse_cams(config.plugins.camalert.mosaic.value)
        if streams:
            return then(streams)
        if self._names:
            return then(self._names[:9])

        def fetched(names):
            self._names = names
            self._names_at = time.time()
            then(names[:9])
        threads.deferToThread(all_camera_names).addCallbacks(fetched, lambda e: log("no cameras:", e.getErrorMessage()))
        return "show"

    def mosaic(self, streams=None, seconds=0):
        """Opens the photo mosaic (up to 9 cameras)."""
        from Screens.Standby import inStandby
        if inStandby is not None:
            return "ignore"

        def open_it(names):
            tiles = [(s, u[2], u[1]) for s, u in ((s, camera_urls(s)) for s in names) if u and u[1]]
            if not tiles:
                log("mosaic: no cameras with a snapshot address")
                return "error"
            self.session.open(MosaicScreen, tiles[:9], seconds)
            return "show"
        return self._streams(streams, open_it)

    # --- camera devices: Foscam alarms, PTZ ------------------------------------------------------------------------
    def load_devices(self):
        try:
            mtime = os.path.getmtime(devices.DEVICES_FILE)
        except OSError:
            mtime = None
        if mtime != self.devices_mtime:
            self.devices_mtime = mtime
            self.devices = devices.load_devices()
            if self.devices:
                log("devices file: %d cameras (%s)" % (len(self.devices), ", ".join(
                    "%s=%s" % (n, d["type"]) for n, d in sorted(self.devices.items()))))
        return self.devices

    def poll_devices(self):
        c = config.plugins.camalert
        if self.poll_interval() != self.poll_seconds:  # 'Check every (seconds)' changed
            self.poll_seconds = self.poll_interval()
            self.poll_timer.start(self.poll_seconds * 1000, False)
        source = FoscamSource(trigger_settings())
        if not c.enabled.value or not source.enabled():
            return
        for name, dev in source.devices(self.load_devices()).items():
            if self.alarms.get(name) == "busy":
                continue
            previous = self.alarms.get(name, False)
            self.alarms[name] = "busy"

            def done(alarm, name=name, previous=previous):
                self.alarms[name] = alarm
                trig = source.check(name, previous, alarm)
                if trig:
                    self.show(*trig.show_args())

            def failed(err, name=name, previous=previous):
                self.alarms[name] = previous
                if previous is not None:  # log once, not every 2 seconds
                    log("Foscam %s: %s" % (name, err.getErrorMessage()), level="error")
                self.alarms[name] = None
            threads.deferToThread(source.poll, dev).addCallbacks(done, failed)

    def has_ptz(self, name):
        return bool(name) and name in self.load_devices()

    def camera_on_screen(self):
        """(camera name, True if colour keys should be swallowed) while a camera is shown, else (None, False)."""
        if self.window is not None:
            return self.window.stream.split(",")[0], True
        dialog = getattr(self.session, "current_dialog", None)
        if isinstance(dialog, (MosaicScreen, TourScreen)):
            return getattr(dialog, "current_camera", lambda: "mosaic")(), False
        stream = self.live_stream or self.current_stream()
        if stream and self._tv_on_top():
            return stream, True
        return None, False

    def enter_ptz(self, name):
        if self.window is not None:
            self.window.extend(120)
        self.ptz_stream = name
        self.ptz_overlay = self.session.instantiateDialog(
            PtzOverlay, "%s: %s   %s" % (_("Camera control (PTZ)"), display_name(name), hint("ptz", name)))
        self.ptz_overlay.show()
        log("PTZ mode on:", name)

    def leave_ptz(self):
        if self.ptz_overlay is not None:
            self.ptz_overlay.hide()
            self.session.deleteDialog(self.ptz_overlay)
            self.ptz_overlay = None
        if self.ptz_stream:
            log("PTZ mode off:", self.ptz_stream)
        self.ptz_stream = None
        if self.window is not None:
            self.window.extend(int(config.plugins.camalert.duration.value))

    def ptz_move(self, action, name=None):
        name = name or self.ptz_stream
        dev = self.load_devices().get(name)
        if not dev or self.alarms.get(("ptz", name)):
            return False
        self.alarms[("ptz", name)] = True
        if self.window is not None:
            self.window.extend(120)

        def done(_r):
            self.alarms[("ptz", name)] = False

        def failed(err):
            self.alarms[("ptz", name)] = False
            log("PTZ %s %s failed: %s" % (name, action, err.getErrorMessage()), level="error")
        threads.deferToThread(devices.ptz, dev, action).addCallbacks(done, failed)
        log("PTZ", name, action, level="verbose")
        return True

    # --- update check (at most once a day, GitHub releases) ------------------------------------------------------
    def check_update(self):
        self.update_timer.start(6 * 3600 * 1000, True)
        c = config.plugins.camalert
        try:
            last = float(c.update_checked.value or 0)
        except ValueError:
            last = 0
        if not c.update_check.value or time.time() - last < UPDATE_INTERVAL:
            return

        def fetch():
            control = open("/var/lib/opkg/info/enigma2-plugin-extensions-camalert.control").read()
            repo = github_repo(control) or "kevinrossnl/camalert"
            req = urllib.request.Request("https://api.github.com/repos/%s/releases/latest" % repo,
                                         headers={"Accept": "application/vnd.github+json",
                                                  "User-Agent": "CamAlert/%s" % __version__})
            with urllib.request.urlopen(req, timeout=15) as r:
                return latest_tag(r.read().decode("utf-8", "replace"))

        def done(tag):
            c.update_checked.value = str(int(time.time()))
            c.update_checked.save()
            new = newer_version(__version__, tag)
            log("update check: installed %s, latest %s" % (__version__, tag or "-"))
            if new and new != c.update_seen.value:
                c.update_seen.value = new
                c.update_seen.save()
                text = _("CamAlert %s is available (installed: %s).\nUpdate via the software update or: opkg update && opkg upgrade")
                Notifications.AddPopup(text % (new, __version__), MessageBox.TYPE_INFO, 20, id="CamAlertUpdate")
        threads.deferToThread(fetch).addCallbacks(done, lambda e: log("update check failed:", e.getErrorMessage(),
                                                                     level="verbose"))

    # --- colour buttons -> Home Assistant -------------------------------------------------------------------------
    def send_button(self, camera, button):
        from . import mqtt
        log("button %s on camera %s -> Home Assistant" % (button, camera))
        mqtt.publish_button(camera, button)
        hook = config.plugins.camalert.ha_webhook.value.strip()
        if hook:
            from .mqtt import node_id
            body = button_event(node_id(), camera, button).encode("utf-8")

            def post():
                why = url_target(hook)  # checked again on use: a host name may resolve elsewhere now (#53)
                if why:
                    raise ValueError(why)
                req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status
            threads.deferToThread(post).addErrback(lambda e: log("button webhook failed:", e.getErrorMessage()))

    def _tv_on_top(self):
        """True when the user is just watching TV (no menu or other screen open)."""
        ib = self._infobar()
        return ib is not None and getattr(self.session, "current_dialog", None) is ib

    def close_keys(self):
        k, self.keys = self.keys, None
        if k is not None:
            k.remove()

    def window_to_live(self, stream):
        self.leave_ptz()
        self.hide()
        self.show(stream, None, "live", "high")

    def other_camera(self, step):
        """LEFT/RIGHT in the photo window: show the previous/next camera."""
        if self.window is None:
            return
        try:
            names = all_camera_names() if config.plugins.camalert.source.value == "direct" else self._names
        except Exception:
            names = []
        target = neighbour(names, self.window.stream, step)
        urls = camera_urls(target) if target else None
        if not urls or not urls[1]:
            return
        w = self.window
        w.stream, w.url = target, urls[1]
        w.base_title = urls[2]
        w.title_text = with_hint(urls[2], window_hint(target))
        w["title"].setText(w.title_text)
        w.extend(int(config.plugins.camalert.duration.value))

    def refresh_names(self):
        """Caches the camera list (go2rtc mode needs the network) for LEFT/RIGHT in the photo window."""
        def done(names):
            self._names = names
            self._names_at = time.time()
        threads.deferToThread(all_camera_names).addCallbacks(done, lambda e: None)

    def tour(self, streams=None, interval=None):
        from Screens.Standby import inStandby
        if inStandby is not None:
            return "ignore"

        def open_it(names):
            cams = [(s, u[2], u[1]) for s, u in ((s, camera_urls(s)) for s in names) if u and u[1]]
            if not cams:
                return "error"
            self.session.open(TourScreen, cams, interval or int(config.plugins.camalert.tour_interval.value))
            return "show"
        return self._streams(streams, open_it)

    def _infobar(self):
        try:
            from Screens.InfoBar import InfoBar
            return InfoBar.instance
        except Exception:
            return None

    def pause_tv(self):
        """Pause the TV picture (starts timeshift on live TV, if the receiver supports it)."""
        ib = self._infobar()
        if ib is None:
            return
        try:
            service = self.session.nav.getCurrentService()
            seek = service and service.seek()
            if (seek is None or not seek.isCurrentlySeekable()) and hasattr(ib, "startTimeshift"):
                ib.startTimeshift()  # live TV: start timeshift and pause (like the PAUSE key)
            elif hasattr(ib, "pauseService"):
                ib.pauseService()
            else:
                return
            self.paused = True
        except Exception as e:
            log("pause failed:", e)

    def resume_tv(self):
        if not self.paused:
            return
        self.paused = False
        ib = self._infobar()
        try:
            if ib is not None and hasattr(ib, "unPauseService"):
                ib.unPauseService()
        except Exception as e:
            log("resume failed:", e)

    def hide(self, resume=True):
        self.close_keys()
        if self.ptz_stream:
            self.leave_ptz()
        if self.window is not None:
            w, self.window = self.window, None
            w.active = False
            w.close_timer.stop()
            w.hide()
            self.session.deleteDialog(w)
        if self.live_stream is not None:
            self.end_live()
        if resume:
            self.notify_timer.stop()
            self.resume_tv()

    def window_closed(self, w):
        reactor.callLater(0.1, _notify)
        self.close_keys()
        if self.ptz_stream:
            self.leave_ptz()
        if self.window is w:
            self.window = None
            self.session.deleteDialog(w)
            self.resume_tv()

    def lower_volume(self, percent):
        if percent >= 100 or self.saved_volume is not None:
            return
        try:
            vc = eDVBVolumecontrol.getInstance()
            self.saved_volume = vc.getVolume()
            v = lowered_volume(self.saved_volume, percent)
            vc.setVolume(v, v)
        except Exception as e:
            log("volume failed:", e)

    def restore_volume(self):
        if self.saved_volume is None:
            return
        try:
            vc = eDVBVolumecontrol.getInstance()
            vc.setVolume(self.saved_volume, self.saved_volume)
        except Exception as e:
            log("volume restore failed:", e)
        self.saved_volume = None

    def end_live(self):
        reactor.callLater(0.1, _notify)
        self.live_timer.stop()
        self.restore_volume()
        stream, self.live_stream = self.live_stream, None
        if stream and config.plugins.camalert.live_return.value and self.previous_ref \
                and self.current_stream() == stream:
            self.session.nav.playService(eServiceReference(self.previous_ref))
        self.previous_ref = None

    def status(self):
        return {"window": self.window.stream if self.window else None, "live": self.live_stream, "paused": self.paused,
                "dnd": bool(config.plugins.camalert.dnd.value)}
