# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Keep cameras ready (#111): a warm MJPEG feed per chosen camera while the player is on.

go2rtc's frame.jpeg waits for the next keyframe (2-5 s with many cameras). For the cameras in the setting
*Keep cameras ready* (``front_door=front_door_jpeg|garden``) the player keeps go2rtc's ``stream.mjpeg`` of that
stream open and keeps only the last picture, so the photo window shows it at once. Only while the player is on:
in standby, with the screen off or with CamAlert off the connection is closed, and when no player watches the
stream any more go2rtc stops transcoding by itself (do not put the stream in go2rtc's ``preload``).

Plain Python 3.8 with threads (Enigma2, Kodi); the Android TV app has the same logic in Kotlin.
"""
import threading
import time

from .i18n import N_
from .urls import normalize_server
try:
    from urllib.parse import quote
except ImportError:  # pragma: no cover
    from urllib import quote

STALE_SECONDS = 5.0  # an older warm picture is not used (the feed stalled): the next source is asked
RETRY = (1, 2, 5, 10, 30)  # seconds between connection attempts after an error
MAX_FRAME = 4 * 1024 * 1024  # a part larger than this is not a camera picture: reconnect


def parse_ready(text):
    """'front_door=front_door_jpeg|garden' -> {'front_door': 'front_door_jpeg', 'garden': 'garden'}; empty = {}."""
    out = {}
    for part in (text or "").replace(",", "|").split("|"):
        part = part.strip()
        if not part:
            continue
        cam, sep, stream = part.partition("=")
        cam, stream = cam.strip(), (stream.strip() if sep else cam.strip())
        if cam and stream:
            out[cam] = stream
    return out


def mjpeg_url(server, stream):
    """go2rtc's MJPEG stream of a stream name, or None without a valid server."""
    base = normalize_server(server or "")
    if not base or not stream:
        return None
    return "%s/api/stream.mjpeg?src=%s" % (base, quote(stream, safe="_.-"))


class MjpegParser(object):
    """Splits a multipart MJPEG byte stream (go2rtc: ``--frame`` parts with Content-Length) into pictures.
    Parts without Content-Length are cut at the next boundary line."""

    def __init__(self):
        self.buf = b""

    def feed(self, data):
        """Adds bytes; returns the complete pictures found (oldest first). Raises ValueError on garbage."""
        self.buf += data
        out = []
        while True:
            i = self.buf.find(b"--")
            if i < 0:
                if len(self.buf) > MAX_FRAME:
                    raise ValueError("no MJPEG boundary")
                return out
            head_end = self.buf.find(b"\r\n\r\n", i)
            if head_end < 0:
                if len(self.buf) - i > 8192:
                    raise ValueError("MJPEG part header too long")
                self.buf = self.buf[i:]
                return out
            headers = self.buf[i:head_end].decode("latin-1").split("\r\n")[1:]
            length = None
            for h in headers:
                k, _sep, v = h.partition(":")
                if k.strip().lower() == "content-length":
                    try:
                        length = int(v.strip())
                    except ValueError:
                        raise ValueError("bad Content-Length")
            start = head_end + 4
            if length is None:
                nxt = self.buf.find(b"\r\n--", start)
                if nxt < 0:
                    if len(self.buf) - start > MAX_FRAME:
                        raise ValueError("MJPEG part too large")
                    self.buf = self.buf[i:]
                    return out
                end = nxt
            else:
                if length > MAX_FRAME:
                    raise ValueError("MJPEG part too large")
                end = start + length
                if len(self.buf) < end:
                    self.buf = self.buf[i:]
                    return out
            out.append(self.buf[start:end])
            self.buf = self.buf[end:]


class WarmFeeds(object):
    """The warm feeds of one player. open_stream(url) -> object with read(n) and close() (the player's own HTTP
    open: certificate setting, user:password@). update(server, ready_text, active) is called by the player at
    least once a second; frame(camera) gives the last picture when it is fresh."""

    def __init__(self, open_stream, clock=time.time, sleep=time.sleep, start=None, chunk=65536):
        self.open_stream = open_stream
        self.clock = clock
        self.sleep = sleep
        self.chunk = chunk
        self.start = start or (lambda fn: threading.Thread(target=fn, daemon=True).start())
        self.lock = threading.Lock()
        self.urls = {}  # camera -> mjpeg url
        self.active = False
        self.gen = 0  # every change ends the running readers
        self.frames = {}  # camera -> (bytes, time)
        self.streams = {}  # camera -> open stream (closed to stop a blocked read)
        self.errors = {}  # camera -> short error text
        self.running = set()

    def update(self, server, ready_text, active):
        """Configures the feeds and switches them on or off; cheap when nothing changed."""
        urls = {}
        for cam, stream in sorted(parse_ready(ready_text).items()):
            u = mjpeg_url(server, stream)
            if u:
                urls[cam] = u
        active = bool(active and urls)
        with self.lock:
            if urls == self.urls and active == self.active:
                return
            self.urls, self.active = urls, active
            self.gen += 1
            gen = self.gen
            old = list(self.streams.values())
            self.streams = {}
            if not active:
                self.frames, self.errors = {}, {}
        for s in old:
            _close(s)
        if active:
            for cam, url in urls.items():
                self.start(lambda cam=cam, url=url: self._run(cam, url, gen))

    def stop(self):
        self.update("", "", False)

    def _current(self, gen):
        with self.lock:
            return self.active and gen == self.gen

    def _run(self, cam, url, gen):
        with self.lock:
            self.running.add(cam)
        fails = 0
        try:
            while self._current(gen):
                try:
                    s = self.open_stream(url)
                except Exception as e:
                    self._error(cam, gen, e)
                else:
                    with self.lock:
                        if not (self.active and gen == self.gen):
                            _close(s)
                            return
                        self.streams[cam] = s
                    try:
                        self._read(cam, s, gen)
                        fails = 0
                    except Exception as e:
                        self._error(cam, gen, e)
                    finally:
                        _close(s)
                        with self.lock:
                            if self.streams.get(cam) is s:
                                del self.streams[cam]
                if not self._current(gen):
                    return
                wait = RETRY[min(fails, len(RETRY) - 1)]
                fails += 1
                end = self.clock() + wait
                while self._current(gen) and self.clock() < end:
                    self.sleep(0.2)
        finally:
            with self.lock:
                self.running.discard(cam)

    def _read(self, cam, s, gen):
        parser = MjpegParser()
        while self._current(gen):
            data = s.read(self.chunk)
            if not data:
                raise IOError("stream ended")
            for pic in parser.feed(data):
                with self.lock:
                    if gen == self.gen:
                        self.frames[cam] = (pic, self.clock())
                        self.errors.pop(cam, None)

    def _error(self, cam, gen, e):
        with self.lock:
            if gen == self.gen:
                self.errors[cam] = e.__class__.__name__

    def frame(self, camera, max_age=STALE_SECONDS):
        """The last picture of a ready camera when it is at most max_age seconds old, else None."""
        with self.lock:
            f = self.frames.get(camera) if self.active else None
        if f is None or self.clock() - f[1] > max_age:
            return None
        return f[0]

    def lines(self, tr):
        """[(ok, text)] for the diagnostics: per ready camera its last picture or that it is not connected."""
        with self.lock:
            urls, frames, errors, active = dict(self.urls), dict(self.frames), dict(self.errors), self.active
        out = []
        for cam in sorted(urls):
            f = frames.get(cam)
            if not active:
                out.append((None, tr(N_("Ready: %s (not while the player is off)")) % cam))
            elif f is not None and self.clock() - f[1] <= STALE_SECONDS:
                out.append((True, tr(N_("Ready: %s (last picture %d s ago)")) % (cam, int(self.clock() - f[1]))))
            else:
                err = errors.get(cam)
                out.append((False, tr(N_("Ready: %s not connected")) % cam + (" (%s)" % err if err else "")))
        return out

    def state(self):
        """Plain data for the diagnostics of another interpreter (Kodi): {camera: age in s or None}, active."""
        with self.lock:
            now = self.clock()
            return {"active": self.active,
                    "cameras": {c: (round(now - self.frames[c][1], 1) if c in self.frames else None) for c in self.urls}}


def lines_from_state(state, tr):
    """WarmFeeds.lines() from WarmFeeds.state() (Kodi's diagnostics run in another interpreter)."""
    out = []
    if not state:
        return out
    for cam, age in sorted((state.get("cameras") or {}).items()):
        if not state.get("active"):
            out.append((None, tr(N_("Ready: %s (not while the player is off)")) % cam))
        elif age is not None and age <= STALE_SECONDS:
            out.append((True, tr(N_("Ready: %s (last picture %d s ago)")) % (cam, int(age))))
        else:
            out.append((False, tr(N_("Ready: %s not connected")) % cam))
    return out


def _close(s):
    try:
        s.close()
    except Exception:
        pass
