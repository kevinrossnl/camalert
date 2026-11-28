"""Light players (#95): a TV that runs an existing notification app instead of CamAlert.

Supported apps (their APIs as the projects document them):

- ``pipup``: PiPup (rogro82/PiPup and its forks): ``POST http://<tv>:7979/notify`` with ``duration``, ``position``
  (0-4), ``title``, ``message`` and ``media.image.uri`` / ``media.video.uri``. Newer forks also have
  ``POST /cancel``.
- ``tvoverlay``: TvOverlay (gugutab/TvOverlay): ``POST http://<tv>:5001/notify`` with ``id``, ``title``,
  ``message``, ``image`` (URL), ``video`` (stream URL), ``corner`` and ``seconds``; ``GET /get`` answers while the
  app runs.
- ``nfandroidtv``: Home Assistant's own "Notifications for Android TV / Fire TV" integration, through its notify
  entity (``nfandroidtv.send_message``); a picture only through a camera entity of Home Assistant
  (``media-source://camera/camera.<name>``).

:class:`AppApi` answers the CamAlert API inside Home Assistant (like ``BrowserApi`` for #92/#127), so the
coordinator, the entities, the actions, the doorbell option (#90) and the blueprints work unchanged. The TV fetches
pictures and streams straight from go2rtc. The rules (Do not disturb, active hours) mirror ``camalert_core.rules``;
``tests/test_ha_apps.py`` checks the copy against the core. No Home Assistant imports at module level: the pure
helpers are tested without Home Assistant.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import parse_qs, quote, unquote, urlsplit

APP = "app"  # config entry data "type" of a light player
CONF_TYPE = "type"
CONF_APP = "app"
CONF_SERVER = "go2rtc"  # go2rtc base URL the TV fetches pictures and streams from
CONF_NOTIFY_ENTITY = "notify_entity"  # nfandroidtv: its notify entity
CONF_DEFAULT_CAMERA = "camera"
CONF_ACTIVE_FROM = "active_from"  # options: active hours (normal priority only), "HH:MM:SS"; equal = all day
CONF_ACTIVE_UNTIL = "active_until"
OPT_DND = "dnd"
OPT_DND_LEVEL = "dnd_level"
OPT_POSITION = "position"
OPT_SIZE = "size"

APPS = ("pipup", "tvoverlay", "nfandroidtv")
DEFAULT_PORTS = {"pipup": 7979, "tvoverlay": 5001}
HOST_APPS = ("pipup", "tvoverlay")  # reached over the network; nfandroidtv through its entity
VIDEO_APPS = ("pipup", "tvoverlay")  # can play the live stream in the window
RTSP_PORT = 8554  # go2rtc's RTSP server
# What a light player can do (capabilities of the CamAlert API, #5). No mosaic, tour, PTZ, colour keys/webhook,
# update (#126), setup (#122), log, events, metrics, spoken announcements (#89) or hold (#81).
CAPABILITIES = ("cameras", "dnd", "hide", "post", "screen", "settings", "show", "status", "test")
POSITIONS = ("top_right", "top_left", "bottom_right", "bottom_left")
SIZES = {"small": 320, "medium": 480, "large": 640}  # picture width on the TV
PIPUP_POSITION = {"top_right": 0, "top_left": 1, "bottom_right": 2, "bottom_left": 3}
TVOVERLAY_CORNER = {"top_right": "top_end", "top_left": "top_start", "bottom_right": "bottom_end",
                    "bottom_left": "bottom_start"}
NFA_POSITION = {"top_right": "top-right", "top_left": "top-left", "bottom_right": "bottom-right",
                "bottom_left": "bottom-left"}
PRIORITIES = ("normal", "high", "alarm")
MODES = ("photo", "live", "notify", "strip")
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
TIMEOUT = 5
DEFAULT_SECONDS, MIN_SECONDS, MAX_SECONDS, HOLD_SECONDS = 30, 5, 300, 600


def is_app(data) -> bool:
    return (data or {}).get(CONF_TYPE) == APP


def node_id(data) -> str:
    """Unique id of a light player: the app and where it is (address or notify entity)."""
    app = data.get(CONF_APP, "")
    where = data.get(CONF_NOTIFY_ENTITY) if app == "nfandroidtv" else data.get("host", "")
    return "app-%s-%s" % (app, re.sub(r"[^a-z0-9]+", "-", str(where or "").lower()).strip("-"))


# --- rules: a copy of camalert_core.rules (tests/test_ha_apps.py compares them) -------------------------------------
def clamp_seconds(value, default=DEFAULT_SECONDS):
    try:
        s = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(MIN_SECONDS, min(MAX_SECONDS, s))


def show_seconds(value, default=DEFAULT_SECONDS):
    try:
        if int(value) == 0:
            return HOLD_SECONDS
    except (TypeError, ValueError, OverflowError):
        pass
    return clamp_seconds(value, default)


def in_time_window(now, start, end):
    n, a, b = now[0] * 60 + now[1], start[0] * 60 + start[1], end[0] * 60 + end[1]
    if a == b:
        return True
    return a <= n < b if a < b else n >= a or n < b


def dnd_blocks(priority, dnd_on, level="normal"):
    if not dnd_on or priority == "alarm":
        return False
    return priority == "normal" or (level == "high" and priority == "high")


def clock(value):
    """(hour, minute) from "HH:MM[:SS]", or None."""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(value or ""))
    return (int(m.group(1)) % 24, int(m.group(2)) % 60) if m else None


def blocked(priority, options, now):
    """None when the request may show, else the reason ("dnd" / "active_hours"). now = (hour, minute)."""
    if dnd_blocks(priority, bool(options.get(OPT_DND)), options.get(OPT_DND_LEVEL) or "normal"):
        return "dnd"
    start, end = clock(options.get(CONF_ACTIVE_FROM)), clock(options.get(CONF_ACTIVE_UNTIL))
    if priority == "normal" and start and end and not in_time_window(now, start, end):
        return "active_hours"
    return None


# --- go2rtc: the camera list as the players make it (#117) ----------------------------------------------------------
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _source_stream(url):
    if not isinstance(url, str):
        return None
    if url.startswith("ffmpeg:"):
        return url[len("ffmpeg:"):].split("#", 1)[0]
    try:
        p = urlsplit(url)
    except ValueError:
        return None
    if p.scheme not in ("rtsp", "rtsps") or p.hostname not in LOOPBACK:
        return None
    source = (parse_qs(p.query).get("source") or [""])[0]
    if source.startswith("ffmpeg:"):
        return source[len("ffmpeg:"):].split("#", 1)[0]
    return unquote(p.path.lstrip("/")) or None


def derived_streams(data):
    if not isinstance(data, dict):
        return set()
    out = set()
    for name, info in data.items():
        producers = info.get("producers") if isinstance(info, dict) else None
        if not isinstance(producers, list) or not producers:
            continue
        bases = [_source_stream(p.get("url") if isinstance(p, dict) else None) for p in producers]
        if all(b is not None and b != name and b in data for b in bases):
            out.add(name)
    return out


def stream_names(text):
    """Camera names from go2rtc's /api/streams answer, sorted, helper streams left out (camalert_core.urls)."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    skip = derived_streams(data)
    return sorted(k for k in data.keys() if NAME.match(k) and k not in skip)


def title(name):
    """A readable camera title: front_door -> Front door."""
    t = re.sub(r"[_.-]+", " ", str(name or "")).strip()
    return t[:1].upper() + t[1:]


def normalize_server(text):
    """go2rtc base URL ("http://host:port") or "" for an invalid one; no scheme means http."""
    s = (text or "").strip().rstrip("/")
    if s and "://" not in s:
        s = "http://" + s
    try:
        p = urlsplit(s)
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.path not in ("", "/"):
        return ""
    return "%s://%s" % (p.scheme, p.netloc)


def frame_url(server, camera, width):
    return "%s/api/frame.jpeg?src=%s&width=%d" % (server, quote(camera, safe=""), int(width))


def rtsp_url(server, camera):
    host = urlsplit(server).hostname or ""
    host = "[%s]" % host if ":" in host else host
    return "rtsp://%s:%d/%s" % (host, RTSP_PORT, quote(camera, safe=""))


# --- what each app gets ---------------------------------------------------------------------------------------------
def pipup_payload(head, text, picture, video, seconds, position, width):
    media = {"video": {"uri": video, "width": width}} if video else {"image": {"uri": picture, "width": width}}
    return {"duration": int(seconds), "position": PIPUP_POSITION.get(position, 0), "title": head, "message": text,
            "media": media}


def tvoverlay_payload(notification_id, head, text, picture, video, seconds, position):
    out = {"id": notification_id, "title": head, "message": text, "seconds": int(seconds),
           "corner": TVOVERLAY_CORNER.get(position, "top_end")}
    if video:
        out["video"] = video
    else:
        out["image"] = picture
    return out


def nfandroidtv_data(entity_id, head, text, seconds, position, camera_entity=None):
    data = {"entity_id": entity_id, "title": head, "message": text or head, "duration": {"seconds": int(seconds)},
            "position": NFA_POSITION.get(position, "top-right")}
    if camera_entity:
        data["image"] = {"media_content_id": "media-source://camera/%s" % camera_entity,
                         "media_content_type": "image/jpeg"}
    return data


# --- the API ----------------------------------------------------------------------------------------------------------
def make_app_api(hass, data):
    from .api import CamAlertApi, CamAlertError, CamAlertNotSupported, INTEGRATION_VERSION

    class AppApi(CamAlertApi):
        """CamAlertApi of a light player: answered in Home Assistant, pictures sent to the app."""

        is_app = True

        def __init__(self):
            super().__init__(None, data.get("host") or data.get(CONF_NOTIFY_ENTITY) or "app",
                             int(data.get("port") or DEFAULT_PORTS.get(data.get(CONF_APP), 0)))
            self.hass, self.data = hass, dict(data)
            self.app = data.get(CONF_APP)
            self.server = normalize_server(data.get(CONF_SERVER))
            self.entry = None  # set by bind(); options (Do not disturb, position, size, active hours) live there
            self.shown = None  # (camera, screen, until monotonic)
            self.names: list[str] = []

        def bind(self, entry):
            self.entry = entry

        @property
        def configuration_url(self):
            return None

        @property
        def options(self) -> dict:
            return dict(getattr(self.entry, "options", None) or {})

        async def _store(self, **values):
            if self.entry is None:
                raise CamAlertNotSupported("not set up yet")
            self.hass.config_entries.async_update_entry(self.entry, options=dict(self.options, **values))

        def _client(self):
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            return async_get_clientsession(self.hass)

        def _base(self):
            host = self.host if ":" not in self.host else "[%s]" % self.host
            return "http://%s:%d" % (host, self.port)

        async def _http(self, method, url, body=None):
            import aiohttp
            try:
                async with self._client().request(method, url, json=body,
                                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        raise CamAlertError("%s answered HTTP %d" % (url.split("?")[0], resp.status))
                    return resp.status, text
            except (aiohttp.ClientError, TimeoutError, asyncio.TimeoutError) as err:
                raise CamAlertError(str(err) or type(err).__name__) from err

        async def reachable(self) -> bool:
            if self.app == "nfandroidtv":
                state = self.hass.states.get(self.data.get(CONF_NOTIFY_ENTITY) or "")
                return state is not None and state.state != "unavailable"
            if self.app == "tvoverlay":
                try:
                    await self._http("GET", self._base() + "/get")
                    return True
                except CamAlertError:
                    return False
            try:  # PiPup has no state route (only newer forks): an open port is enough
                _reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), TIMEOUT)
            except (OSError, asyncio.TimeoutError):
                return False
            writer.close()
            return True

        def screen(self):
            if self.shown and time.monotonic() < self.shown[2]:
                return self.shown
            self.shown = None
            return None

        async def _cameras(self):
            if not self.server:
                return []
            _code, text = await self._http("GET", self.server + "/api/streams")
            self.names = stream_names(text)
            return self.names

        async def _get(self, action, params=None):
            p = dict(params or {})
            if action == "status":
                if not await self.reachable():
                    raise CamAlertError("%s not reachable" % self.app)
                o, s = self.options, self.screen()
                return {"result": True, "version": INTEGRATION_VERSION, "id": node_id(self.data),
                        "name": self.data.get("name") or "", "platform": self.app, "api_version": 1,
                        "capabilities": list(CAPABILITIES), "min_ha_version": INTEGRATION_VERSION,
                        "dnd": bool(o.get(OPT_DND)), "paused": False, "configured": bool(self.server),
                        "window": s[0] if s and s[1] != "live" else None, "live": s[0] if s and s[1] == "live" else None,
                        "screen": s[1] if s else "none", "position": o.get(OPT_POSITION) or "top_right",
                        "size": o.get(OPT_SIZE) or "medium"}
            if action == "cameras":
                return {"result": True, "cameras": [{"name": n, "title": title(n), "snapshot": True}
                                                    for n in await self._cameras()]}
            if action in ("show", "camalert"):
                return await self._show(p)
            if action == "hide":
                await self._hide()
                return {"result": True, "action": "hide"}
            if action == "dnd":
                if "on" in p:
                    await self._store(**{OPT_DND: str(p["on"]) in ("1", "true", "on", "True")})
                return {"result": True, "action": "dnd", "dnd": bool(self.options.get(OPT_DND))}
            if action == "settings":
                values = {k: v for k, v in p.items() if v not in (None, "")}
                if values.get(OPT_POSITION, "top_right") not in POSITIONS or values.get(OPT_SIZE, "medium") not in SIZES:
                    raise CamAlertError("invalid position or size")
                if values:
                    await self._store(**values)
                o = self.options
                return {"result": True, "position": o.get(OPT_POSITION) or "top_right", "size": o.get(OPT_SIZE) or "medium"}
            raise CamAlertNotSupported("not supported by this player (%s)" % action)

        async def _show(self, p):
            from homeassistant.util import dt as dt_util
            priority = p.get("priority") if p.get("priority") in PRIORITIES else "normal"
            now = dt_util.now()
            why = blocked(priority, self.options, (now.hour, now.minute))
            if why:
                return {"result": True, "action": "ignore", "reason": why}
            cams = [c for c in str(p.get("cam") or "").split(",") if c]
            names = self.names or await self._cameras()
            cam = cams[0] if cams else (self.data.get(CONF_DEFAULT_CAMERA) or (names[0] if names else ""))
            if not cam or (names and cam not in names) or not NAME.match(cam):
                return {"result": True, "action": "error"}
            mode = p.get("mode") if p.get("mode") in MODES else "photo"
            seconds = show_seconds(p.get("sec")) if p.get("sec") not in (None, "") else DEFAULT_SECONDS
            o = self.options
            position, width = o.get(OPT_POSITION) or "top_right", SIZES.get(o.get(OPT_SIZE) or "medium", 480)
            head, text = title(cam), str(p.get("label") or "")
            live = mode == "live" and self.app in VIDEO_APPS
            picture = frame_url(self.server, cam, width) if self.server else None
            video = rtsp_url(self.server, cam) if live and self.server else None
            if self.app == "pipup":
                await self._http("POST", self._base() + "/notify",
                                 pipup_payload(head, text, picture, video, seconds, position, width))
            elif self.app == "tvoverlay":
                await self._http("POST", self._base() + "/notify",
                                 tvoverlay_payload("camalert", head, text, picture, video, seconds, position))
            else:
                await self._nfandroidtv(head, text, seconds, position, cam)
            screen = "live" if live else ("notification" if mode == "notify" else "photo")
            self.shown = (cam, screen, time.monotonic() + seconds)
            return {"result": True, "action": "show", "cam": cam}

        async def _nfandroidtv(self, head, text, seconds, position, cam):
            entity = self.data.get(CONF_NOTIFY_ENTITY) or ""
            camera_entity = "camera.%s" % cam.replace(".", "_").replace("-", "_").lower()
            if self.hass.states.get(camera_entity) is None:
                camera_entity = None  # no camera entity of that name: text only
            try:
                if self.hass.services.has_service("nfandroidtv", "send_message"):
                    await self.hass.services.async_call(
                        "nfandroidtv", "send_message",
                        nfandroidtv_data(entity, head, text, seconds, position, camera_entity), blocking=True)
                else:  # Home Assistant before the nfandroidtv action: the generic notify entity, text only
                    await self.hass.services.async_call(
                        "notify", "send_message", {"entity_id": entity, "title": head, "message": text or head},
                        blocking=True)
            except Exception as err:  # noqa: BLE001 - a service error is a failed request of this player
                raise CamAlertError(str(err) or type(err).__name__) from err

        async def _hide(self):
            self.shown = None
            if self.app == "tvoverlay":  # the same id replaces the notification; 1 s and it is gone
                await self._http("POST", self._base() + "/notify",
                                 {"id": "camalert", "title": "", "message": "", "seconds": 1})
            elif self.app == "pipup":  # newer forks have /cancel; the original has no way to close a popup
                try:
                    await self._http("POST", self._base() + "/cancel")
                except CamAlertError:
                    pass

    return AppApi()
