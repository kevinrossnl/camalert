# -*- coding: utf-8 -*-
# DoorCam - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 DoorCam developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The three ways to show a camera: photo window, switch to live stream, notification."""
import os
import ssl
import urllib.request

import time

from enigma import eTimer, ePicLoad, getDesktop, eServiceReference, eDVBVolumecontrol
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import config
from Tools import Notifications
from twisted.internet import reactor, threads

from . import _
from .logic import (decide, display_name, in_time_window, lowered_volume, normalize_server, pick_mode, rtsp_url,
                    service_ref, should_pause, snapshot_url, stream_from_ref, window_geometry)

PHOTO = "/tmp/doorcam.jpg"


def log(*args):
    print("[DoorCam]", *args)


def open_url(url, timeout=8):
    """urlopen that honours the 'check go2rtc certificate' setting for https addresses."""
    ctx = None
    if url.startswith("https://") and not config.plugins.doorcam.verify_ssl.value:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen(url, timeout=timeout, context=ctx)


def _download(url):
    with open_url(url) as r:
        data = r.read()
    with open(PHOTO + ".tmp", "wb") as f:
        f.write(data)
    os.replace(PHOTO + ".tmp", PHOTO)
    return True


class PhotoWindow(Screen):
    """Small always-on-top window that keeps fetching a fresh snapshot from go2rtc (about one every 1-2 s)."""

    def __init__(self, session, stream, url):
        c = config.plugins.doorcam
        size = getDesktop(0).size()
        x, y, w, h, t = window_geometry(c.position.value, c.size.value, size.width(), size.height())
        f = size.width() / 1920.0
        self.skin = """<screen name="DoorCamPhoto" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">
            <eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />
            <widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" zPosition="2" />
            <widget name="photo" position="0,%d" size="%d,%d" alphatest="off" zPosition="1" />
        </screen>""" % (x, y, w, h + t, w, h + t, int(10 * f), w - int(20 * f), t, int(26 * f), t, w, h)
        Screen.__init__(self, session)
        self.stream, self.url, self.size = stream, url, (w, h)
        self["title"] = Label(display_name(stream))
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
        if not self.active or self.busy:
            return
        self.busy = True
        threads.deferToThread(_download, self.url).addCallbacks(self.loaded, self.failed)

    def loaded(self, _result):
        self.busy = False
        if not self.active:
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
        if self.active:
            reactor.callLater(2, self.fetch)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.hide()
        Controller.instance.window_closed(self)


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
        self.paused = False
        self.saved_volume = None
        self.notify_timer = eTimer()
        self.notify_timer.callback.append(self.resume_tv)

    # --- helpers -------------------------------------------------------------------------------------------
    def server(self):
        return normalize_server(config.plugins.doorcam.server.value)

    def current_stream(self):
        ref = self.session.nav.getCurrentlyPlayingServiceReference()
        return stream_from_ref(ref.toString()) if ref else None

    # --- public ----------------------------------------------------------------------------------------------
    def show(self, stream=None, seconds=None, mode=None):
        from Screens.Standby import inStandby
        c = config.plugins.doorcam
        stream = stream or c.camera.value
        seconds = seconds or int(c.duration.value)
        mode = pick_mode(mode, c.mode.value)
        server = self.server()
        if not server:
            log("no valid go2rtc address configured")
            return "error"
        if c.limit_hours.value:
            t = time.localtime()
            if not in_time_window((t.tm_hour, t.tm_min), tuple(c.from_time.value), tuple(c.until_time.value)):
                log("request", stream, "outside active hours")
                return "ignore"
        if c.skip_recording.value and self.session.nav.getRecordings():
            log("request", stream, "ignored: recording in progress")
            return "ignore"
        window_stream = self.window.stream if self.window else (self.live_stream if mode == "live" else None)
        action = decide(inStandby is not None, self.current_stream() if self.live_stream is None else None,
                        window_stream, stream)
        log("request", stream, seconds, mode, "->", action)
        if action == "ignore":
            return action
        if action == "show" and not self.paused and should_pause(c.pause_tv.value, mode, self.current_stream() is not None):
            self.pause_tv()
        if mode == "photo":
            if action == "extend":
                self.window.extend(seconds)
            else:
                self.hide()
                self.window = self.session.instantiateDialog(PhotoWindow, stream, snapshot_url(server, stream))
                self.window.start(seconds)
        elif mode == "live":
            if action == "show":
                if self.live_stream is None:
                    cur = self.session.nav.getCurrentlyPlayingServiceOrGroup()
                    self.previous_ref = cur.toString() if cur else None
                url = rtsp_url(server, stream, int(c.rtsp_port.value))
                self.session.nav.playService(eServiceReference(service_ref(url, display_name(stream))))
                self.live_stream = stream
                self.lower_volume(int(c.live_volume.value))
            self.live_timer.start(seconds * 1000, True)
        else:
            Notifications.AddPopup(_("Camera: %s") % display_name(stream), MessageBox.TYPE_INFO, seconds,
                                   id="DoorCam")
            if self.paused:
                self.notify_timer.start(seconds * 1000, True)
        return action

    def _infobar(self):
        try:
            from Screens.InfoBar import InfoBar
            return InfoBar.instance
        except Exception:
            return None

    def pause_tv(self):
        """Pause the TV picture (starts timeshift on live TV, if the receiver supports it)."""
        ib = self._infobar()
        try:
            if ib is not None and hasattr(ib, "pauseService"):
                ib.pauseService()
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

    def hide(self):
        if self.window is not None:
            w, self.window = self.window, None
            w.active = False
            w.close_timer.stop()
            w.hide()
            self.session.deleteDialog(w)
        if self.live_stream is not None:
            self.end_live()
        self.notify_timer.stop()
        self.resume_tv()

    def window_closed(self, w):
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
        self.live_timer.stop()
        self.restore_volume()
        stream, self.live_stream = self.live_stream, None
        if stream and config.plugins.doorcam.live_return.value and self.previous_ref \
                and self.current_stream() == stream:
            self.session.nav.playService(eServiceReference(self.previous_ref))
        self.previous_ref = None

    def status(self):
        return {"window": self.window.stream if self.window else None, "live": self.live_stream, "paused": self.paused}
