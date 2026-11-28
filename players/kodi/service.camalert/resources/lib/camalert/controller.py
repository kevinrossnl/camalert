# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""What is on screen, and the show / mosaic / tour / hide requests (same behaviour as the Enigma2 plugin)."""
import os
import shutil
import threading
import time
import urllib.request

import xbmc
import xbmcgui

from . import kodiapi, sources
from .display import FullScreen, LiveOverlay, LiveStillWindow, PhotoWindow, open_window
from .klogic import blocked_by_playing, chime_wanted, kodi_volume, live_mime, playing_kind, resume_plan
from .camalert_core.access import url_target
from .camalert_core.cameras import known_camera, neighbour, parse_cams, slug
from .camalert_core.api import screen_name
from .camalert_core.events import TEST_SOURCE, add_event, event_title, is_test
from .camalert_core.frames import LiveStill, STILL_MAX_SECONDS
from .camalert_core.keymap import button_event, colour_action
from .camalert_core.present import priority_label, reason as reason_code
from .camalert_core.rules import (blocked_by_rules, clamp_seconds, clock_tuple, cooldown_seconds, decide, dnd_blocks,
                                  in_cooldown, in_time_window, pick_mode, pick_priority)

STATS = {"errors": 0, "requests": {}, "started": time.time(), "last_event": 0, "unreachable": 0}


def free_bytes(folder):
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return 0


def metrics():
    """Prometheus metrics for /camalert/metrics (same names as the Enigma2 plugin)."""
    from . import __version__
    from .camalert_core.obs.metrics import metrics_text
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
    }, {"version": __version__, "platform": "kodi"})


def live_item(url, title):
    li = xbmcgui.ListItem(title, path=url)
    mime = live_mime(url)
    if mime:
        li.setMimeType(mime)
    li.setContentLookup(False)
    return li



def notification_text(title, priority):
    """'Camera: Person · Front door' (+ '  ·  High' / 'Alarm' for a higher priority), like Enigma2 (#49)."""
    text = kodiapi.tr(30180).replace("%s", title)
    if priority in ("high", "alarm"):
        text += "  ·  " + priority_label(priority, kodiapi.core_tr())
    return text


def _remove(path):
    try:
        if path:
            os.remove(path)
    except OSError:
        pass


class Controller(object):
    instance = None

    def __init__(self):
        Controller.instance = self
        self.lock = threading.RLock()
        self.player = xbmc.Player()
        self.window = None
        self.full = None
        self.live_stream = None
        self.live_timer = None
        self.live_seconds = 30
        self.overlay = None
        self.still = LiveStill()  # #91: still picture until the camera picture is on screen
        self.still_win = None
        self.resume = None
        self.saved_volume = None
        self.paused = False
        self.names, self.names_at = [], 0.0
        self.listeners = []
        self.events = []
        self.label = None
        self.source = None
        self.reason = ""
        self.last_caller = None  # (time, address, source) of the last API call
        self.last_shown = {}

    # --- helpers ---------------------------------------------------------------------------------------------
    def changed(self):
        for f in list(self.listeners):
            try:
                f()
            except Exception as e:
                kodiapi.log("listener failed: %s" % e)

    def refresh_names(self, s=None):
        try:
            self.names, self.names_at = sources.all_camera_names(s), time.time()
        except Exception as e:
            kodiapi.log("camera list failed: %s" % e)
        return self.names

    def playing(self):
        """(kind, file, position, paused) of what Kodi plays now."""
        try:
            if not self.player.isPlaying():
                return "none", "", 0.0, False
            f = self.player.getPlayingFile()
            pos = self.player.getTime() if self.player.isPlayingVideo() else 0.0
        except RuntimeError:
            return "none", "", 0.0, False
        kind = playing_kind(f, kodiapi.cond("VideoPlayer.Content(livetv)") or kodiapi.cond("PVR.IsPlayingTV"),
                            self.player.isPlayingVideo())
        return kind, f, pos, bool(kodiapi.cond("Player.Paused"))

    def current_camera(self):
        return self.live_stream if self.playing()[0] == "camera" else None

    def screen_off(self):
        return bool(kodiapi.cond("System.DPMSActive"))

    def wake(self):
        kodiapi.builtin("CECActivateSource")
        kodiapi.builtin("Action(noop)")

    def end_screensaver(self):
        """#119: a CamAlert window must not open behind a screensaver (CamAlert's own, #99, or another one): for
        every priority the screensaver is ended first (any action ends it), waiting at most 1.5 s for Kodi."""
        if not kodiapi.cond("System.ScreenSaverActive"):
            return False
        kodiapi.log("screensaver active: ending it before showing", "verbose")
        kodiapi.jsonrpc("Input.ExecuteAction", {"action": "noop"})
        for _ in range(15):
            if not kodiapi.cond("System.ScreenSaverActive"):
                break
            time.sleep(0.1)
        return True

    # --- public ----------------------------------------------------------------------------------------------
    def window_priority(self, priority):
        """The priority a window marks (#48): none for what the viewer asked for himself (#13)."""
        return "normal" if getattr(self, "source", None) == "menu" else pick_priority(priority)

    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        """Handles a show request; logs it (source, decision, reason) and keeps it in the event list."""
        s = kodiapi.settings()
        cam = stream or s["camera"]
        if mode == "log":  # display mode 'log only' (#71): event list and log, nothing on screen, no chime
            reason = reason_code("log_only")
            kodiapi.log("request from %s: camera=%s priority=%s mode=log label=%s -> ignore (%s)"
                        % (source, cam, pick_priority(priority), label or "-", reason))
            self.record_event(cam, label, source, pick_priority(priority), "ignore", reason, event_id)
            return "ignore"
        wait = cooldown_seconds(cam, s["cooldown"])
        with self.lock:
            self.reason, self.label, self.source = "", (label or "").strip()[:40] or None, source
            on_screen = (self.window.stream if self.window else None) == cam
            try:
                if not on_screen and pick_priority(priority) != "alarm" and \
                        in_cooldown(self.last_shown.get(cam), time.time(), wait):
                    self.reason, result = reason_code("cooldown", wait), "ignore"
                else:
                    result = self._show(stream, seconds, mode, priority)
            except Exception as e:
                kodiapi.log("show failed: %s" % e, "error")
                result = "error"
            finally:
                self.label = None
            reason = self.reason
        if result == "show":
            self.last_shown[cam] = time.time()
        STATS["requests"][result] = STATS["requests"].get(result, 0) + 1
        STATS["last_event"] = time.time()
        if result == "error":
            STATS["errors"] += 1
        kodiapi.log("request from %s: camera=%s priority=%s mode=%s label=%s -> %s%s"
                    % (source, cam, pick_priority(priority), mode or "-", label or "-", result,
                       (" (%s)" % reason) if reason else ""), "error" if result == "error" else "normal")
        self.record_event(cam, label, source, pick_priority(priority), result, reason, event_id)
        if result in ("show", "extend") and chime_wanted(s["chime"], pick_priority(priority)) \
                and not is_test(source) and source != "menu":  # a test (#62) or the viewer's own choice (#13): no sound
            if kodiapi.cond("Player.Muted"):  # Kodi muted: no chime either (#20)
                kodiapi.log("chime skipped: Kodi is muted")
            else:
                kodiapi.chime()
        return result

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
        if not first or action not in ("show", "extend", "wake"):
            return

        def save():
            try:
                urls = sources.camera_urls(first, kodiapi.settings())
                folder = os.path.join(kodiapi.profile_dir(), "events")
                os.makedirs(folder, exist_ok=True)
                if urls and urls[1] and free_bytes(folder) > 8 * 1024 * 1024:  # low storage: no snapshots
                    path = os.path.join(folder, "%d_%s.jpg" % (int(ev["time"]), slug(first)))
                    ev["snapshot"] = sources.download(urls[1].replace("width=640", "width=320"), path,
                                                      kodiapi.settings()["verify_ssl"])
            except Exception as e:
                kodiapi.log("event snapshot failed: %s" % e, "verbose")
        threading.Thread(target=save, daemon=True).start()

    def _show(self, stream, seconds, mode, priority):
        s = kodiapi.settings()
        priority = pick_priority(priority)
        if dnd_blocks(priority, s["dnd"], s["dnd_level"]):
            self.reason = reason_code("dnd")
            return "ignore"
        if self.screen_off():
            if priority == "alarm" and s["alarm_wake"]:
                kodiapi.log("alarm: waking the screen")
                self.wake()
                label = self.label
                again = TEST_SOURCE if is_test(self.source) else "wake"
                threading.Timer(4, self.show, (stream, seconds, mode, priority, again, label)).start()
                return "wake"
            self.reason = reason_code("screen_off")
            return "ignore"
        self.end_screensaver()
        cams = parse_cams(stream)
        seconds = seconds or s["duration"]
        if len(cams) > 1:
            if 2 <= len(cams) <= 4 and pick_mode(mode, s["mode"]) == "photo":
                return self._strip(cams, seconds, s, priority)
            return self.mosaic(",".join(cams), seconds)
        stream = stream or s["camera"]
        if not stream:
            self.reason = reason_code("no_camera")
            return "error"
        if time.time() - self.names_at > 60:
            self.refresh_names(s)
        if not known_camera(stream, self.names):
            self.reason = reason_code("unknown_camera")
            return "error"
        mode = pick_mode(mode, s["mode"])
        urls = sources.camera_urls(stream, s)
        if not urls:
            self.reason = reason_code("no_address")
            return "error"
        live, snap, title = urls
        title = event_title(title, self.label)
        if mode == "photo" and not snap:
            mode = "live"
        kind, f, pos, was_paused = self.playing()
        t = time.localtime()
        in_hours = in_time_window((t.tm_hour, t.tm_min), clock_tuple(s["from_time"]), clock_tuple(s["until_time"]))
        if blocked_by_rules(priority, s["limit_hours"], in_hours, False, False, s["skip_playing"] != "off",
                            blocked_by_playing(s["skip_playing"], kind)):
            self.reason = reason_code("outside_hours" if s["limit_hours"] and not in_hours else "playing")
            return "ignore"
        window_stream = self.window.stream if self.window else (self.live_stream if mode == "live" else None)
        action = decide(False, self.current_camera(), window_stream, stream)
        if action == "ignore":
            self.reason = reason_code("on_screen")
            return action
        if mode == "photo":
            if action == "extend":
                self.window.extend(seconds)
            else:
                self._close_window()
                self._maybe_pause(s, kind, was_paused)
                mark = self.window_priority(priority)
                self.window = open_window(lambda: PhotoWindow(self, [(stream, title, snap)], s, s["window_keys"],
                                                              None, mark))
                self.window.start(seconds)
        elif mode == "live":
            self._live(stream, live, title, seconds, s, priority, kind, f, pos, was_paused, action, snap)
        else:
            self._maybe_pause(s, kind, was_paused)
            icon = ""
            if snap:
                try:
                    icon = sources.download(snap, os.path.join(kodiapi.temp_dir(), "notify_%d.jpg" % int(time.time())),
                                            s["verify_ssl"])
                except Exception as e:
                    kodiapi.log("snapshot for notification failed: %s" % e)
            kodiapi.notify("CamAlert", notification_text(title, priority), icon, seconds * 1000)
            if icon:
                threading.Timer(seconds + 5, lambda: os.path.exists(icon) and os.remove(icon)).start()
            if self.paused:
                threading.Timer(seconds, self.resume_tv).start()
        self.changed()
        return action

    def _strip(self, cams, seconds, s, priority):
        tiles = []
        for c in cams:
            u = sources.camera_urls(c, s)
            if u and u[1]:
                tiles.append((c, u[2], u[1]))
        if not tiles:
            return "error"
        self._close_window()
        kind, _f, _p, was_paused = self.playing()
        self._maybe_pause(s, kind, was_paused)
        label = self.label
        mark = self.window_priority(priority)
        self.window = open_window(lambda: PhotoWindow(self, tiles, s, s["window_keys"], label, mark))
        self.window.start(seconds)
        self.changed()
        return "show"

    def _live(self, stream, url, title, seconds, s, priority, kind, f, pos, was_paused, action, snap=None):
        if action == "show":
            if self.live_stream is None:
                self.resume = resume_plan(f, pos, kind, was_paused) if s["live_return"] else None
                if priority != "alarm" and s["live_volume"] < 100:
                    vol = (kodiapi.jsonrpc("Application.GetProperties", {"properties": ["volume"]}) or {}).get("volume")
                    if vol is not None:
                        self.saved_volume = vol
                        kodiapi.jsonrpc("Application.SetVolume", {"volume": kodi_volume(vol, s["live_volume"])})
            self._close_window()
            self.player.play(url, live_item(url, title))
            self.live_stream = stream
            self._start_still(stream, snap, s, url)
            threading.Thread(target=self._show_overlay, args=(stream, title), daemon=True).start()
        self.live_seconds = seconds
        self.extend_live()

    def _start_still(self, stream, snap, s, live_url):
        """#91: fetch a picture (warm feed, Protect, go2rtc cache, frame.jpeg) in a thread while the stream opens,
        and close it from another thread as soon as this camera's stream is on screen."""
        with self.lock:
            self._close_still()
            if not snap:
                return
            token = self.still.start(stream)
        threading.Thread(target=self._fetch_still, args=(stream, snap, s, token), daemon=True).start()
        threading.Thread(target=self._watch_still, args=(live_url, token), daemon=True).start()

    def _stream_on_screen(self, live_url):
        kind, f = self.playing()[:2]
        return kind == "camera" and f.split("|", 1)[0] == live_url and \
            bool(kodiapi.cond("Window.IsActive(fullscreenvideo)"))

    def _watch_still(self, live_url, token):
        for _ in range(int(STILL_MAX_SECONDS * 4) + 8):
            xbmc.sleep(250)
            with self.lock:
                if self.still.token != token:
                    return  # ended, or another camera with its own watcher
                if self._stream_on_screen(live_url):
                    if self.still.playing(token):
                        self._close_still()
                    return
                if self.still.expired():
                    self._close_still()
                    return

    def _fetch_still(self, stream, snap, s, token):
        path = os.path.join(kodiapi.temp_dir(), "still_%d.jpg" % token)  # a new name: Kodi caches by path
        try:
            sources.picture(stream, snap, path, s["verify_ssl"], True, s)
        except Exception as e:
            kodiapi.log("still picture for %s failed: %s" % (stream, e), "verbose")
            return
        with self.lock:
            if self.live_stream != stream or not self.still.picture(token):
                _remove(path)  # the stream was faster, or live view ended / another camera meanwhile
                return
            self.still_win = open_window(lambda: LiveStillWindow(self, path))
            self.still_win.path = path
        kodiapi.log("live view %s: still picture shown" % stream, "verbose")

    def _close_still(self):
        w, self.still_win = self.still_win, None
        if w is not None:
            w.stop()
            _remove(getattr(w, "path", ""))

    def _show_overlay(self, stream, title):
        for _ in range(120):  # wait until the camera picture is on screen
            xbmc.sleep(250)
            if self.live_stream != stream:
                return
            if self.playing()[0] == "camera" and kodiapi.cond("Window.IsActive(fullscreenvideo)"):
                break
        with self.lock:
            if self.live_stream != stream:
                return
            if self.overlay is None:
                self.overlay = open_window(lambda: LiveOverlay(self, stream, title))
            else:
                self.overlay.set_camera(stream, title)

    def extend_live(self):
        if self.live_timer:
            self.live_timer.cancel()
        self.live_timer = threading.Timer(self.live_seconds, self.end_live)
        self.live_timer.daemon = True
        self.live_timer.start()

    def live_other(self, step):
        s = kodiapi.settings()
        target = neighbour(self.names or self.refresh_names(s), self.live_stream, step) if self.live_stream else None
        u = sources.camera_urls(target, s) if target else None
        if not u:
            return
        with self.lock:
            self.player.play(u[0], live_item(u[0], u[2]))
            self.live_stream = target
            self._start_still(target, u[1], s, u[0])
            if self.overlay is not None:
                self.overlay.set_camera(target, u[2])
            self.extend_live()
        self.changed()

    def _maybe_pause(self, s, kind, was_paused):
        if s["pause_tv"] and kind in ("video", "livetv") and not was_paused and not self.paused:
            self.player.pause()
            self.paused = True

    def resume_tv(self):
        if self.paused:
            self.paused = False
            if kodiapi.cond("Player.Paused"):
                self.player.pause()

    def end_live(self):
        with self.lock:
            if self.live_timer:
                self.live_timer.cancel()
                self.live_timer = None
            stream, self.live_stream = self.live_stream, None
            plan, self.resume = self.resume, None
            self.still.stop()
            self._close_still()
            if self.overlay is not None:
                o, self.overlay = self.overlay, None
                o.stop()
            if self.saved_volume is not None:
                kodiapi.jsonrpc("Application.SetVolume", {"volume": self.saved_volume})
                self.saved_volume = None
            if stream and self.playing()[0] in ("camera", "none"):  # 'none': still opening
                self.player.stop()
                if plan:
                    self._resume(plan)
        self.changed()

    def _resume(self, plan):
        def go():
            xbmc.sleep(500)
            kodiapi.log("back to what was playing (at %ds)" % plan["seek"])
            li = xbmcgui.ListItem(path=plan["file"])
            if plan["seek"]:
                li.setProperty("StartOffset", "%.1f" % plan["seek"])  # Kodi starts there itself
            self.player.play(plan["file"], li)
            if plan["paused"]:
                for _ in range(60):
                    xbmc.sleep(250)
                    try:
                        if self.player.isPlaying() and self.player.getTime() > 0:
                            self.player.pause()
                            break
                    except RuntimeError:
                        pass
        threading.Thread(target=go, daemon=True).start()

    def window_to_live(self, stream):
        self.hide(resume=False)
        self.show(stream, None, "live", "high")

    def other_camera(self, step):
        w = self.window
        if w is None:
            return
        s = kodiapi.settings()
        target = neighbour(self.names or self.refresh_names(s), w.stream, step)
        u = sources.camera_urls(target, s) if target else None
        if u and u[1]:
            w.switch(target, u[2], u[1])
            w.extend(s["duration"])
            self.changed()

    def window_timeout(self, w):
        with self.lock:
            if self.window is w:
                self._close_window()
                self.resume_tv()
        self.changed()

    def _close_window(self):
        w, self.window = self.window, None
        if w is not None:
            w.stop()

    def hide(self, resume=True):
        with self.lock:
            self._close_window()
            if self.full is not None:
                f, self.full = self.full, None
                f.stop()
            if self.live_stream is not None:
                self.end_live()
            if resume:
                self.resume_tv()
        self.changed()

    def _cams_with_snapshots(self, streams, s):
        out = []
        for c in streams[:9]:
            u = sources.camera_urls(c, s)
            if u and u[1]:
                out.append((c, u[2], u[1]))
        return out

    def _fullscreen(self, stream, seconds, tour, interval=None):
        s = kodiapi.settings()
        if self.screen_off():
            return "ignore"
        streams = parse_cams(stream) or parse_cams(s["mosaic"]) or sources.overview_names(self.refresh_names(s))
        cams = self._cams_with_snapshots(streams, s)
        if not cams:
            return "error"
        with self.lock:
            self._close_window()
            if self.full is not None:
                self.full.stop()
            self.full = open_window(lambda: FullScreen(self, cams, s, tour, seconds, interval or s["tour_interval"]))
            self.full.start()
        self.changed()
        return "show"

    def mosaic(self, stream=None, seconds=60):
        return self._fullscreen(stream, clamp_seconds(seconds, 60) if seconds else 0, False)

    def tour(self, stream=None, interval=None):
        return self._fullscreen(stream, 0, True, interval)

    def fullscreen_closed(self, f):
        with self.lock:
            if self.full is f:
                self.full = None
            f.stop()
        self.changed()

    def set_dnd(self, on):
        kodiapi.set_setting("dnd", bool(on))
        self.changed()

    def status(self):
        s = kodiapi.settings()
        return {"window": self.window.stream if self.window else None, "live": self.live_stream,
                "paused": self.paused, "dnd": s["dnd"], "screen": self.screen()}

    def screen(self):
        """What CamAlert shows now, for status "screen" (#63). Kodi notifications are toasts: not tracked."""
        full, w = self.full, self.window
        return screen_name("tour" if getattr(full, "tour", False) else "mosaic" if full is not None else None,
                           None if w is None else "strip" if len(getattr(w, "cams", ())) > 1 else "photo",
                           False, self.live_stream is not None)

    def play_clip(self, url, title):
        """Frigate clip from the event list (a normal film for Kodi: no camera rules, no automatic end)."""
        if url:
            self.hide()
            li = xbmcgui.ListItem(title or "CamAlert", path=url)
            li.setMimeType("video/mp4")
            li.setContentLookup(False)
            self.player.play(url, li)

    # --- camera control and colour keys ----------------------------------------------------------------------
    def has_ptz(self, name):
        from . import ptz
        return bool(name) and name in ptz.ptz_devices()

    def ptz_move(self, action, name=None):
        from . import ptz
        name = name or (self.window.stream if self.window else self.live_stream)
        p = ptz.Ptz(name)
        if not p.available():
            return False
        p.do(action) if action != "stop" else p.stop()
        return True

    def colour_key(self, camera, colour):
        """A colour key while a camera is on screen: 'ptz' (toggle PTZ mode) or sent to Home Assistant."""
        s = kodiapi.settings()
        what = colour_action(colour, s["ptz_key"], self.has_ptz(camera), s["ha_buttons"])
        if what and what != "ptz":
            self.send_button(camera, what, s)
        return what

    def send_button(self, camera, button, s=None):
        from . import mqtt
        from .server import node_id
        s = s or kodiapi.settings()
        kodiapi.log("button %s on camera %s -> Home Assistant" % (button, camera))
        mqtt.publish_button(camera, button)
        hook = s["ha_webhook"].strip()
        if hook:
            body = button_event(node_id(), camera, button, s.get("ha_webhook_secret") or None).encode("utf-8")  # #82

            def post():
                try:
                    why = url_target(hook)  # checked again on use: a host name may resolve elsewhere now (#53)
                    if why:
                        raise ValueError(why)
                    req = urllib.request.Request(hook, data=body, headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=5).close()
                except Exception as e:
                    kodiapi.log("button webhook failed: %s" % e, "error")
            threading.Thread(target=post, daemon=True).start()

    def shutdown(self):
        try:
            self.hide()
        except Exception:
            pass
