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

from . import _
from Components.ActionMap import ActionMap

from .logic import (blocked_by_rules, clock_tuple, key_action, known_camera, neighbour, pick_priority, decide, display_name, grid, in_time_window, lowered_volume, normalize_server, parse_camera_file,
                    parse_cams, pick_mode, rtsp_url, service_ref, should_pause, snapshot_url, split_credentials,
                    stream_from_ref, tcp_url, window_geometry)

PHOTO = "/tmp/camalert.jpg"


def log(*args):
    print("[CamAlert]", *args)


CAMERA_FILE = "/etc/enigma2/camalert_cameras.conf"


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
    return rtsp_url(server, name, int(c.rtsp_port.value)), snapshot_url(server, name), display_name(name)


def all_camera_names():
    """Camera names in the current mode (go2rtc mode needs a network call; call from a thread)."""
    if config.plugins.camalert.source.value == "direct":
        return [cam["name"] for cam in direct_cameras()]
    from .setup import fetch_streams
    return fetch_streams(normalize_server(config.plugins.camalert.server.value))


def _download(url, path=PHOTO):
    with open_url(url) as r:
        data = r.read()
    with open(path + ".tmp", "wb") as f:
        f.write(data)
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
        threads.deferToThread(_download, self.url, self.path).addCallbacks(self.loaded, self.failed)

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
        reactor.callLater(0.3, self.fetch)

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
        self["title"] = Label(_("Cameras") + "  ·  " + _("EXIT = close"))
        self.tiles = []
        for i, ((name, title, url), (x, y, w, h)) in enumerate(zip(cams, tiles)):
            self["tile%d" % i] = Pixmap()
            self["label%d" % i] = Label(" " + title + " ")
            url = url.replace("width=640", "width=%d" % min(960, w)) if "/api/frame.jpeg" in url else url
            self.tiles.append(Tile(self, "tile%d" % i, name, url, (w, h)))
        self["actions"] = ActionMap(["OkCancelActions"], {"ok": self.close, "cancel": self.close}, -1)
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

    def __init__(self, session, stream, url, title=None, hint=False):
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t = window_geometry(c.position.value, c.size.value, size.width(), size.height())
        f = size.width() / 1920.0
        self.skin = """<screen name="CamAlertPhoto" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">
            <eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />
            <widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" zPosition="2" />
            <widget name="photo" position="0,%d" size="%d,%d" alphatest="off" zPosition="1" />
        </screen>""" % (x, y, w, h + t, w, h + t, int(10 * f), w - int(20 * f), t, int(26 * f), t, w, h)
        Screen.__init__(self, session)
        self.stream, self.url, self.size = stream, url, (w, h)
        self["title"] = Label((title or display_name(stream)) + ("   OK = live  < >  EXIT" if hint else ""))
        self["photo"] = Pixmap()
        self.picload = ePicLoad()
        self.busy = self.active = False
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
        threads.deferToThread(_download, self.url).addCallbacks(self.loaded, self.failed)

    def loaded(self, _result):
        self.busy = False
        if not getattr(self, "active", False):  # window closed meanwhile (Enigma2 clears closed screens)
            return
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(PHOTO, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self["photo"].instance.setPixmap(ptr)
        except Exception as e:
            log("showing photo failed:", e)
        reactor.callLater(0.2, self.fetch)

    def failed(self, err):
        self.busy = False
        log("snapshot failed:", err.getErrorMessage())
        if getattr(self, "active", False):
            reactor.callLater(2, self.fetch)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.hide()
        Controller.instance.window_closed(self)


class KeyHook(object):
    """Catches the remote while the photo window is open (only when the user is just watching TV).
    OK = live, LEFT/RIGHT = other camera, EXIT = close; volume keys pass; any other key closes the window and
    then does its normal job (zapping, numbers, menu)."""

    def __init__(self):
        self.swallow = set()
        eActionMap.getInstance().bindAction("", -0x7FFFFFFF, self.key)

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
            stream = ctl.window.stream if ctl.window else None
            if stream:
                reactor.callLater(0, ctl.window_to_live, stream)
        else:
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
        self["actions"] = ActionMap(["OkCancelActions", "DirectionActions", "ColorActions"], {
            "ok": self.toggle_hold, "cancel": self.close, "left": lambda: self.step(-1), "right": lambda: self.step(1),
            "green": self.live}, -1)
        self.onShown.append(self.started)
        self.onClose.append(self.stopped)

    def started(self):
        if not self.active:
            self.active = True
            self.load()

    def stopped(self):
        self.active = False
        self.timer.stop()

    def load(self):
        name, title, url = self.cams[self.index]
        state = _("hold") if self.hold else _("tour")
        self["title"].setText(" %s   (%d/%d, %s)   < >  OK  %s  EXIT " % (title, self.index + 1, len(self.cams), state, _("GREEN = live")))
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
        reactor.callLater(20, self.refresh_names)
        self.paused = False
        self.saved_volume = None
        self.keys = None
        self.notify_timer = eTimer()
        self.notify_timer.callback.append(self.resume_tv)

    # --- helpers -------------------------------------------------------------------------------------------
    def server(self):
        return normalize_server(config.plugins.camalert.server.value)

    def current_stream(self):
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        if not ref:
            return None
        direct = config.plugins.camalert.source.value == "direct"
        return stream_from_ref(ref.toString(), direct_cameras() if direct else None)

    # --- public ----------------------------------------------------------------------------------------------
    def show(self, stream=None, seconds=None, mode=None, priority=None):
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
                reactor.callLater(6, self.show, stream, seconds, mode, priority)
                return "wake"
            return "ignore"
        inStandby = None
        cams = parse_cams(stream)
        if len(cams) > 1:
            return self.mosaic(cams, seconds or int(c.duration.value))
        stream = stream or c.camera.value
        if not stream:
            log("no camera given and no default camera set")
            return "error"
        if not known_camera(stream, self._names):
            log("unknown camera:", stream)
            return "error"
        seconds = seconds or int(c.duration.value)
        mode = pick_mode(mode, c.mode.value)
        urls = camera_urls(stream)
        if not urls:
            log("unknown camera or no valid go2rtc address:", stream)
            return "error"
        live_url, snap_url, title = urls
        if mode == "photo" and not snap_url:
            mode = "live"  # camera has no snapshot address (direct mode)
        t = time.localtime()
        in_hours = in_time_window((t.tm_hour, t.tm_min), clock_tuple(c.from_time.value), clock_tuple(c.until_time.value))
        if blocked_by_rules(priority, c.limit_hours.value, in_hours, c.skip_recording.value,
                            bool(self.session.nav.getRecordings())):
            log("request", stream, "ignored by the receiver rules (active hours / recording)")
            return "ignore"
        window_stream = self.window.stream if self.window else (self.live_stream if mode == "live" else None)
        action = decide(inStandby is not None, self.current_stream() if self.live_stream is None else None,
                        window_stream, stream)
        log("request", stream, seconds, mode, "->", action)
        reactor.callLater(0.5, _notify)
        if action == "ignore":
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

    def _tv_on_top(self):
        """True when the user is just watching TV (no menu or other screen open)."""
        ib = self._infobar()
        return ib is not None and getattr(self.session, "current_dialog", None) is ib

    def close_keys(self):
        k, self.keys = self.keys, None
        if k is not None:
            k.remove()

    def window_to_live(self, stream):
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
        w["title"].setText(urls[2] + "   OK = live  < >  EXIT")
        w.extend(int(config.plugins.camalert.duration.value))

    def refresh_names(self):
        """Caches the camera list (go2rtc mode needs the network) for LEFT/RIGHT in the photo window."""
        def done(names):
            self._names = names
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
        return {"window": self.window.stream if self.window else None, "live": self.live_stream, "paused": self.paused}
