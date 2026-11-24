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
from .display import FullScreen, LiveOverlay, PhotoWindow, open_window
from .klogic import blocked_by_playing, chime_wanted, kodi_volume, live_mime, playing_kind, resume_plan
from .logic import (add_event, blocked_by_rules, button_event, button_for, clamp_seconds, clock_tuple, cooldown_seconds,
                    decide, dnd_blocks, event_title, in_cooldown, in_time_window, known_camera, neighbour, parse_cams,
                    pick_mode, pick_priority, slug)

STATS = {"errors": 0, "requests": {}, "started": time.time(), "last_event": 0, "unreachable": 0}


def free_bytes(folder):
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return 0


def metrics():
    """Prometheus metrics for /camalert/metrics (same names as the Enigma2 plugin)."""
    from . import __version__
    from .logic import metrics_text
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
        self.resume = None
        self.saved_volume = None
        self.paused = False
        self.names, self.names_at = [], 0.0
        self.listeners = []
        self.events = []
        self.label = None
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

    # --- public ----------------------------------------------------------------------------------------------
    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        """Handles a show request; logs it (source, decision, reason) and keeps it in the event list."""
        s = kodiapi.settings()
        cam = stream or s["camera"]
        wait = cooldown_seconds(cam, s["cooldown"])
        with self.lock:
            self.reason, self.label = "", (label or "").strip()[:40] or None
            on_screen = (self.window.stream if self.window else None) == cam
            try:
                if not on_screen and pick_priority(priority) != "alarm" and \
                        in_cooldown(self.last_shown.get(cam), time.time(), wait):
                    self.reason, result = "cooldown (%d s)" % wait, "ignore"
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
        if result in ("show", "extend") and chime_wanted(s["chime"], pick_priority(priority)):
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
            self.reason = "do not disturb"
            return "ignore"
        if self.screen_off():
            if priority == "alarm" and s["alarm_wake"]:
                kodiapi.log("alarm: waking the screen")
                self.wake()
                label = self.label
                threading.Timer(4, self.show, (stream, seconds, mode, priority, "wake", label)).start()
                return "wake"
            self.reason = "screen off"
            return "ignore"
        cams = parse_cams(stream)
        seconds = seconds or s["duration"]
        if len(cams) > 1:
            if 2 <= len(cams) <= 4 and pick_mode(mode, s["mode"]) == "photo":
                return self._strip(cams, seconds, s, priority)
            return self.mosaic(",".join(cams), seconds)
        stream = stream or s["camera"]
        if not stream:
            self.reason = "no camera"
            return "error"
        if time.time() - self.names_at > 60:
            self.refresh_names(s)
        if not known_camera(stream, self.names):
            self.reason = "unknown camera"
            return "error"
        mode = pick_mode(mode, s["mode"])
        urls = sources.camera_urls(stream, s)
        if not urls:
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
            self.reason = "outside active hours" if s["limit_hours"] and not in_hours else "playing"
            return "ignore"
        window_stream = self.window.stream if self.window else (self.live_stream if mode == "live" else None)
        action = decide(False, self.current_camera(), window_stream, stream)
        if action == "ignore":
            self.reason = "already on screen"
            return action
        if mode == "photo":
            if action == "extend":
                self.window.extend(seconds)
            else:
                self._close_window()
                self._maybe_pause(s, kind, was_paused)
                self.window = open_window(lambda: PhotoWindow(self, [(stream, title, snap)], s, s["window_keys"]))
                self.window.start(seconds)
        elif mode == "live":
            self._live(stream, live, title, seconds, s, priority, kind, f, pos, was_paused, action)
        else:
            self._maybe_pause(s, kind, was_paused)
            icon = ""
            if snap:
                try:
                    icon = sources.download(snap, os.path.join(kodiapi.temp_dir(), "notify_%d.jpg" % int(time.time())),
                                            s["verify_ssl"])
                except Exception as e:
                    kodiapi.log("snapshot for notification failed: %s" % e)
            kodiapi.notify("CamAlert", kodiapi.tr(30180).replace("%s", title), icon, seconds * 1000)
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
        self.window = open_window(lambda: PhotoWindow(self, tiles, s, s["window_keys"], label))
        self.window.start(seconds)
        self.changed()
        return "show"

    def _live(self, stream, url, title, seconds, s, priority, kind, f, pos, was_paused, action):
        if action == "show":
            if self.live_stream is None:
                self.resume = resume_plan(f, pos, kind, was_paused) if s["live_resume"] else None
                if priority != "alarm" and s["live_volume"] < 100:
                    vol = (kodiapi.jsonrpc("Application.GetProperties", {"properties": ["volume"]}) or {}).get("volume")
                    if vol is not None:
                        self.saved_volume = vol
                        kodiapi.jsonrpc("Application.SetVolume", {"volume": kodi_volume(vol, s["live_volume"])})
            self._close_window()
            self.player.play(url, live_item(url, title))
            self.live_stream = stream
            threading.Thread(target=self._show_overlay, args=(stream, title), daemon=True).start()
        self.live_seconds = seconds
        self.extend_live()

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
        streams = parse_cams(stream) or parse_cams(s["mosaic"]) or self.refresh_names(s)
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
                "paused": self.paused, "dnd": s["dnd"]}

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
        return bool(name) and name in ptz.all_devices()

    def ptz_move(self, action, name=None):
        from . import ptz
        name = name or (self.window.stream if self.window else self.live_stream)
        p = ptz.Ptz(name)
        if not p.available():
            return False
        p.do(action) if action != "stop" else p.stop()
        return True

    def colour_key(self, camera, code):
        """A colour key while a camera is on screen: 'ptz' (toggle PTZ mode) or sent to Home Assistant."""
        s = kodiapi.settings()
        what = button_for(code, s["ptz_key"], self.has_ptz(camera), s["ha_buttons"])
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
            body = button_event(node_id(), camera, button).encode("utf-8")

            def post():
                try:
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
