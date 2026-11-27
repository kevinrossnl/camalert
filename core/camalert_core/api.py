# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The CamAlert HTTP API, the same on every player (#5): route table, validation, access rules and answers.

The players only adapt their HTTP server to Request/Response and implement a Backend (settings, controller,
camera list, log, metrics); everything else happens here, so Enigma2 and Kodi answer exactly the same.

    POST /camalert/<action>   actions: show, mosaic, tour, hide, dnd (with on=...), ptz, webhook
    GET  /camalert/<action>   reads: status, cameras, dnd (state), settings, events, log, metrics
    POST /camalert/settings   position=... and/or size=...: the photo window of this player (#84)
    POST /camalert/setup      server=<go2rtc address> [camera=...]: Home Assistant sets the player up (#122)
                              (GET of an action still works, but is deprecated and logged once per caller)
    Parameters: query string, form body or JSON object body.
    test=1 on any request (#62): the caller source becomes "test": no chime, the event is tagged "test".
    status answers "screen" (#63): none / photo / strip / notification / live / mosaic / tour.
    Token: header X-CamAlert-Token (a token= query parameter still works: deprecated, logged once, redacted)

Access: address allowlist (setting allow: lan / any) + token (if set), compared with hmac.compare_digest.
log, events and metrics never answer callers outside the local network unless a token is set (and given).
No server-side requests to caller-chosen addresses: cameras are names from the camera list (urls are built from
the configured go2rtc server or camera file), the webhook must point into the local network.
"""
import json
import re
import time
from urllib.parse import parse_qs

from .access import RateLimiter, client_allowed, exposed_without_token, token_ok, url_target
from .cameras import parse_cams
from .devices.config import PTZ_ACTIONS
from .events import TEST_SOURCE, caller_source
from .obs.log import redact
from .rules import MODES, PRIORITIES, clamp_seconds, has_seconds, show_seconds
from .schema import BY_ID as _SCHEMA
from .urls import go2rtc_state, normalize_server

API_VERSION = 1
MIN_HA_VERSION = "1.0.0"  # oldest Home Assistant integration that understands this API version
CAPABILITIES = ("cameras", "dnd", "events", "header_token", "hide", "hold", "log", "metrics", "mosaic", "post", "ptz",
                "screen", "settings", "setup", "show", "status", "strip", "test", "tour", "webhook")
# Settings a caller may change through /camalert/settings (#84), with their choices from the settings schema.
DISPLAY_SETTINGS = {k: tuple(_SCHEMA[k].choices) for k in ("position", "size")}
# What /camalert/status reports as "screen" (#63): the top-most CamAlert screen, "none" when nothing is shown.
SCREENS = ("none", "photo", "strip", "notification", "live", "mosaic", "tour")
NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
TRUE, FALSE = ("1", "true", "on", "yes"), ("0", "false", "off", "no")


class Request(object):
    def __init__(self, method, path, args=None, ip="", header_token=None, user_agent="", body=b"",
                 content_type=""):
        self.method, self.path, self.args, self.ip = (method or "GET").upper(), path or "", dict(args or {}), ip or ""
        self.header_token, self.user_agent = header_token, user_agent or ""
        self.body, self.content_type = body or b"", content_type or ""


class Response(object):
    def __init__(self, code, body, content_type="application/json", headers=None):
        self.code, self.body, self.content_type, self.headers = code, body, content_type, dict(headers or {})

    def payload(self):
        """The body as bytes."""
        return (self.body if isinstance(self.body, str) else json.dumps(self.body)).encode("utf-8")


class Invalid(Exception):
    """A parameter is missing or wrong (400)."""


class Backend(object):
    """What a player provides. controller(): show/hide/mosaic/tour/ptz_move/has_ptz/set_dnd/status/events and the
    attribute last_caller (same interface on every player)."""
    platform = ""
    version = ""

    def settings(self):
        """{enabled, allow, token, duration, camera, dnd, ha_webhook, position, size}"""
        raise NotImplementedError

    def controller(self):
        raise NotImplementedError

    def node(self):
        """(id, name) of this player."""
        raise NotImplementedError

    def cameras(self):
        """[{name, title, snapshot}] of every camera (may block: a network call in go2rtc mode)."""
        raise NotImplementedError

    def set_webhook(self, url):
        raise NotImplementedError

    def set_display(self, key, value):
        """Saves position or size (#84); value is one of DISPLAY_SETTINGS[key]."""
        raise NotImplementedError

    def set_setup(self, server, camera):
        """Saves the go2rtc address (and the default camera, None = keep) sent by Home Assistant, and shows
        SETUP_RECEIVED on the screen (#122). May be called from a thread."""
        raise NotImplementedError

    def log_tail(self, lines):
        raise NotImplementedError

    def metrics(self):
        raise NotImplementedError

    def status_extra(self):
        return {}

    def log(self, message, level="normal"):
        pass


class Route(object):
    """writes: parameters that turn a read into a change (dnd: on; settings: position, size)."""

    def __init__(self, name, handler, action=False, sensitive=False, blocking=False, writes=()):
        self.name, self.handler, self.action, self.sensitive, self.blocking = name, handler, action, sensitive, blocking
        self.writes = tuple(writes)

    def changes(self, args):
        """True when this request changes something on the player (POST; GET still works but is deprecated)."""
        return self.action or any(k in args for k in self.writes)


# --- parameters ---------------------------------------------------------------------------------------------------
def cameras_param(value, many=True):
    """None (= default) or 'a,b' with only valid camera names; Invalid otherwise."""
    if value is None or not str(value).strip():
        return None
    names = [x for x in re.split(r"[,\s]+", str(value).strip()) if x]
    if not names or any(not NAME.match(x) for x in names) or (not many and len(names) > 1):
        raise Invalid("invalid camera name")
    return ",".join(names)


def choice_param(args, key, allowed):
    value = args.get(key)
    if value in (None, ""):
        return None
    if value not in allowed:
        raise Invalid("invalid %s" % key)
    return value


def bool_param(value, name="on"):
    text = str(value).strip().lower()
    if text in TRUE:
        return True
    if text in FALSE:
        return False
    raise Invalid("%s must be 1 or 0" % name)


def screen_name(fullscreen=None, window=None, notification=False, live=False):
    """The "screen" value of /camalert/status (#63), top-most first: fullscreen 'mosaic'/'tour', window
    'photo'/'strip', a notification, live view; 'none' when nothing of CamAlert is on screen."""
    for value in (fullscreen, window, "notification" if notification else None, "live" if live else None):
        if value in SCREENS:
            return value
    return "none"


def local_url(url, caller_ip, resolver=None):
    """The webhook may only point into the local network (access.url_target, #53); Invalid otherwise.
    A host name with dots is resolved (blocking: the webhook route runs in a thread on Enigma2)."""
    why = url_target(url, caller_ip, resolver)
    if why:
        raise Invalid(why)
    return url


def parse_body(content_type, body):
    """Parameters from a POST body: JSON object or form (application/x-www-form-urlencoded); else {}."""
    if not body:
        return {}
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    if "json" in (content_type or "") or text.lstrip().startswith("{"):
        try:
            d = json.loads(text)
        except ValueError:
            raise Invalid("invalid JSON body")
        if not isinstance(d, dict):
            raise Invalid("invalid JSON body")
        return {k: ("" if v is None else str(v).lower() if isinstance(v, bool) else str(v)) for k, v in d.items()}
    return {k: v[0] for k, v in parse_qs(text, keep_blank_values=True).items()}


# --- handlers -------------------------------------------------------------------------------------------------------
def _show(b, ctl, a, s, source):
    cam = cameras_param(a.get("cam"))
    mode = choice_param(a, "mode", MODES + ("strip",))
    priority = choice_param(a, "priority", PRIORITIES)
    sec = show_seconds(a.get("sec"), s["duration"]) if has_seconds(a.get("sec")) else None  # 0: until hide (#81)
    label = a.get("label")
    res = ctl.show(cam, sec, mode, priority, source, label)
    return {"result": res in ("show", "extend", "wake"), "action": res, "cam": cam or s["camera"]}


def _hide(b, ctl, a, s, source):
    ctl.hide()
    return {"result": True, "action": "hide"}


def _mosaic(b, ctl, a, s, source):
    cam = cameras_param(a.get("cam"))
    sec = clamp_seconds(a.get("sec"), 60) if a.get("sec") else 60
    res = ctl.mosaic(cam, sec)
    b.log("mosaic from %s: cameras=%s -> %s" % (source, cam or "-", res))
    return {"result": res == "show", "action": res}


def _tour(b, ctl, a, s, source):
    cam = cameras_param(a.get("cam"))
    iv = a.get("interval")
    res = ctl.tour(cam, max(3, min(60, int(iv))) if iv and iv.isdigit() else None)
    b.log("tour from %s: cameras=%s -> %s" % (source, cam or "-", res))
    return {"result": res == "show", "action": res}


def _dnd(b, ctl, a, s, source):
    dnd = bool(s["dnd"])
    if "on" in a:
        dnd = bool_param(a["on"])
        ctl.set_dnd(dnd)
    return {"result": True, "action": "dnd", "dnd": dnd}


def _ptz(b, ctl, a, s, source):
    cam, move = a.get("cam"), a.get("move")
    if move not in PTZ_ACTIONS or not cam or not NAME.match(cam) or not ctl.has_ptz(cam):
        raise Invalid("camera without PTZ or unknown move")
    return {"result": ctl.ptz_move(move, cam), "cam": cam, "move": move}


def _webhook(b, ctl, a, s, source):
    url = (a.get("url") or "").strip()
    if url:
        local_url(url, a.get("_ip"))
    if url != s.get("ha_webhook", ""):
        b.set_webhook(url)
        b.log("Home Assistant webhook %s" % ("set" if url else "removed"))
    return {"result": True, "webhook": bool(url)}


def _settings(b, ctl, a, s, source):
    new = {k: choice_param(a, k, allowed) for k, allowed in DISPLAY_SETTINGS.items()}
    out = {"result": True}
    for k in DISPLAY_SETTINGS:
        value = new[k] or s.get(k)
        if new[k] is not None and new[k] != s.get(k):
            b.set_display(k, new[k])
            b.log("window %s set to %s" % (k, new[k]))
        out[k] = value
    return out


def configured(s):
    """False while the player has never been set up (#122): no go2rtc address, not in direct mode, first-start
    wizard not finished. settings() without source / wizard_done: go2rtc, not finished."""
    return not (go2rtc_state(s.get("server")) == "not_set" and s.get("source", "go2rtc") != "direct"
                and not s.get("wizard_done"))


def _setup(b, ctl, a, s, source):
    """Home Assistant sends its go2rtc address (#122). Allowed when the player was never set up, or when the
    address is in the local network (the webhook rule, #53); otherwise 409. An invalid address is always 400."""
    server = normalize_server(a.get("server"))
    if not server:
        raise Invalid("invalid server")
    camera = cameras_param(a.get("camera"), many=False)
    if configured(s) and url_target(server, a.get("_ip")):
        return Response(409, {"result": False, "error": "already set up"})
    b.set_setup(server, camera)
    b.log("set up by %s: go2rtc %s%s" % (a.get("_ip"), server, ", camera %s" % camera if camera else ""))
    return {"result": True, "configured": True, "server": server, "camera": camera or s.get("camera") or ""}


def _cameras(b, ctl, a, s, source):
    try:
        cams = b.cameras()
    except Exception as e:  # noqa: BLE001 - go2rtc / camera file not reachable
        b.log("camera list failed: %s" % e, "error")
        return {"result": False, "error": "camera source not reachable"}
    return {"result": True, "cameras": cams}


def _status(b, ctl, a, s, source):
    node, name = b.node()
    out = dict(ctl.status(), result=True, version=b.version, id=node, name=name, platform=b.platform,
               api_version=API_VERSION, capabilities=list(CAPABILITIES), min_ha_version=MIN_HA_VERSION)
    out.update({k: s.get(k) for k in DISPLAY_SETTINGS})  # #84
    out["configured"] = configured(s)  # #122
    out.update(b.status_extra())
    if out.get("screen") not in SCREENS:  # a player that does not know it yet (#63)
        out["screen"] = screen_name(window="photo" if out.get("window") else None, live=bool(out.get("live")))
    return out


def _log(b, ctl, a, s, source):
    n = int(a["lines"]) if (a.get("lines") or "").isdigit() else 200
    return {"result": True, "lines": [redact(x) for x in b.log_tail(min(n, 2000))]}


def _events(b, ctl, a, s, source):
    return {"result": True, "events": [{k: v for k, v in e.items() if k != "snapshot"} for e in ctl.events]}


def _metrics(b, ctl, a, s, source):
    return Response(200, b.metrics(), "text/plain; version=0.0.4")


ROUTES = {r.name: r for r in (
    Route("show", _show, action=True), Route("camalert", _show, action=True), Route("hide", _hide, action=True),
    Route("mosaic", _mosaic, action=True), Route("tour", _tour, action=True), Route("ptz", _ptz, action=True),
    Route("webhook", _webhook, action=True, blocking=True), Route("setup", _setup, action=True, blocking=True), Route("dnd", _dnd, writes=("on",)),
    Route("status", _status), Route("settings", _settings, writes=tuple(DISPLAY_SETTINGS)),
    Route("cameras", _cameras, blocking=True), Route("log", _log, sensitive=True),
    Route("events", _events, sensitive=True), Route("metrics", _metrics, sensitive=True),
)}


def route_of(path):
    """The Route for a path, or None."""
    p = (path or "").rstrip("/")
    if not (p == "/camalert" or p.startswith("/camalert/")):
        return None
    return ROUTES.get(p.rsplit("/", 1)[-1])


# --- the request pipeline ------------------------------------------------------------------------------------------
LIMIT = RateLimiter(30, 10.0)
WARNED = set()   # callers already warned about (exposure, deprecations): log once per caller
METHODS = ("GET", "POST")


def _once(b, key, message, level="normal"):
    if key not in WARNED:
        WARNED.add(key)
        b.log(message, level)


def error(code, text):
    return Response(code, {"result": False, "error": text})


def handle(b, req, now=None):
    """Response for one request. Never raises."""
    now = time.time() if now is None else now
    ip = req.ip
    if not LIMIT.allow(ip, now):
        return error(429, "too many requests")
    try:
        s = b.settings()
    except Exception as e:  # noqa: BLE001
        b.log("request failed: %s" % e, "error")
        return error(500, "internal error")
    if exposed_without_token(s["allow"], s["token"], ip):
        _once(b, ("exposed", ip), "WARNING: API called from %s outside the local network without a token; set an "
                                  "access token" % ip, "error")
    query_token = req.args.pop("token", None)
    given = req.header_token or query_token or ""
    if not client_allowed(ip, s["allow"]) or not token_ok(s["token"], given):
        return error(403, "forbidden")
    if query_token and not req.header_token:
        _once(b, ("query token", ip), "deprecated: %s sends the token in the URL; use the X-CamAlert-Token header" % ip)
    if not s["enabled"]:
        return Response(200, {"result": False, "error": "disabled"})
    route = route_of(req.path)
    if route is None:
        return error(404, "unknown action")
    if req.method not in METHODS:
        return Response(405, {"result": False, "error": "method not allowed"}, headers={"Allow": "GET, POST"})
    if route.sensitive and not client_allowed(ip, "lan") and not s["token"]:
        return error(403, "forbidden")  # never readable from the internet without a token
    headers = {}
    try:
        args = dict(req.args)
        if req.method == "POST":
            args.update(parse_body(req.content_type, req.body))
            args.pop("token", None)
        is_action = route.changes(args)
        if is_action and req.method == "GET":
            headers["Deprecation"] = "true"
            _once(b, ("get", route.name, ip), "deprecated: %s uses GET for /camalert/%s; use POST" % (ip, route.name))
        source = caller_source(req.user_agent)
        if "test" in args and bool_param(args.pop("test"), "test"):
            source = TEST_SOURCE  # test run (#62): no chime, event tagged "test"
        ctl = b.controller()
        ctl.last_caller = (now, ip, source)
        b.log("API %s %s %s from %s (%s)" % (req.method, req.path, redact("&".join("%s=%s" % kv for kv in sorted(args.items()))), ip, source),
              "verbose")
        args["_ip"] = ip
        out = route.handler(b, ctl, args, s, source)
    except Invalid as e:
        return Response(400, {"result": False, "error": str(e)}, headers=headers)
    except Exception as e:  # noqa: BLE001 - never let a request break the player
        b.log("request failed: %s" % e, "error")
        return error(500, "internal error")
    if isinstance(out, Response):
        out.headers.update(headers)
        return out
    return Response(200, out, headers=headers)
