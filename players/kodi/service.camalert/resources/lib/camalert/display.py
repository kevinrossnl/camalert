# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Windows: photo window (one camera or a strip of 2-4), full-screen mosaic and tour."""
import os
import threading
import time

import xbmcgui

from . import kodiapi, sources
from .klogic import (PTZ_TOGGLE as TOGGLE_IDS, SCREEN_H, SCREEN_W, VIDEO_FRAME, VIDEO_HINT, VIDEO_MASKS, VIDEO_TITLE,
                     colour_name,
                     forward_builtin, frame_name, key_action, live_key, mosaic_key, ptz_action, text_font_name,
                     title_font_name, tour_key, video_window_xml)
from .camalert_core.cameras import parse_orientation, parse_refresh, refresh_delay
from .camalert_core.events import event_title
from .camalert_core.present import key_hint, tile_label, tour_status
from .camalert_core.layout import grid, strip_geometry, text_scale, window_geometry
from .camalert_core.style import FLASH_MS, marked_title, priority_mark
from .camalert_core.privacy import MAX_MASKS, jpeg_file_size, mask_rects, parse_masks

WHITE = None
ANIM = {"rot180": "effect=rotate end=180 center=auto", "mirror": "effect=rotatey end=180 center=auto",
        "flip": "effect=rotatex end=180 center=auto"}
VOLUME_KEYS = {88: "Action(VolumeUp)", 89: "Action(VolumeDown)", 91: "Action(Mute)"}
# Arrow glyphs in key hints (#41): Estuary's NotoSans-Regular has no U+25C0/U+25B6 (checked on Kodi 21.3, only
# arial.ttf of the Arial fontset has them) and Kodi does not fall back to another font, so Kodi uses < > ^ v.
GLYPHS = False


def hint(context, s=None, has_ptz=False):
    """Translated key hint of a screen, built from the key map (camalert_core.present, #41)."""
    return key_hint("kodi", context, kodiapi.core_tr(), ptz_key=(s or {}).get("ptz_key"), has_ptz=has_ptz,
                    glyphs=GLYPHS)


def has_ptz(name, s):
    """True when devices.conf has camera control for this camera (only then the hint offers it)."""
    try:
        from .ptz import ptz_devices
        return name in ptz_devices(s)
    except Exception:  # a broken devices.conf must not stop the window
        return False


def add_error_overlay(win, tile, x, y, w, h, font="font13"):
    """Dimmed layer with a text over one tile: 'Loading picture...' until the first picture arrives (#110), and
    'Camera not reachable' when the Feeder reports the camera (#49): no silent frozen or black picture."""
    dim = xbmcgui.ControlImage(x, y, w, h, white(), colorDiffuse="C0000000")
    text = xbmcgui.ControlLabel(x + 8, y, max(10, w - 16), h, tile_label("loading", kodiapi.core_tr()),
                                font=font, textColor="FFFFFFFF", alignment=0x00000002 | 0x00000004)
    win.addControl(dim)
    win.addControl(text)
    tile["error"] = (dim, text)


def show_error(tile, state):
    """state: False/None = the picture, True or 'unreachable' (#49), 'loading' (#110)."""
    parts = tile.get("error", ())
    if state and len(parts) == 2:
        parts[1].setLabel(tile_label("loading" if state == "loading" else "unreachable", kodiapi.core_tr()))
    for c in parts:
        c.setVisible(bool(state))


def count_unreachable(bad):
    if bad:
        from .controller import STATS
        STATS["unreachable"] += 1


def white():
    global WHITE
    if WHITE is None:
        WHITE = kodiapi.addon_path("resources", "media", "white.png")
    return WHITE


def open_window(factory):
    """Creates a window and runs it modally in one dedicated thread, and returns it. Kodi runs a window's
    callbacks (onAction) in the thread that created it, and only a modal window gets the remote keys, so both
    have to happen in a thread that lives as long as the window. close() from any thread ends it."""
    box, ready = {}, threading.Event()

    def run():
        try:
            box["w"] = factory()
        finally:
            ready.set()
        box["w"].doModal()

    threading.Thread(target=run, name="camalert-window", daemon=True).start()
    ready.wait(10)
    if "w" not in box:
        raise RuntimeError("window could not be created")
    return box["w"]


def orient(control, name, orientation):
    eff = ANIM.get(orientation.get(name, ""))
    control.setAnimations([("conditional", eff + " time=0 condition=true")] if eff else [])


class PtzMode(object):
    """PTZ mode shared by the photo window and the live overlay: arrows pan/tilt, channel/page up-down zoom,
    OK = home position, BACK leaves PTZ mode."""
    ptz = None

    def ptz_toggle(self, name):
        if self.ptz is not None:
            self.ptz_leave()
            return True
        from .ptz import Ptz
        p = Ptz(name)
        if not p.available():
            kodiapi.notify("CamAlert", kodiapi.tr(30196), "", 3000)
            return False
        self.ptz = p
        self.ptz_label(True)
        return True

    def ptz_leave(self):
        if self.ptz is not None:
            self.ptz.stop()
        self.ptz = None
        self.ptz_label(False)

    def ptz_action(self, aid):
        """True when PTZ mode used the key."""
        if self.ptz is None:
            return False
        k = ptz_action(aid)
        if k is None:
            return aid not in VOLUME_KEYS
        if k == "leave":
            self.ptz_leave()
        else:
            self.ptz.do(k)
        self.ptz_used()
        return True

    def ptz_label(self, on):
        pass

    def ptz_used(self):
        pass


IMAGE_SIZES = {}  # camera -> (width, height) of its last picture: where the masks go over live video (#11)


def masks_of(s):
    return parse_masks((s or {}).get("privacy_masks", ""))


def add_masks(win, s, controls=None):
    """MAX_MASKS hidden black boxes on win (#11), only when some camera has privacy masks; added after the
    pictures, so they lie on top of them. controls: existing image controls of a skin XML window instead."""
    if not masks_of(s):
        return []
    if controls is not None:
        return list(controls)
    out = []
    for _ in range(MAX_MASKS):
        c = xbmcgui.ControlImage(0, 0, 1, 1, white(), colorDiffuse="FF000000")
        win.addControl(c)
        c.setVisible(False)
        out.append(c)
    return out


def place_masks(controls, name, s, box, size=None):
    """Covers the masked areas of camera `name` drawn in box (x, y, w, h) (#11); other boxes are hidden."""
    if not controls:
        return
    if size:
        IMAGE_SIZES[name] = size
    rects = mask_rects(name, masks_of(s), box, size or IMAGE_SIZES.get(name))
    for i, c in enumerate(controls):
        if i < len(rects):
            x, y, w, h = rects[i]
            c.setPosition(x, y)
            c.setWidth(w)
            c.setHeight(h)
            c.setVisible(True)
        else:
            c.setVisible(False)


class Feeder(object):
    """Keeps fetching snapshots, one thread per tile (a slow camera never holds up the others), each camera with
    its own refresh interval. Every picture gets a new file name so Kodi never shows a cached one."""

    def __init__(self, tiles, s):
        self.tiles = list(tiles)  # dicts: name, url, control
        self.verify = s["verify_ssl"]
        self.settings = s
        self.refresh = parse_refresh(s.get("refresh", ""))
        self.active = True
        self.on_unreachable = None  # callback(tile, unreachable)
        self.on_loaded = None  # callback(tile): the first picture of a camera in a tile arrived (#110)
        self.retry = 2.0  # seconds between attempts while a camera does not answer

    def start(self):
        for i in range(len(self.tiles)):
            threading.Thread(target=self.loop, args=(i,), daemon=True).start()

    def loop(self, i):
        tmp = kodiapi.temp_dir()
        n = 0
        fails = {}
        last = None
        while self.active:
            t = self.tiles[i]
            if t is not last:  # another camera in this tile (tour, other camera): count its failures from 0
                fails[i], last, first = 0, t, True
            n += 1
            path, stale = frame_name(os.path.join(tmp, "f%d_%x" % (i, id(self) & 0xffff)), n)
            start = time.time()
            try:
                sources.picture(t["name"], t["url"], path, self.verify, first, self.settings)  # #109, #110
            except Exception as e:  # camera or go2rtc not reachable: try again a bit later
                fails[i] = fails.get(i, 0) + 1
                if fails[i] == 1:
                    kodiapi.log("snapshot failed for %s: %s" % (t["name"], e))
                if fails[i] == 2 and self.on_unreachable:  # say so instead of a black or frozen picture
                    self.on_unreachable(t, True)
                time.sleep(self.retry)
                continue
            if fails.get(i, 0) >= 2 and self.on_unreachable:
                self.on_unreachable(t, False)
            fails[i] = 0
            if not self.active:
                break
            if self.tiles[i] is t:  # not switched to another camera meanwhile
                place_masks(t.get("masks"), t["name"], self.settings, t.get("box"), jpeg_file_size(path))  # #11
                t["control"].setImage(path, False)
                if first and self.on_loaded:
                    self.on_loaded(t)
            first = False
            try:
                os.remove(stale)
            except OSError:
                pass
            wait = refresh_delay(t["name"], self.refresh, 0.3) - (time.time() - start)
            end = time.time() + max(0.0, wait)
            while self.active and time.time() < end and self.tiles[i] is t:
                time.sleep(0.05)
        for k in range(max(1, n - 3), n + 1):
            try:
                os.remove("%s_%d.jpg" % (os.path.join(tmp, "f%d_%x" % (i, id(self) & 0xffff)), k))
            except OSError:
                pass

    def replace(self, old_name, tile):
        self.tiles = [tile if t["name"] == old_name else t for t in self.tiles]

    def stop(self):
        self.active = False


class Frame(object):
    """The priority frame of a window (#48): four bars in the priority colour, steady or flashing (at most
    style.FLASH_PER_SECOND); the title carries the priority word too, so colour is never the only signal."""

    def __init__(self, win, x, y, w, h, mark, controls=None):
        self.mark, self.controls, self.timer, self.on = mark, list(controls or []), None, True
        if not mark or controls is not None:
            return
        b = 6
        colour = "FF" + mark["colour"].lstrip("#")
        for (fx, fy, fw, fh) in ((x, y, w, b), (x, y + h - b, w, b), (x, y, b, h), (x + w - b, y, b, h)):
            c = xbmcgui.ControlImage(fx, fy, fw, fh, white(), colorDiffuse=colour)
            win.addControl(c)
            self.controls.append(c)

    def start(self):
        if self.mark and self.mark["flash"]:
            self.timer = threading.Timer(FLASH_MS / 1000.0, self.toggle)
            self.timer.daemon = True
            self.timer.start()

    def toggle(self):
        self.on = not self.on
        for c in self.controls:
            c.setVisible(self.on)
        if self.timer is not None:
            self.start()

    def stop(self):
        t, self.timer = self.timer, None
        if t is not None:
            t.cancel()


class CornerKeys(object):
    """Remote keys of the corner windows (photo window and video window, #129): colour keys, camera control, OK =
    live, LEFT/RIGHT = other camera, BACK closes; any other key closes and is passed on."""

    def single(self):
        return True

    def window_key(self, action):
        aid = action.getId()
        kodiapi.log("photo window key %d / button %d" % (aid, action.getButtonCode()), "verbose")
        if self.ptz_action(aid):
            return
        colour = colour_name(action.getButtonCode())
        if colour and self.single():
            if self.ctl.colour_key(self.stream, colour) == "ptz" and self.ptz_toggle(self.stream):
                self.ptz_used()
            else:
                self.extend(self.duration)
            return
        if self.keys and aid in TOGGLE_IDS and self.single():
            if self.ptz_toggle(self.stream):
                self.ptz_used()
            return
        what = key_action(aid) if self.keys else ("pass" if aid in VOLUME_KEYS or aid == 107 else "close_pass")
        if what == "pass":
            if aid in VOLUME_KEYS:
                kodiapi.builtin(VOLUME_KEYS[aid])
            return
        if what == "live" and self.single():
            self.ctl.window_to_live(self.stream)
        elif what in ("prev", "next") and self.single():
            self.ctl.other_camera(-1 if what == "prev" else 1)
        elif what in ("close", "close_pass", "live", "prev", "next"):
            wid = getattr(self, "wid", None)
            self.ctl.hide(window_id=wid) if wid else self.ctl.hide()  # #87: a window with an id closes only itself
            b = forward_builtin(aid) if what == "close_pass" else None
            if b:
                kodiapi.builtin(b)


class PhotoWindow(CornerKeys, PtzMode, xbmcgui.WindowDialog):
    """Corner window with one camera, or a strip of 2-4 cameras."""

    def __init__(self, ctl, cams, s, keys=True, label=None, priority="normal", slot=0, wid=None):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.cams, self.keys = ctl, list(cams), keys
        self.wid = wid  # #87: a window with its own id (closes only itself)
        n = len(self.cams)
        ts = s.get("text_size", "normal")  # #48
        font = title_font_name(s["title_size"], kodiapi.skin_fonts(), ts)
        if n == 1:
            x, y, w, h, t = window_geometry(s["position"], s["size"], SCREEN_W, SCREEN_H, s["title_size"], ts, slot)
            tiles = [(0, t, w, h)]
            total_h = h + t
        else:
            x, y, w, h, t, tiles = strip_geometry(n, s.get("strip_layout", "auto"), s["position"], s["size"],
                                                  SCREEN_W, SCREEN_H, ts)
            total_h = h + t
        self.addControl(xbmcgui.ControlImage(x, y, w, total_h, white(), colorDiffuse="FF202020"))
        names = ", ".join(c[1] for c in self.cams)
        if n > 1:
            names = event_title(names, label)
        border = s.get("priority_border", "steady")
        names = marked_title(names, priority, border, kodiapi.core_tr())
        self.label = xbmcgui.ControlLabel(x + 8, y, w - 16, t, names, font=font, textColor="FFFFFFFF",
                                          alignment=0x00000004)
        self.addControl(self.label)
        self.settings = s
        orientation = parse_orientation(s.get("orientation", ""))
        self.tiles = []
        for (name, title, url), (tx, ty, tw, th) in zip(self.cams, tiles):
            img = xbmcgui.ControlImage(x + tx, y + ty, tw, th, "", aspectRatio=2)
            self.addControl(img)
            orient(img, name, orientation)
            self.tiles.append({"name": name, "url": url, "control": img, "box": (x + tx, y + ty, tw, th)})
        for tile in self.tiles:
            tile["masks"] = add_masks(self, s)  # #11
        for tile, (tx, ty, tw, th) in zip(self.tiles, tiles):
            add_error_overlay(self, tile, x + tx, y + ty, tw, th, font)
        self.stream = self.cams[0][0] if n == 1 else ",".join(c[0] for c in self.cams)
        self.title_text = names
        self.hint_label = None
        if keys and n == 1:  # dark strip with the key hint at the bottom of the picture
            hh = max(22, t - 8)
            self.addControl(xbmcgui.ControlImage(x, y + total_h - hh, w, hh, white(), colorDiffuse="99000000"))
            self.hint_label = xbmcgui.ControlLabel(x + 8, y + total_h - hh, w - 16, hh, "",
                                                   font=title_font_name("small", kodiapi.skin_fonts(), ts),
                                                   textColor="FFDDDDDD", alignment=0x00000004 | 0x00000002)
            self.addControl(self.hint_label)
        self.frame = Frame(self, x, y, w, total_h, priority_mark(priority, border))
        self.orientation = orientation
        self.duration = s["duration"]
        self.feeder = Feeder(self.tiles, s)
        self.feeder.on_unreachable = self.unreachable
        self.feeder.on_loaded = lambda tile: show_error(tile, False)
        self.timer = None
        self.ptz_label(False)

    def start(self, seconds):
        self.feeder.start()
        self.frame.start()
        self.extend(seconds)

    def extend(self, seconds):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(seconds, lambda: self.ctl.window_timeout(self))
        self.timer.daemon = True
        self.timer.start()

    def switch(self, name, title, url):
        """Show another camera in the single-camera window."""
        if len(self.tiles) != 1:
            return
        old = self.tiles[0]["name"]
        self.tiles[0] = dict(self.tiles[0], name=name, url=url)
        self.feeder.replace(old, self.tiles[0])
        orient(self.tiles[0]["control"], name, self.orientation)
        show_error(self.tiles[0], False)
        self.stream = name
        self.title_text = title
        self.ptz_label(False)

    def ptz_label(self, on):
        self.label.setLabel(self.title_text)
        if self.hint_label is not None:
            self.hint_label.setLabel(hint("ptz", self.settings) if on else
                                     hint("window", self.settings, has_ptz(self.stream, self.settings)))

    def unreachable(self, tile, bad):
        count_unreachable(bad)
        show_error(tile, bad)
        if len(self.tiles) != 1:
            return
        if bad:
            self.label.setLabel(kodiapi.tr(30254) % self.title_text)
        else:
            self.ptz_label(self.ptz is not None)

    def single(self):
        return len(self.tiles) == 1

    def ptz_used(self):
        self.extend(max(self.duration, 30))

    def stop(self):
        if self.timer:
            self.timer.cancel()
        self.frame.stop()
        if self.ptz is not None:
            self.ptz.stop()
        self.feeder.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        self.window_key(action)


VIDEO_XML_DIR = ("videowindow", "resources", "skins", "Default")


def video_xml(s, priority):
    """Writes the skin XML of the video window for the current settings into the profile (Kodi loads window XML
    from <scriptPath>/resources/skins/Default/720p/) and returns (file name, script path, geometry)."""
    import hashlib
    import shutil
    ts = s.get("text_size", "normal")
    x, y, w, h, t = window_geometry(s["position"], s["size"], SCREEN_W, SCREEN_H, s["title_size"], ts)
    fonts = kodiapi.skin_fonts()
    hint_h = max(22, t - 8)
    mark = priority_mark(priority, s.get("priority_border", "steady"))
    xml = video_window_xml(x, y, w, h, t, title_font_name(s["title_size"], fonts, ts),
                           title_font_name("small", fonts, ts), hint_h, mark, bool(masks_of(s)))
    base = os.path.join(kodiapi.profile_dir(), *VIDEO_XML_DIR)
    folder, media = os.path.join(base, "720p"), os.path.join(base, "media")
    for d in (folder, media):
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(os.path.join(media, "white.png")):
        shutil.copyfile(white(), os.path.join(media, "white.png"))
    name = "camalert-video-%s.xml" % hashlib.sha1(xml.encode("utf-8")).hexdigest()[:10]
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        for old in os.listdir(folder):  # one file per look; old looks are not needed any more
            if old.startswith("camalert-video-"):
                _remove(os.path.join(folder, old))
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
    return name, os.path.join(kodiapi.profile_dir(), VIDEO_XML_DIR[0]), (x, y, w, h, t)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


class VideoWindow(CornerKeys, PtzMode, xbmcgui.WindowXMLDialog):
    """#129: the corner window with the camera's live stream as video (Kodi plays it 'windowed'; the skin's video
    window control shows it inside this dialog). The controller starts and stops the stream; the window shows the
    first picture (still) until the video runs, the title, the key hint and the priority frame."""

    def setup(self, ctl, name, title, snap, s, priority="normal", geo=None):
        self.ctl, self.stream, self.keys, self.settings = ctl, name, s["window_keys"], s
        self.box = (geo[0], geo[1] + geo[4], geo[2], geo[3]) if geo else None  # where the video is (#11)
        self.masks = []
        self.snap, self.duration, self.priority = snap, s["duration"], priority
        self.title_text = marked_title(title, priority, s.get("priority_border", "steady"), kodiapi.core_tr())
        self.timer, self.frame, self.closed, self.still_path = None, None, False, ""
        return self

    def onInit(self):
        self.label = self.getControl(VIDEO_TITLE)
        self.hint_label = self.getControl(VIDEO_HINT)
        mark = priority_mark(self.priority, self.settings.get("priority_border", "steady"))
        bars = []
        if mark:
            bars = [self.getControl(cid) for cid in VIDEO_FRAME]
        self.frame = Frame(self, 0, 0, 0, 0, mark, bars)
        self.frame.start()
        if self.box and masks_of(self.settings):  # #11
            self.masks = add_masks(self, self.settings, [self.getControl(cid) for cid in VIDEO_MASKS])
            self.place()
        self.ptz_label(False)

    def place(self):
        if self.masks:
            place_masks(self.masks, self.stream, self.settings, self.box, IMAGE_SIZES.get(self.stream) or (16, 9))

    def start(self, seconds):
        if self.snap:
            threading.Thread(target=self.fetch_still, daemon=True).start()
        self.extend(seconds)

    def fetch_still(self):
        """The first picture (warm feed / Protect / go2rtc cache, #109-#111) under the video until it runs."""
        path = os.path.join(kodiapi.temp_dir(), "video_still_%x.jpg" % (id(self) & 0xffffff))
        try:
            sources.picture(self.stream, self.snap, path, self.settings["verify_ssl"], True, self.settings)
        except Exception as e:
            kodiapi.log("still picture for the video window failed: %s" % e, "verbose")
            return
        if self.closed:
            _remove(path)
            return
        size = jpeg_file_size(path)
        if size:
            IMAGE_SIZES[self.stream] = size
            self.place()
        self.still_path = path
        self.setProperty("still", path)

    def extend(self, seconds):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(seconds, lambda: self.ctl.window_timeout(self))
        self.timer.daemon = True
        self.timer.start()

    def switch(self, name, title, url):
        """Another camera (LEFT/RIGHT): the controller plays its stream; here the title and the still."""
        self.stream, self.snap = name, url
        self.title_text = marked_title(title, self.priority, self.settings.get("priority_border", "steady"),
                                       kodiapi.core_tr())
        self.setProperty("still", "")
        self.place()
        if url:
            threading.Thread(target=self.fetch_still, daemon=True).start()
        self.ptz_label(False)

    def ptz_label(self, on):
        if getattr(self, "label", None) is None:
            return
        self.label.setLabel(self.title_text)
        self.hint_label.setLabel(hint("ptz", self.settings) if on else
                                 hint("window", self.settings, has_ptz(self.stream, self.settings)))

    def ptz_used(self):
        self.extend(max(self.duration, 30))

    def stop(self):
        self.closed = True
        if self.timer:
            self.timer.cancel()
        if self.frame is not None:
            self.frame.stop()
        if self.ptz is not None:
            self.ptz.stop()
        _remove(self.still_path)
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        self.window_key(action)


class FullScreen(xbmcgui.WindowDialog):
    """Mosaic (all tiles at once) or tour (one camera after the other)."""

    def __init__(self, ctl, cams, s, tour=False, seconds=0, interval=8):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.cams, self.tour, self.interval = ctl, list(cams), tour, interval
        self.index, self.hold, self.active = 0, False, True
        self.addControl(xbmcgui.ControlImage(-40, -40, SCREEN_W + 80, SCREEN_H + 80, white(), colorDiffuse="FF000000"))
        self.orientation = parse_orientation(s.get("orientation", ""))
        ts = s.get("text_size", "normal")  # #48
        scale, font = text_scale(ts), text_font_name(ts, kodiapi.skin_fonts())
        top = int(36 * scale)
        if tour:
            img = xbmcgui.ControlImage(0, top, SCREEN_W, SCREEN_H - top, "", aspectRatio=2)
            self.addControl(img)
            self.tiles = [{"name": self.cams[0][0], "url": self.cams[0][2], "control": img,
                           "box": (0, top, SCREEN_W, SCREEN_H - top), "masks": add_masks(self, s)}]
            orient(img, self.cams[0][0], self.orientation)
            add_error_overlay(self, self.tiles[0], 0, top, SCREEN_W, SCREEN_H - top, font)
        else:
            self.tiles = []
            cells = grid(len(self.cams), SCREEN_W, SCREEN_H - top)
            for (name, title, url), (x, y, w, h) in zip(self.cams, cells):
                img = xbmcgui.ControlImage(x, y + top, w, h, "", aspectRatio=2)
                self.addControl(img)
                orient(img, name, self.orientation)
                self.tiles.append({"name": name, "url": url, "control": img, "box": (x, y + top, w, h)})
                self.tiles[-1]["masks"] = add_masks(self, s)  # #11
                add_error_overlay(self, self.tiles[-1], x, y + top, w, h, font)
            for (name, title, url), (x, y, w, h) in zip(self.cams, cells):  # labels on top of all pictures
                # dark strip behind the label: ControlLabel has no shadowColor in any Kodi version (#25)
                lh = int(34 * scale)
                self.addControl(xbmcgui.ControlImage(x, y + top + h - lh, w, lh, white(), colorDiffuse="99000000"))
                self.addControl(xbmcgui.ControlLabel(x + 8, y + top + h - lh, w - 16, lh - 4, title, font=font,
                                                     textColor="FFFFFFFF"))
        self.title = xbmcgui.ControlLabel(12, 2, SCREEN_W - 24, top - 4, "", font=font, textColor="FFFFFFFF")
        self.addControl(self.title)
        self.feeder = Feeder(self.tiles, s)
        self.feeder.on_unreachable = self.unreachable
        self.feeder.on_loaded = lambda tile: show_error(tile, False)
        self.timer = None
        self.close_timer = None
        self.seconds = seconds
        self.update_title()

    def update_title(self):
        if self.tour:
            name, title, _url = self.cams[self.index]
            self.title.setLabel("%s      %s" % (tour_status(title, self.index + 1, len(self.cams), self.hold,
                                                            kodiapi.core_tr()), hint("tour")))
        else:
            self.title.setLabel("%s      %s" % (kodiapi.tr(30192), hint("mosaic")))

    def unreachable(self, tile, bad):
        count_unreachable(bad)
        show_error(tile, bad)

    def start(self):
        self.feeder.start()
        if self.tour:
            self.schedule()
        if self.seconds:
            self.close_timer = threading.Timer(self.seconds, lambda: self.ctl.fullscreen_closed(self))
            self.close_timer.daemon = True
            self.close_timer.start()

    def schedule(self):
        if self.timer:
            self.timer.cancel()
        if not self.hold:
            self.timer = threading.Timer(self.interval, lambda: self.step(1))
            self.timer.daemon = True
            self.timer.start()

    def step(self, delta):
        if not self.active:
            return
        self.index = (self.index + delta) % len(self.cams)
        name, title, url = self.cams[self.index]
        old = self.tiles[0]["name"]
        self.tiles[0] = dict(self.tiles[0], name=name, url=url)
        self.feeder.replace(old, self.tiles[0])
        orient(self.tiles[0]["control"], name, self.orientation)
        show_error(self.tiles[0], False)
        self.update_title()
        self.schedule()

    def stop(self):
        self.active = False
        for t in (self.timer, self.close_timer):
            if t:
                t.cancel()
        self.feeder.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        aid = action.getId()
        if aid in VOLUME_KEYS:
            kodiapi.builtin(VOLUME_KEYS[aid])
            return
        what = tour_key(aid, action.getButtonCode()) if self.tour else mosaic_key(aid)
        if what == "close":
            self.ctl.fullscreen_closed(self)
        elif what in ("prev", "next"):
            self.step(-1 if what == "prev" else 1)
        elif what == "hold":
            self.hold = not self.hold
            self.update_title()
            self.schedule()
        elif what == "live":
            name = self.cams[self.index][0]
            self.ctl.fullscreen_closed(self)
            self.ctl.show(name, None, "live", "high")


class LiveOverlay(PtzMode, xbmcgui.WindowDialog):

    """Thin bar over the live camera picture: BACK/STOP ends live, < > other camera, MENU/INFO = PTZ mode."""

    def __init__(self, ctl, name, title, s=None):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl, self.name, self.title_text = ctl, name, title
        self.settings = s if s is not None else kodiapi.settings()
        ts = self.settings.get("text_size", "normal")  # #48
        bar = int(40 * text_scale(ts))
        self.bg = xbmcgui.ControlImage(0, SCREEN_H - bar, SCREEN_W, bar, white(), colorDiffuse="99000000")
        self.addControl(self.bg)
        self.label = xbmcgui.ControlLabel(16, SCREEN_H - bar + 2, SCREEN_W - 32, bar - 4, "",
                                          font=text_font_name(ts, kodiapi.skin_fonts()), textColor="FFFFFFFF")
        self.addControl(self.label)
        self.masks = add_masks(self, self.settings)  # #11: over the live video
        self.place()
        self.ptz_label(False)

    def place(self):
        place_masks(self.masks, self.name, self.settings, (0, 0, SCREEN_W, SCREEN_H),
                    IMAGE_SIZES.get(self.name) or (16, 9))

    def set_camera(self, name, title):
        if self.ptz is not None:
            self.ptz_leave()
        self.name, self.title_text = name, title
        self.place()
        self.ptz_label(False)

    def ptz_label(self, on):
        self.label.setLabel("%s      %s" % (self.title_text, hint("ptz", self.settings) if on else
                                           hint("live", self.settings, has_ptz(self.name, self.settings))))

    def ptz_used(self):
        self.ctl.extend_live()

    def stop(self):
        if self.ptz is not None:
            self.ptz.stop()
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        aid = action.getId()
        if self.ptz_action(aid):
            return
        colour = colour_name(action.getButtonCode())
        if colour:
            if self.ctl.colour_key(self.name, colour) == "ptz" and self.ptz_toggle(self.name):
                self.ptz_used()
            return
        what = live_key(aid)
        if what == "ptz":
            if self.ptz_toggle(self.name):
                self.ptz_used()
            return
        if aid in VOLUME_KEYS:
            kodiapi.builtin(VOLUME_KEYS[aid])
        elif what in ("prev", "next"):
            self.ctl.live_other(-1 if what == "prev" else 1)
        elif what == "close":
            self.ctl.hide()
        elif what == "pause":
            kodiapi.builtin("Action(Pause)")


class LiveStillWindow(xbmcgui.WindowDialog):
    """Full-screen still picture while a live view opens (#91); the controller closes it as soon as the camera
    picture is on screen. BACK/STOP ends the live view, < > another camera, like the live overlay."""

    def __init__(self, ctl, path, name=None, s=None):
        xbmcgui.WindowDialog.__init__(self)
        self.ctl = ctl
        self.addControl(xbmcgui.ControlImage(0, 0, SCREEN_W, SCREEN_H, white(), colorDiffuse="FF000000"))
        self.image = xbmcgui.ControlImage(0, 0, SCREEN_W, SCREEN_H, path, aspectRatio=2)
        self.addControl(self.image)
        if name:  # #11
            place_masks(add_masks(self, s), name, s, (0, 0, SCREEN_W, SCREEN_H), jpeg_file_size(path))

    def stop(self):
        try:
            self.close()
        except Exception:
            pass

    def onAction(self, action):
        what = live_key(action.getId())
        if what in ("prev", "next"):
            self.ctl.live_other(-1 if what == "prev" else 1)
        elif what == "close":
            self.ctl.hide()
