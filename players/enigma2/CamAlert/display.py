# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The three ways to show a camera: photo window, switch to live stream, notification."""
import os
import ssl
import urllib.request

import time

from enigma import eActionMap, eTimer, ePicLoad, getDesktop, eServiceReference, eDVBVolumecontrol, ePoint, eSize
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
from .camalert_core.devices.client import secure_file

from .camalert_core.access import url_target
from .camalert_core.cameras import (display_name, known_camera, live_stream_name, neighbour, parse_camera_file,
                                    parse_cams, parse_orientation, parse_refresh, parse_titles, refresh_delay, slug,
                                    title_for)
from .camalert_core import present
from .camalert_core.frames import LiveStill, ProtectSnapshots, Snapshots, STILL_MAX_SECONDS
from .camalert_core.privacy import GUEST, MAX_MASKS, guest_hidden, guest_visible, jpeg_file_size, mask_rects, parse_masks
from .camalert_core.warm import WarmFeeds
from .camalert_core.events import TEST_SOURCE, add_event, event_title, is_test
from .camalert_core.api import screen_name
from .camalert_core.keymap import button_event
from .camalert_core.layout import grid, strip_geometry, text_scale, title_font, window_geometry
from .camalert_core.style import FLASH_MS, marked_title, priority_mark
from .camalert_core.obs.log import redact
from .camalert_core.obs.metrics import metrics_text
from .camalert_core.triggers.foscam import FoscamSource
from .camalert_core.triggers.unifi import STATUS as UNIFI_STATUS, UnifiSource, labels as unifi_labels
from .camalert_core.rules import (blocked_by_rules, clock_tuple, cooldown_seconds, decide, dnd_blocks, in_cooldown,
                                  in_time_window, lowered_volume, pick_mode, pick_priority, should_pause)
from .camalert_core.update import latest_tag, newer_version, UPDATE_INTERVAL
from .camalert_core.urls import normalize_server, rtsp_url, snapshot_url, split_credentials, tcp_url, valid_port
from .helpable import HelpBase, help_actions, init_help
from .keys import actionmap_actions, button_for, key_action, ptz_key
from .services import chime_command, github_repo, is_media_ref, service_ref, stream_from_ref

PHOTO = "/tmp/camalert.jpg"
STILL = "/tmp/camalert-still.jpg"  # still picture of a live view that is opening (#91)
# Opening a stream holds Enigma2 (and the Python threads) for about 2.5 s, so the live view first shows its still
# picture and starts the stream after it, or after STILL_WAIT_SECONDS without a picture (#91).
STILL_WAIT_SECONDS = 1.5
STILL_DRAW_MS = 100  # time to draw the still before the stream takes the box
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


def key_actions(screen, context, handlers, prio=-1):
    """Action maps of a full-screen CamAlert screen from the key map, with help texts for the HELP key."""
    by_action = {a: label for acts, label in present.HINTS[context] for a in acts}
    for ctx, acts in sorted(actionmap_actions(context, handlers).items()):
        help_actions(screen, "actions_" + ctx, ctx,
                     {name: (fn, _(by_action.get(action, action))) for name, (fn, action) in acts.items()}, prio)


def window_hint(stream):
    return hint("window", stream)


def with_hint(title, text):
    return title + (present.SEPARATOR + text if text else "")


# Estimated average width of a character of the skin's Regular font, as a fraction of the font size (mixed-case
# text in common sans-serif skin fonts is about 0.5; a little margin on top).
CHAR_W = 0.55


def fit_font(text, width, font, minimum=None):
    """Largest font size <= font at which `text` fits on one line of `width` pixels (#56); never below `minimum`
    (default 60 % of font). Labels that use it also get noWrap, so a text that still does not fit is cut, not
    wrapped onto a half-visible second line."""
    low = max(1, int(font * 0.6)) if minimum is None else minimum
    if not text:
        return font
    return max(low, min(font, int(width / (CHAR_W * len(text)))))


def hint_widget(x, y, w, h, f, text, font):
    """Skin of the key-hint strip at the bottom of a photo or multi-camera window (#56: the hint no longer shares
    the title bar, where it did not fit at size medium). Hidden when the window takes no keys."""
    return ('<widget name="hint" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" '
            'backgroundColor="#202020" halign="center" valign="center" noWrap="1" zPosition="5" />'
            % (x, y, w, h, fit_font(text, w - int(20 * f), font)))


def text_size():
    """The text size setting (#48): every CamAlert screen scales its fonts with it."""
    return config.plugins.camalert.text_size.value


def tf(f):
    """Font factor: screen factor f (width / 1920) times the text size (#48)."""
    return f * text_scale(text_size())


def frame_skin(w, h, f, mark):
    """Skin of the priority frame (#48): four bars around a window, in the priority colour; '' without a mark.
    The window title carries the priority word as well, so the colour is never the only signal."""
    if not mark:
        return ""
    b = max(3, int(6 * f))
    return "".join('<widget name="frame%d" position="%d,%d" size="%d,%d" backgroundColor="%s" zPosition="6" />'
                   % (i, x, y, fw, fh, mark["colour"])
                   for i, (x, y, fw, fh) in enumerate(((0, 0, w, b), (0, h - b, w, b), (0, 0, b, h), (w - b, 0, b, h))))


class Frame(object):
    """The priority frame of a window (#48): steady, or flashing at style.FLASH_MS (at most 3 flashes a second)."""

    def __init__(self, screen, mark):
        self.screen, self.mark, self.on = screen, mark, True
        self.timer = None
        if mark:
            for i in range(4):
                screen["frame%d" % i] = Label("")
            if mark["flash"]:
                self.timer = eTimer()
                self.timer.callback.append(self.toggle)

    def start(self):
        if self.timer is not None:
            self.timer.start(FLASH_MS, False)

    def toggle(self):
        self.on = not self.on
        for i in range(4):
            key = "frame%d" % i
            if key in self.screen:
                (self.screen[key].show if self.on else self.screen[key].hide)()

    def stop(self):
        if self.timer is not None:
            self.timer.stop()


def hint_label(text):
    label = Label(text)
    if not text:
        label.hide()
    return label


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


SERVER_MAP = {}  # camera name -> (go2rtc server, stream) of the last camera list (#15)


def go2rtc_servers():
    """The go2rtc servers in order: the setting `server` first, then `more_servers` (#15)."""
    from .camalert_core.servers import server_list
    c = config.plugins.camalert
    return server_list(c.server.value, c.more_servers.value)


def resolve_camera(name):
    """(go2rtc server, stream) for a camera name; (None, name) without a server."""
    from .camalert_core.servers import resolve
    return resolve(name, go2rtc_servers(), SERVER_MAP)


def camera_urls(name):
    """(live url, snapshot url or None, title) for a camera in the current mode; None if unknown."""
    c = config.plugins.camalert
    if c.source.value == "direct":
        for cam in direct_cameras():
            if cam["name"] == name:
                return tcp_url(cam["rtsp"]), cam["snapshot"], cam["title"]
        return None
    server, stream = resolve_camera(name)
    if not server:
        return None
    title = title_for(name, parse_titles(c.titles.value))
    live_server, live = resolve_camera(live_stream_name(name, c.substreams.value))
    return (rtsp_url(live_server, live, valid_port(c.rtsp_port.value, 8554)), snapshot_url(server, stream), title)


def trigger_settings():
    """The settings of the trigger sources (#6), with the keys camalert_core.triggers expects."""
    c = config.plugins.camalert
    return {"frigate_enabled": c.frigate_enabled.value, "frigate_prefix": c.frigate_prefix.value,
            "frigate_labels": c.frigate_labels.value, "frigate_map": c.frigate_map.value,
            "frigate_priority": c.frigate_priority.value, "frigate_mode": c.frigate_mode.value,
            "frigate_seconds": int(c.frigate_seconds.value),
            "foscam_enabled": c.foscam_enabled.value, "foscam_priority": c.foscam_priority.value,
            "foscam_mode": c.foscam_mode.value, "foscam_seconds": int(c.foscam_seconds.value),
            "foscam_label": _("Motion"),
            "unifi_enabled": c.unifi_enabled.value, "unifi_kinds": c.unifi_kinds.value,
            "unifi_cameras": c.unifi_cameras.value, "unifi_priority": c.unifi_priority.value,
            "unifi_mode": c.unifi_mode.value, "unifi_seconds": int(c.unifi_seconds.value),
            "unifi_rules": c.unifi_rules.value, "unifi_camera_rules": c.unifi_camera_rules.value,
            "unifi_labels": unifi_labels(_)}


def chime_wanted(setting, priority):
    """Doorbell chime: 'off', 'high' (doorbell and alarm) or 'all' requests (schema version 2, #39)."""
    return setting == "all" or (setting == "high" and priority in ("high", "alarm"))


COMPOSITES = set()  # composite streams (an own mosaic in go2rtc) of the last camera list (#125)


def all_camera_names():
    """Camera names in the current mode (go2rtc mode needs a network call; call from a thread)."""
    global COMPOSITES
    if config.plugins.camalert.source.value == "direct":
        return [cam["name"] for cam in direct_cameras()]
    global SERVER_MAP
    servers = go2rtc_servers()
    if not servers:  # no (valid) go2rtc address: nothing to ask, no network call (#73)
        return []
    from .setup import fetch_stream_info
    from .camalert_core.servers import combine
    from .camalert_core.warm import visible_cameras
    per, error = [], None
    for srv in servers:  # #15: every server on its own; one that does not answer only drops its own cameras
        try:
            names, comp = fetch_stream_info(srv.url)
        except Exception as e:  # noqa: BLE001
            if len(servers) == 1:
                raise
            log("go2rtc server %s not reachable: %s" % (srv.url, e))
            error = e
            continue
        per.append((srv, names, comp))
    if not per and error is not None:
        raise error
    names, COMPOSITES, SERVER_MAP = combine(per)
    return visible_cameras(names, config.plugins.camalert.ready_cameras.value)  # #113


def overview_names(names):
    """Default cameras of a mosaic or tour: all cameras except composite streams (#125) and guest-mode cameras."""
    from .camalert_core.urls import overview_cameras
    return guest_filter(overview_cameras(names, COMPOSITES))


def guest_filter(names):
    """names without the cameras guest mode hides right now (#11)."""
    c = config.plugins.camalert
    return guest_visible(names, c.guest_mode.value, c.guest_cameras.value)


def is_guest_hidden(name):
    c = config.plugins.camalert
    return guest_hidden(name, c.guest_mode.value, c.guest_cameras.value)


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


def _read(url):
    with open_url(url) as r:
        return r.read()


WARM = WarmFeeds(lambda url: open_url(url, timeout=10))  # #111: ready cameras while the receiver is on
SNAPSHOTS = Snapshots(lambda url: _read(url), ProtectSnapshots(), WARM)
_SNAPSHOT_KEY = [None]


def snapshot_sources():
    """SNAPSHOTS with the UniFi Protect consoles of the devices file (#109); configured again only when the devices
    file or the settings change, so a skipped camera stays skipped."""
    c = config.plugins.camalert
    ctl = Controller.instance
    devs = ctl.load_devices() if ctl is not None else {}
    key = (getattr(ctl, "devices_mtime", None), c.protect_snapshots.value, c.unifi_cameras.value)
    if key != _SNAPSHOT_KEY[0]:
        _SNAPSHOT_KEY[0] = key
        SNAPSHOTS.protect.configure(list(devs.values()), c.unifi_cameras.value, c.protect_snapshots.value)
    return SNAPSHOTS


def _download(url, path=PHOTO, orientation=None, first=False, camera=None):
    """Fetches one picture into path (in a thread): from UniFi Protect for a Protect camera (#109), else from go2rtc,
    the first picture of a window from go2rtc's cache (#110)."""
    data, _source = snapshot_sources().fetch(camera, url, first)
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


IMAGE_SIZES = {}  # camera -> (width, height) of its last picture: where the masks go over live video (#11)
_MASKS = [None, {}]


def current_masks():
    """The privacy masks of the settings (#11), parsed once per change."""
    text = config.plugins.camalert.privacy_masks.value or ""
    if _MASKS[0] != text:
        _MASKS[0], _MASKS[1] = text, parse_masks(text)
    return _MASKS[1]


def mask_skin(prefix, z=8):
    """Skin of the black mask boxes of one picture (none without masks): moved into place per picture."""
    if not current_masks():
        return ""
    return "".join('<widget name="%s%d" position="0,0" size="1,1" backgroundColor="#000000" zPosition="%d" />'
                   % (prefix, i, z) for i in range(MAX_MASKS))


class Masks(object):
    """Privacy masks (#11) over one picture of a screen: black boxes, placed after each picture."""

    def __init__(self, screen, prefix="mask"):
        self.screen = screen
        self.keys = ["%s%d" % (prefix, i) for i in range(MAX_MASKS)] if current_masks() else []
        for k in self.keys:
            screen[k] = Label("")
        if self.keys:
            screen.onLayoutFinish.append(self.hide_all)

    def hide_all(self):
        for k in self.keys:
            self.screen[k].hide()

    def place(self, name, box, image_size=None):
        """Covers the masked areas of camera `name` drawn in box (x, y, w, h) of the screen."""
        if not self.keys:
            return
        if image_size:
            IMAGE_SIZES[name] = image_size
        rects = mask_rects(name, current_masks(), box, image_size or IMAGE_SIZES.get(name))
        for i, k in enumerate(self.keys):
            w = self.screen[k]
            if i < len(rects):
                x, y, rw, rh = rects[i]
                try:
                    w.instance.move(ePoint(x, y))
                    w.instance.resize(eSize(rw, rh))
                except Exception as e:  # never show the picture without its mask: hide the picture instead
                    log("privacy mask failed:", e)
                    raise
                w.show()
            else:
                w.hide()


class Tile(object):
    """One camera in the mosaic: keeps fetching snapshots into its own pixmap widget."""

    def __init__(self, screen, key, stream, url, size, box=None, masks=None):
        self.screen, self.key, self.stream, self.url, self.size = screen, key, stream, url, size
        self.box, self.masks = box or (0, 0, size[0], size[1]), masks  # #11: where the tile is, its mask boxes
        self.path = "/tmp/camalert_%s.jpg" % key
        self.picload = ePicLoad()
        self.busy = False
        self.failures = 0
        self.error_key = key.replace("tile", "error")
        self.first = True  # until the first picture: 'Loading picture...' and a cached frame (#110)
        set_error(screen, self.error_key, key, "loading")

    def fetch(self):
        if not getattr(self.screen, "active", False) or self.busy or not self.url:
            return
        self.busy = True
        threads.deferToThread(_download, self.url, self.path, orientation_for(self.stream), self.first,
                              self.stream).addCallbacks(self.loaded, self.failed)

    def loaded(self, _path):
        self.busy = False
        if not getattr(self.screen, "active", False) or not self.url:
            return
        if self.failures >= 2 or self.first:
            set_error(self.screen, self.error_key, self.key, False)
        self.first = False
        self.failures = 0
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(self.path, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    if self.masks:
                        self.masks.place(self.stream, self.box, jpeg_file_size(self.path))
                    self.screen[self.key].instance.setPixmap(ptr)
        except Exception as e:
            log("mosaic tile failed:", e)
        reactor.callLater(delay_for(self.stream, 0.3), self.fetch)

    def failed(self, err):
        self.busy = False
        self.failures += 1
        if not getattr(self.screen, "active", False) or not self.url:
            return
        if self.failures == 2:  # a dimmed tile with text instead of a frozen or black picture (#49)
            STATS["unreachable"] += 1
            log("tile %s: camera not reachable: %s" % (self.stream, err.getErrorMessage()), level="verbose")
            set_error(self.screen, self.error_key, self.key, True)
        reactor.callLater(3, self.fetch)


def error_widget(name, x, y, w, h, f):
    """Skin of the 'camera not reachable' overlay of a tile (hidden until the camera fails twice)."""
    return ('<widget name="%s" position="%d,%d" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
            'foregroundColor="#c0c0c0" backgroundColor="#303030" zPosition="4" />'
            % (name, x, y, w, h, max(int(22 * tf(f)), min(int(34 * tf(f)), h // 6))))


def set_error(screen, error_key, picture_key, on):
    """Shows or hides the text overlay of a tile (and the picture under it): on = True for 'Camera not reachable'
    (#49), 'loading' for 'Loading picture...' until the first picture arrives (#110), False for the picture."""
    if error_key not in screen:
        return
    if on:
        screen[error_key].setText(present.tile_label("loading" if on == "loading" else "unreachable", _))
        screen[error_key].show()
        if picture_key in screen:
            screen[picture_key].hide()
    else:
        screen[error_key].hide()
        if picture_key in screen:
            screen[picture_key].show()


class MosaicScreen(Screen, HelpBase):
    """Full-screen grid with up to 9 cameras (photo mode). Closes with EXIT/OK or after `seconds` (0 = stay open)."""

    def __init__(self, session, cams, seconds=0):
        """cams: list of (name, title, snapshot url)."""
        size = getDesktop(0).size()
        sw, sh = size.width(), size.height()
        f = sw / 1920.0
        top = int(50 * tf(f))
        tiles = grid(len(cams), sw, sh - top)
        parts = ['<screen name="CamAlertMosaic" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#000000">' % (sw, sh),
                 '<widget name="title" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#000000" />'
                 % (int(20 * f), int(8 * f), sw - int(40 * f), int(40 * tf(f)), int(28 * tf(f)))]
        for i, (x, y, w, h) in enumerate(tiles):
            parts.append('<widget name="tile%d" position="%d,%d" size="%d,%d" alphatest="off" />' % (i, x, y + top, w, h))
            parts.append(error_widget("error%d" % i, x, y + top, w, h, f))
            parts.append(mask_skin("mask%d_" % i, 3))
            parts.append('<widget name="label%d" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" noWrap="1" zPosition="5" />'
                         % (i, x + int(8 * f), y + top + int(8 * f), w // 2, int(34 * tf(f)), int(24 * tf(f))))
        parts.append("</screen>")
        self.skin = "".join(parts)
        Screen.__init__(self, session)
        init_help(self)
        self["title"] = Label(_("Cameras") + present.SEPARATOR + hint("mosaic"))
        self.tiles = []
        for i, ((name, title, url), (x, y, w, h)) in enumerate(zip(cams, tiles)):
            self["tile%d" % i] = Pixmap()
            self["error%d" % i] = Label("")
            self["label%d" % i] = Label(" " + title + " ")
            url = url.replace("width=640", "width=%d" % min(960, w)) if "/api/frame.jpeg" in url else url
            self.tiles.append(Tile(self, "tile%d" % i, name, url, (w, h), (x, y + top, w, h), Masks(self, "mask%d_" % i)))
        key_actions(self, "mosaic", {"close": self.close})
        self.active = False
        register_fullscreen(self)
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
        unregister_fullscreen(self)


def first_frame_events():
    """Service events that mean the live stream shows video (#91): the video size is known (all images, gstreamer
    and exteplayer3), or gstreamer started playing (OpenPLi family). Missing names are skipped."""
    try:
        from enigma import iPlayableService
    except ImportError:
        return set()
    return set(v for v in (getattr(iPlayableService, n, None) for n in ("evVideoSizeChanged", "evGstreamerPlayStarted"))
               if v is not None)


class LiveMaskScreen(Screen):
    """Privacy masks over live video (#11): a transparent full-screen layer with only the black boxes. The video
    keeps its aspect ratio; where it lands follows the camera's last picture (16:9 until one was seen)."""

    def __init__(self, session):
        size = getDesktop(0).size()
        self.size = (size.width(), size.height())
        self.skin = """<screen name="CamAlertLiveMask" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="6">
            %s
        </screen>""" % (self.size + (mask_skin("mask", 1),))
        Screen.__init__(self, session)
        self.masks = Masks(self)

    def place(self, stream):
        self.masks.place(stream, (0, 0) + self.size, IMAGE_SIZES.get(stream) or (16, 9))


class LiveStillScreen(Screen):
    """Full-screen still picture over a live view that is still opening (#91). The controller hides it at the
    first video frame; the picture keeps its aspect on black, like the live picture itself."""

    def __init__(self, session):
        size = getDesktop(0).size()
        self.size = (size.width(), size.height())
        self.skin = """<screen name="CamAlertLiveStill" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#00000000" zPosition="5">
            <widget name="photo" position="0,0" size="%d,%d" alphatest="off" zPosition="1" />
            %s
        </screen>""" % (self.size + self.size + (mask_skin("mask", 3),))
        Screen.__init__(self, session)
        self["photo"] = Pixmap()
        self.masks = Masks(self)  # #11
        self.picload = ePicLoad()

    def load(self, path, stream=None):
        """Shows the picture at path; False when it cannot be decoded (the live view then opens without it)."""
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(path, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    if stream:
                        self.masks.place(stream, (0, 0) + self.size, jpeg_file_size(path))  # #11
                    self["photo"].instance.setPixmap(ptr)
                    return True
        except Exception as e:
            log("showing still picture failed:", e)
        return False


class PhotoWindow(Screen):
    """Small always-on-top window that keeps fetching a fresh snapshot from go2rtc (about one every 1-2 s)."""

    def __init__(self, session, stream, url, title=None, keys=False, priority="normal"):
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t = window_geometry(c.position.value, c.size.value, size.width(), size.height(), c.title_size.value,
                                        text_size())
        f = size.width() / 1920.0
        mark = priority_mark(priority, c.priority_border.value)
        base_title = marked_title(title or display_name(stream), priority, c.priority_border.value, _)
        hint_text = window_hint(stream) if keys else ""
        font = title_font(c.title_size.value, size.width(), text_size())
        hh = max(int(t * 0.8), int(26 * tf(f)))
        self.skin = """<screen name="CamAlertPhoto" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">
            <eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />
            <widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" noWrap="1" zPosition="2" />
            <widget name="photo" position="0,%d" size="%d,%d" alphatest="off" zPosition="1" />
            %s
            %s
            %s
            %s
        </screen>""" % (x, y, w, h + t, w, h + t, int(10 * f), w - int(20 * f), t,
                        fit_font(base_title, w - int(20 * f), font), t, w, h,
                        error_widget("error", 0, t, w, h, f), mask_skin("mask", 3),
                        hint_widget(0, t + h - hh, w, hh, f, hint_text, int(font * 0.85)),
                        frame_skin(w, h + t, f, mark))
        Screen.__init__(self, session)
        self.frame = Frame(self, mark)
        self.stream, self.url, self.size = stream, url, (w, h)
        self.masks, self.box = Masks(self), (0, t, w, h)  # #11
        self.base_title = self.title_text = base_title
        self["title"] = Label(self.title_text)
        self["hint"] = hint_label(hint_text)
        self["photo"] = Pixmap()
        self["error"] = Label("")
        self.first = True  # until the first picture: 'Loading picture...' and a cached frame (#110)
        set_error(self, "error", "photo", "loading")
        self.picload = ePicLoad()
        self.busy = self.active = False
        self.failures = 0
        self.close_timer = eTimer()
        self.close_timer.callback.append(self.stop)

    def start(self, seconds):
        self.active = True
        self.show()
        self.frame.start()
        self.close_timer.start(seconds * 1000, True)
        self.fetch()

    def extend(self, seconds):
        self.close_timer.start(seconds * 1000, True)

    def fetch(self):
        if not getattr(self, "active", False) or self.busy:
            return
        self.busy = True
        threads.deferToThread(_download, self.url, PHOTO, orientation_for(self.stream), self.first,
                              self.stream).addCallbacks(self.loaded, self.failed)

    def loaded(self, _result):
        self.busy = False
        if not getattr(self, "active", False):  # window closed meanwhile (Enigma2 clears closed screens)
            return
        if self.failures >= 2:
            self["title"].setText(self.title_text)
        if self.failures >= 2 or self.first:
            set_error(self, "error", "photo", False)
        self.first = False
        self.failures = 0
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(PHOTO, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self.masks.place(self.stream, self.box, jpeg_file_size(PHOTO))  # before the picture (#11)
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
            set_error(self, "error", "photo", True)
        reactor.callLater(2, self.fetch)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.frame.stop()
        self.hide()
        Controller.instance.window_closed(self)


class StripWindow(Screen):
    """One corner window with 2-4 cameras (below each other, next to each other or 2 x 2); TV stays visible."""

    def __init__(self, session, cams, keys=False, label=None, priority="normal"):
        """cams: list of (name, title, snapshot url)."""
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t, tiles = strip_geometry(len(cams), c.strip_layout.value, c.position.value, c.size.value,
                                              size.width(), size.height(), text_size())
        f = size.width() / 1920.0
        mark = priority_mark(priority, c.priority_border.value)
        self.names = [n for n, _t, _u in cams]
        title_text = marked_title(event_title("  ·  ".join(t for _n, t, _u in cams), label), priority,
                                  c.priority_border.value, _)
        hint_text = hint("window", self.names[0], without=("other camera",)) if keys else ""
        font = min(title_font(c.title_size.value, size.width(), text_size()), int(t * 0.8))
        hh = max(int(t * 0.8), int(26 * tf(f)))
        parts = ['<screen name="CamAlertStrip" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">' % (x, y, w, h + t),
                 '<eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />' % (w, h + t),
                 '<widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" noWrap="1" zPosition="2" />'
                 % (int(10 * f), w - int(20 * f), t, fit_font(title_text, w - int(20 * f), font))]
        for i, (tx, ty, tw, th) in enumerate(tiles):
            parts.append('<widget name="tile%d" position="%d,%d" size="%d,%d" alphatest="off" zPosition="1" />' % (i, tx, ty, tw, th))
            parts.append(error_widget("error%d" % i, tx, ty, tw, th, f))
            parts.append(mask_skin("mask%d_" % i, 3))
            parts.append('<widget name="label%d" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" noWrap="1" zPosition="5" />'
                         % (i, tx + int(6 * f), ty + int(6 * f), tw // 2, int(30 * tf(f)), int(22 * tf(f))))
        parts.append(hint_widget(0, t + h - hh, w, hh, f, hint_text, int(font * 0.85)))
        parts.append(frame_skin(w, h + t, f, mark))
        parts.append("</screen>")
        self.skin = "".join(parts)
        Screen.__init__(self, session)
        self.frame = Frame(self, mark)
        self.stream = ",".join(self.names)
        self["title"] = Label(title_text)
        self["hint"] = hint_label(hint_text)
        self.tiles = []
        for i, ((name, title, url), (tx, ty, tw, th)) in enumerate(zip(cams, tiles)):
            self["tile%d" % i] = Pixmap()
            self["error%d" % i] = Label("")
            self["label%d" % i] = Label(" " + title + " ")
            url = url.replace("width=640", "width=%d" % min(960, tw)) if "/api/frame.jpeg" in url else url
            self.tiles.append(Tile(self, "tile%d" % i, name, url, (tw, th), (tx, ty, tw, th), Masks(self, "mask%d_" % i)))
        self.active = False
        self.close_timer = eTimer()
        self.close_timer.callback.append(self.stop)

    def start(self, seconds):
        self.active = True
        self.show()
        self.frame.start()
        self.close_timer.start(seconds * 1000, True)
        for t in self.tiles:
            t.fetch()

    def extend(self, seconds):
        self.close_timer.start(seconds * 1000, True)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.frame.stop()
        self.hide()
        Controller.instance.window_closed(self)


class NotifyWindow(Screen):
    """Notification mode (#49, like Kodi): a small window with one snapshot, the title (who/what) and the priority;
    it does not take the remote and closes by itself. Without a snapshot only the text is shown."""

    def __init__(self, session, stream, url, text):
        c = config.plugins.camalert
        size = getDesktop(0).size()
        x, y, w, h, t = window_geometry(c.position.value, "small", size.width(), size.height(), c.title_size.value,
                                        text_size())
        f = size.width() / 1920.0
        self.skin = """<screen name="CamAlertNotify" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#ff000000" zPosition="10">
            <eLabel position="0,0" size="%d,%d" backgroundColor="#202020" zPosition="0" />
            <widget name="title" position="%d,0" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" valign="center" zPosition="2" />
            <widget name="photo" position="0,%d" size="%d,%d" alphatest="off" zPosition="1" />
            %s
            %s
        </screen>""" % (x, y, w, h + t, w, h + t, int(10 * f), w - int(20 * f), t,
                        title_font(c.title_size.value, size.width(), text_size()),
                        t, w, h, error_widget("error", 0, t, w, h, f), mask_skin("mask", 3))
        Screen.__init__(self, session)
        self.stream, self.url, self.size = stream, url, (w, h)
        self.path = "/tmp/camalert_notify.jpg"
        self.masks, self.box = Masks(self), (0, t, w, h)  # #11
        self["title"] = Label(text)
        self["photo"] = Pixmap()
        self["error"] = Label("")
        set_error(self, "error", "photo", "loading" if url else False)
        self.picload = ePicLoad()
        self.active = False
        self.close_timer = eTimer()
        self.close_timer.callback.append(self.stop)

    def start(self, seconds):
        self.active = True
        self.show()
        self.close_timer.start(seconds * 1000, True)
        if self.url:
            threads.deferToThread(_download, self.url, self.path, orientation_for(self.stream), True,
                                  self.stream).addCallbacks(self.loaded, self.failed)

    def loaded(self, _path):
        if not getattr(self, "active", False):
            return
        set_error(self, "error", "photo", False)
        try:
            self.picload.setPara((self.size[0], self.size[1], 1, 1, False, 1, "#ff000000"))
            if self.picload.startDecode(self.path, 0, 0, False) == 0:
                ptr = self.picload.getData()
                if ptr is not None:
                    self.masks.place(self.stream, self.box, jpeg_file_size(self.path))  # #11
                    self["photo"].instance.setPixmap(ptr)
        except Exception as e:
            log("notification photo failed:", e)

    def failed(self, err):
        if getattr(self, "active", False):
            log("notification snapshot failed:", err.getErrorMessage(), level="verbose")
            set_error(self, "error", "photo", True)

    def stop(self):
        self.active = False
        self.close_timer.stop()
        self.hide()
        if Controller.instance is not None:
            Controller.instance.notice_closed(self)


def notification_text(title, priority):
    """'Camera: Person · Front door' (+ '  ·  High' / 'Alarm' for a higher priority), like Kodi's notification."""
    text = _("Camera: %s") % title
    if priority in ("high", "alarm"):
        text += "  ·  " + present.priority_label(priority, _)
    return text


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
        w, h = int(1100 * f), int(56 * tf(f))
        self.skin = ('<screen name="CamAlertPtz" position="%d,%d" size="%d,%d" flags="wfNoBorder" backgroundColor="#202020" zPosition="12">'
                     '<widget name="text" position="0,0" size="%d,%d" font="Regular;%d" halign="center" valign="center" '
                     'foregroundColor="#ffcc00" backgroundColor="#202020" /></screen>'
                     % ((size.width() - w) // 2, size.height() - h - int(60 * f), w, h, w, h, int(28 * tf(f))))
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


class TourScreen(Screen, HelpBase):
    """Full-screen camera tour: shows one camera after the other. LEFT/RIGHT = previous/next, OK = hold,
    GREEN or PLAY = live, EXIT = close."""

    def __init__(self, session, cams, interval):
        size = getDesktop(0).size()
        sw, sh = size.width(), size.height()
        f = sw / 1920.0
        self.skin = """<screen name="CamAlertTour" position="0,0" size="%d,%d" flags="wfNoBorder" backgroundColor="#000000">
            <widget name="tile0" position="0,0" size="%d,%d" alphatest="off" />
            %s
            %s
            <widget name="title" position="%d,%d" size="%d,%d" font="Regular;%d" foregroundColor="#ffffff" backgroundColor="#202020" zPosition="5" />
        </screen>""" % (sw, sh, sw, sh, error_widget("error0", 0, 0, sw, sh, f), mask_skin("mask", 3), int(30 * f), int(20 * f), sw - int(60 * f),
                        int(46 * tf(f)), int(30 * tf(f)))
        Screen.__init__(self, session)
        init_help(self)
        self.cams, self.index, self.hold, self.interval = cams, 0, False, interval
        self["tile0"] = Pixmap()
        self["error0"] = Label("")
        self.masks = Masks(self)  # #11
        self["title"] = Label("")
        self.active = False
        self.tile = None
        self.timer = eTimer()
        self.timer.callback.append(lambda: self.step(1, auto=True))
        key_actions(self, "tour", {
            "hold": self.toggle_hold, "close": self.close, "prev": lambda: self.step(-1), "next": lambda: self.step(1),
            "live": self.live})
        register_fullscreen(self)
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
        unregister_fullscreen(self)

    def load(self):
        name, title, url = self.cams[self.index]
        self["title"].setText(" %s " % with_hint(present.tour_status(title, self.index + 1, len(self.cams), self.hold, _),
                                                  hint("tour", name)))
        size = getDesktop(0).size()
        url = url.replace("width=640", "width=1280") if "/api/frame.jpeg" in url else url
        self.tile = Tile(self, "tile0", name, url, (size.width(), size.height()), None, self.masks)
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


def register_fullscreen(screen):
    """Mosaic and tour screens tell the controller they are open (#63), however they were opened (API, menu)."""
    ctl = Controller.instance
    if ctl is not None and screen not in ctl.fullscreens:
        ctl.fullscreens.append(screen)


def unregister_fullscreen(screen):
    ctl = Controller.instance
    if ctl is not None and screen in ctl.fullscreens:
        ctl.fullscreens.remove(screen)
        reactor.callLater(0.1, _notify)


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
        self.still = LiveStill()  # #91: still picture until the live stream shows video
        self.still_screen = None
        self.mask_screen = None  # privacy masks over live video (#11)
        self.still_timer = eTimer()
        self.still_timer.callback.append(self.hide_still)
        self.pending_play = None  # (token, service reference) of a live stream waiting for its still (#91)
        self.play_timer = eTimer()
        self.play_timer.callback.append(self.play_pending)
        self.first_frame = first_frame_events()
        events = getattr(session.nav, "event", None)
        if isinstance(events, list):
            events.append(self.service_event)
        self._names = []
        self._names_at = 0
        reactor.callLater(20, self.refresh_names)
        self.paused = False
        self.saved_volume = None
        self.keys = None
        self.notify_timer = eTimer()
        self.notify_timer.callback.append(self.resume_tv)
        self.notice = None
        self.fullscreens = []  # open MosaicScreen / TourScreen, oldest first (#63)
        self.source = None
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
        self.unifi_state = {}  # console name -> last answer, None (first poll / after an error) or "busy"
        self.unifi_timer = eTimer()
        self.unifi_timer.callback.append(self.poll_unifi)
        self.unifi_seconds = self.unifi_interval()
        self.unifi_timer.start(self.unifi_seconds * 1000, False)
        self.warm_timer = eTimer()  # #111: keep cameras ready only while the receiver is on (checked every second)
        self.warm_timer.callback.append(self.warm_tick)
        self.warm_timer.start(1000, False)
        self.button_hook = GlobalKeys()
        c = config.plugins.camalert
        LOG.configure(c.log_level.value, c.log_syslog.value)
        c.log_level.addNotifier(lambda _e: LOG.configure(c.log_level.value, c.log_syslog.value), initial_call=False)
        c.log_syslog.addNotifier(lambda _e: LOG.configure(c.log_level.value, c.log_syslog.value), initial_call=False)
        for name in ("source", "server"):  # another camera source: the cached camera names are stale
            getattr(c, name).addNotifier(lambda _e: self.camera_source_changed(), initial_call=False)
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
        stream = stream_from_ref(ref.toString(), direct_cameras() if direct else None)
        if stream and not direct and len(go2rtc_servers()) > 1:  # #15: the camera name of a stream on another server
            from .camalert_core.servers import name_for_stream
            from .camalert_core.urls import server_host
            from .services import url_from_ref
            return name_for_stream(server_host(url_from_ref(ref.toString())), stream, SERVER_MAP) or stream
        return stream

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

    @staticmethod
    def unifi_interval():
        """UniFi Protect check interval in seconds (2-60, default 5)."""
        try:
            return max(2, min(60, int(config.plugins.camalert.unifi_interval.value)))
        except (TypeError, ValueError):
            return 5

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
    def window_priority(self, priority):
        """The priority a window marks (#48): none for what the viewer asked for himself (#13)."""
        return "normal" if getattr(self, "source", None) == "menu" else pick_priority(priority)

    def look_at_door(self):
        """#13: the default camera at once, asked for by the viewer (source "menu"): passes do-not-disturb and the
        time rules like a high request, but without chime and without the doorbell frame."""
        return self.show(None, None, None, "high", source="menu")

    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        """Handles a show request and logs it (source, decision and reason) in camalert.log and the event list."""
        self.reason, self.label, self.source = "", (label or "").strip()[:40] or None, source
        cam = stream or config.plugins.camalert.camera.value
        if mode == "log":  # display mode 'log only' (#70): event list and log, nothing on screen, no chime
            self.reason = present.reason("log_only")
            log("request from %s: camera=%s priority=%s mode=log label=%s -> ignore (log only)"
                % (source, cam, pick_priority(priority), label or "-"))
            self.record_event(cam, label, source, pick_priority(priority), "ignore", self.reason, event_id)
            self.label = None
            return "ignore"
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
        if result == "show" and chime_wanted(config.plugins.camalert.chime.value, pick_priority(priority)) \
                and not is_test(source) and source != "menu":  # a test (#62) or the viewer's own key (#13): no sound
            if self.muted():  # the chime plays through ALSA, which the receiver's mute does not reach (#20)
                log("chime skipped: the receiver is muted")
            else:
                self.chime()
        return result

    def muted(self):
        try:
            return bool(eDVBVolumecontrol.getInstance().isMuted())
        except Exception:  # noqa: BLE001 - an image without isMuted(): assume not muted
            return False

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
                reactor.callLater(6, self.show, stream, seconds, mode, priority,
                                  TEST_SOURCE if is_test(self.source) else "wake")
                self.reason = present.reason("woken")
                return "wake"
            self.reason = present.reason("standby")
            return "ignore"
        inStandby = None
        cams = parse_cams(stream)
        if len(cams) > 1:
            cams = guest_filter(cams)  # #11
            if not cams:
                self.reason = present.reason(GUEST)
                return "ignore"
        if len(cams) > 1:
            if self.blocked(priority, ",".join(cams)):
                return "ignore"
            if len(cams) <= 4 and pick_mode(mode, c.mode.value) in ("photo", "strip") or mode == "strip":
                return self.strip(cams[:4], seconds or int(c.duration.value), priority)
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
        if is_guest_hidden(stream):  # #11
            self.reason = present.reason(GUEST)
            return "ignore"
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
                self.window = self.session.instantiateDialog(PhotoWindow, stream, snap_url, title, keys,
                                                             self.window_priority(priority))
                self.window.start(seconds)
                if keys:
                    self.close_keys()
                    self.keys = KeyHook()
        elif mode == "live":
            if action == "show":
                if self.live_stream is None:
                    cur = self.session.nav.getCurrentlyPlayingServiceOrGroup()
                    self.previous_ref = cur.toString() if cur else None
                self.live_stream = stream
                self.start_live(stream, snap_url, eServiceReference(service_ref(live_url, title)))
                if priority != "alarm":
                    self.lower_volume(int(c.live_volume.value))
            self.live_timer.start(seconds * 1000, True)
        else:
            if pause:
                self.pause_tv()
            self.close_notice()
            text = notification_text(title, priority)
            if snap_url:
                self.notice = self.session.instantiateDialog(NotifyWindow, stream, snap_url, text)
                self.notice.start(seconds)
            else:
                Notifications.AddPopup(text, MessageBox.TYPE_INFO, seconds, id="CamAlert")
            if self.paused:
                self.notify_timer.start(seconds * 1000, True)
        return action

    def strip(self, names, seconds, priority="normal"):
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
        self.window = self.session.instantiateDialog(StripWindow, cams, keys, self.label, self.window_priority(priority))
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
            streams = guest_filter(streams)  # #11
            if not streams:
                self.reason = present.reason(GUEST)
                return "ignore"
            return then(streams)
        if self._names:
            return then(overview_names(self._names)[:9])

        def fetched(names):
            self._names = names
            self._names_at = time.time()
            then(overview_names(names)[:9])
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
            UnifiSource.devices_changed()  # new credentials: fresh session, no login backoff (#78)
            secure_file(devices.DEVICES_FILE)
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

    def warm_tick(self):
        """#111: ready cameras get a warm MJPEG feed while CamAlert is on and the receiver is not in standby."""
        from Screens.Standby import inStandby
        c = config.plugins.camalert
        on = c.enabled.value and inStandby is None and c.source.value == "go2rtc"
        try:
            WARM.update(c.server.value, c.ready_cameras.value, on, resolve_camera)
        except Exception as e:  # never let the timer die
            log("keep cameras ready: %s" % e, "error")

    def poll_unifi(self):
        """UniFi Protect consoles (#70): one poll per console in a thread (never on the GUI thread); the first
        answer after a start, a setting change or an error only sets the baseline (no old events)."""
        c = config.plugins.camalert
        if self.unifi_interval() != self.unifi_seconds:  # 'Check every (seconds)' changed
            self.unifi_seconds = self.unifi_interval()
            self.unifi_timer.start(self.unifi_seconds * 1000, False)
        source = UnifiSource(trigger_settings())
        if not c.enabled.value or not source.enabled():
            if self.unifi_state:
                log("UniFi Protect: stopped")
            self.unifi_state = {}
            UNIFI_STATUS.reset()
            return
        consoles = source.devices(self.load_devices())
        UNIFI_STATUS.consoles = len(consoles)
        for name, dev in consoles.items():
            if self.unifi_state.get(name) == "busy":
                continue
            if name not in self.unifi_state:
                log("UniFi Protect: polling console %s every %d s" % (name, self.unifi_seconds))
            previous = self.unifi_state.get(name)
            self.unifi_state[name] = "busy"

            def done(state, name=name, previous=previous):
                if self.unifi_state.get(name) != "busy":  # switched off meanwhile
                    return
                self.unifi_state[name] = state
                UNIFI_STATUS.ok()
                trig = source.check(name, previous, state)
                if trig:
                    UNIFI_STATUS.event(trig)
                    self.show(*trig.show_args())

            def failed(err, name=name):
                if self.unifi_state.get(name) != "busy":
                    return
                self.unifi_state[name] = None
                if UNIFI_STATUS.failed(err.value):  # log once per state change, not at every poll (#78)
                    log("UniFi Protect %s: %s" % (name, UNIFI_STATUS.error), level="error")
            threads.deferToThread(source.poll, dev).addCallbacks(done, failed)

    def ptz_devices(self):
        """Devices with camera control: UniFi Protect consoles are not cameras (#70)."""
        return {n: d for n, d in self.load_devices().items() if d.get("type") != "unifi"}

    def has_ptz(self, name):
        return bool(name) and name in self.ptz_devices()

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
        dev = self.ptz_devices().get(name)
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
            secret = config.plugins.camalert.ha_webhook_secret.value or None  # signed keys (#82)
            body = button_event(node_id(), camera, button, secret).encode("utf-8")

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
        w.first = True  # the other camera's first picture may come from go2rtc's cache (#110)
        w.base_title = w.title_text = urls[2]
        w["title"].setText(w.title_text)
        w["hint"].setText(window_hint(target))
        w.extend(int(config.plugins.camalert.duration.value))

    def camera_source_changed(self):
        """The camera source setting changed (settings screen, OpenWebif): forget the cached camera list, so a
        camera of the new source is not refused as unknown for up to a minute; fetch the new list."""
        self._names, self._names_at = [], 0
        self.refresh_names()

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

    def close_notice(self):
        n, self.notice = self.notice, None
        if n is not None:
            n.active = False
            n.close_timer.stop()
            n.hide()
            self.session.deleteDialog(n)

    def notice_closed(self, n):
        if n is self.notice:
            self.notice = None
            self.session.deleteDialog(n)

    def close_fullscreens(self, tries=10):
        """Closes open mosaic / tour screens (#63). Enigma2 only closes the top dialog, so one per call; the next
        one (stacked screens) after the first has gone."""
        if not self.fullscreens:
            return
        top = getattr(self.session, "current_dialog", self.fullscreens[-1])
        if top in self.fullscreens:
            self.fullscreens.remove(top)
            try:
                top.close()
            except Exception as e:  # noqa: BLE001 - never let hide fail
                log("closing %s failed:" % type(top).__name__, e)
        if self.fullscreens and tries > 0:
            reactor.callLater(0.3, self.close_fullscreens, tries - 1)

    def screen(self):
        """What CamAlert shows now, for status "screen" (#63)."""
        full = self.fullscreens[-1] if self.fullscreens else None
        return screen_name(
            "tour" if isinstance(full, TourScreen) else "mosaic" if full is not None else None,
            "strip" if isinstance(self.window, StripWindow) else "photo" if self.window is not None else None,
            self.notice is not None, self.live_stream is not None)

    def hide(self, resume=True):
        self.close_fullscreens()
        self.close_keys()
        self.close_notice()
        if self.ptz_stream:
            self.leave_ptz()
        if self.window is not None:
            w, self.window = self.window, None
            w.active = False
            w.close_timer.stop()
            if getattr(w, "frame", None) is not None:
                w.frame.stop()  # a flashing priority frame (#48)
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

    def start_live(self, stream, snap_url, ref):
        """#91: fetch a picture (warm feed, Protect, go2rtc cache, frame.jpeg) in a thread, show it, then start the
        stream (at the latest after STILL_WAIT_SECONDS). Without a picture address the stream starts at once."""
        self.hide_still()
        self.play_timer.stop()
        self.show_live_masks(stream)
        if not snap_url:
            self.pending_play = None
            self.session.nav.playService(ref)
            return
        token = self.still.start(stream)
        self.pending_play = (token, ref)
        self.play_timer.start(int(STILL_WAIT_SECONDS * 1000), True)
        threads.deferToThread(_download, snap_url, STILL, orientation_for(stream), True, stream).addCallbacks(
            lambda _r: self.still_ready(token), lambda err: self.still_failed(token, err))

    def play_pending(self):
        self.play_timer.stop()
        pending, self.pending_play = self.pending_play, None
        if pending is not None and pending[0] == self.still.token and self.live_stream is not None:
            self.session.nav.playService(pending[1])

    def play_soon(self, token, ms):
        """Start the waiting stream of token after ms (a moment to draw the still, or at once)."""
        if self.pending_play is not None and self.pending_play[0] == token:
            self.play_timer.stop()
            if ms:
                self.play_timer.start(ms, True)
            else:
                self.play_pending()

    def still_failed(self, token, err):
        log("still picture failed:", err.getErrorMessage(), level="verbose")
        self.play_soon(token, 0)

    def still_ready(self, token):
        if self.live_stream is None or not self.still.picture(token):
            return  # the stream was faster, or the live view ended / changed camera meanwhile
        if self.still_screen is None:
            self.still_screen = self.session.instantiateDialog(LiveStillScreen)
        if not self.still_screen.load(STILL, self.live_stream):
            self.still.playing(token)
            self.hide_still()
            self.play_soon(token, 0)
            return
        self.still_screen.show()
        self.still_timer.start(int(STILL_MAX_SECONDS * 1000), True)
        log("live view", self.live_stream, "still picture shown", level="verbose")
        self.play_soon(token, STILL_DRAW_MS)

    def service_event(self, ev):
        if self.pending_play is not None:
            return  # still the TV channel: the camera stream has not started yet
        if ev in self.first_frame and self.still.playing():
            self.hide_still()

    def hide_still(self):
        self.still_timer.stop()
        s, self.still_screen = self.still_screen, None
        if s is not None:
            s.hide()
            self.session.deleteDialog(s)

    def show_live_masks(self, stream):
        """Black boxes over the live video of a camera with privacy masks (#11); removed without masks."""
        if not current_masks().get(stream):
            self.hide_live_masks()
            return
        if self.mask_screen is None:
            self.mask_screen = self.session.instantiateDialog(LiveMaskScreen)
        self.mask_screen.place(stream)
        self.mask_screen.show()

    def hide_live_masks(self):
        s, self.mask_screen = self.mask_screen, None
        if s is not None:
            s.hide()
            self.session.deleteDialog(s)

    def end_live(self):
        reactor.callLater(0.1, _notify)
        self.hide_live_masks()
        self.live_timer.stop()
        self.play_timer.stop()
        self.pending_play = None
        self.still.stop()
        self.hide_still()
        self.restore_volume()
        stream, self.live_stream = self.live_stream, None
        if stream and config.plugins.camalert.live_return.value and self.previous_ref \
                and self.current_stream() == stream:
            self.session.nav.playService(eServiceReference(self.previous_ref))
        self.previous_ref = None

    def status(self):
        return {"window": self.window.stream if self.window else None, "live": self.live_stream, "paused": self.paused,
                "screen": self.screen(),
                "dnd": bool(config.plugins.camalert.dnd.value)}
