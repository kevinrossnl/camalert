# CamAlert - camera devices: Foscam alarm state and PTZ via ONVIF or Foscam CGI.
# Copyright (C) 2026 CamAlert developers. GPL v2.
# Plain Python (no Enigma2 imports): blocking calls, run them in a thread. Never log urls or passwords.
import http.cookiejar
import json
import os
import ssl
import time
import urllib.error
import urllib.request

from .config import DEVICES_FILE, PTZ_VECTORS, device_base, parse_devices
from .foscam import foscam_alarm, foscam_ptz, foscam_url
from . import unifi
from .onvif import (onvif_body, onvif_created, onvif_envelope, onvif_fault, onvif_profile_token, onvif_time,
                    onvif_xaddrs)

TIMEOUT = 4
MOVE_SECONDS = 0.5


class DeviceError(Exception):
    pass


def load_devices(path=DEVICES_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            return parse_devices(f.read())
    except OSError:
        return {}


def secure_file(path=DEVICES_FILE):
    """The devices file holds passwords: make it readable by its owner only (0600). True if it was changed."""
    try:
        mode = os.stat(path).st_mode & 0o777
        if mode & 0o077:
            os.chmod(path, mode & 0o700 | 0o600)
            return True
    except OSError:
        pass
    return False


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # the url contains the password: never put it in the message
        raise DeviceError("camera not reachable (%s)" % type(e).__name__)


def foscam_state(dev):
    """True if the camera reports a motion or sound alarm right now."""
    return foscam_alarm(_get(foscam_url(dev, "getDevState")))


def foscam_command(dev, cmd):
    xml = _get(foscam_url(dev, cmd))
    if "<result>0</result>" not in xml:
        raise DeviceError("Foscam %s refused" % cmd)


class Onvif(object):
    """Minimal ONVIF PTZ client: finds the media/PTZ service and profile once, corrects for the camera clock."""

    def __init__(self, dev):
        self.dev = dev
        self.device_url = device_base(dev) + "/onvif/device_service"
        self.offset = 0
        self.xaddrs = None
        self.token = None

    def call(self, url, action, auth=True, **kw):
        body = onvif_body(action, **kw)
        if auth and self.dev.get("user"):
            env = onvif_envelope(body, self.dev["user"], self.dev.get("password", ""), os.urandom(16),
                                 onvif_created(time.time() + self.offset))
        else:
            env = onvif_envelope(body)
        req = urllib.request.Request(url, data=env.encode("utf-8"),
                                     headers={"Content-Type": 'application/soap+xml; charset=utf-8'})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                xml = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            xml = e.read().decode("utf-8", "replace")
            raise DeviceError("ONVIF %s: %s" % (action, onvif_fault(xml) or e.code))
        except Exception as e:
            raise DeviceError("ONVIF %s: camera not reachable (%s)" % (action, type(e).__name__))
        fault = onvif_fault(xml)
        if fault:
            raise DeviceError("ONVIF %s: %s" % (action, fault))
        return xml

    def prepare(self):
        if self.token:
            return
        try:
            t = onvif_time(self.call(self.device_url, "GetSystemDateAndTime", auth=False))
            if t:
                self.offset = t - time.time()
        except DeviceError:
            pass
        self.xaddrs = onvif_xaddrs(self.call(self.device_url, "GetCapabilities"))
        if "ptz" not in self.xaddrs:
            raise DeviceError("camera has no ONVIF PTZ service")
        self.token = onvif_profile_token(self.call(self.xaddrs.get("media", self.device_url), "GetProfiles"))
        if not self.token:
            raise DeviceError("no ONVIF media profile")

    def ptz(self, action, seconds=MOVE_SECONDS):
        self.prepare()
        url = self.xaddrs["ptz"]
        if action == "home":
            self.call(url, "GotoHomePosition", token=self.token)
        elif action == "stop":
            self.call(url, "Stop", token=self.token)
        else:
            self.call(url, "ContinuousMove", token=self.token, vector=PTZ_VECTORS[action])
            time.sleep(seconds)
            self.call(url, "Stop", token=self.token)


_onvif = {}


def ptz(dev, action, seconds=MOVE_SECONDS):
    """Moves the camera for `seconds` and stops (blocking). Raises DeviceError."""
    if dev["type"] == "unifi":
        raise DeviceError("UniFi Protect: no PTZ")
    if dev["type"] == "foscam":
        start, stop = foscam_ptz(action)
        foscam_command(dev, start)
        if stop:
            time.sleep(seconds)
            foscam_command(dev, stop)
        return
    key = (dev["host"], dev["port"], dev.get("user"), dev.get("password"))
    client = _onvif.get(key)
    if client is None:
        client = _onvif[key] = Onvif(dev)
    try:
        client.ptz(action, seconds)
    except DeviceError:
        _onvif.pop(key, None)  # find services/profile again next time
        raise


# --- UniFi Protect (#9): read-only, GET only after the login -------------------------------------------------------
BOOTSTRAP_MAX_AGE = 600  # s: camera names are read again after this
EVENT_WINDOW = 60  # s of events asked at every poll
# Login backoff per console (#78): a refused or rate-limited login is not tried again at every poll (every few
# seconds, on every player), that keeps UniFi OS in HTTP 429 and can lock the account.
LOGIN_BACKOFF = (30, 60, 120, 300, 900)  # s after the 1st, 2nd, ... failure in a row (max 15 min)
RETRY_AFTER_MAX = 3600  # s: a larger Retry-After is capped


class HttpError(DeviceError):
    """An HTTP error answer of the console (code, Retry-After in seconds or None)."""

    def __init__(self, message, code, retry_after=None):
        DeviceError.__init__(self, message)
        self.code, self.retry_after = code, retry_after


class LoginError(DeviceError):
    """A failed login, or a login postponed by the backoff. kind: 'auth' (401/403, wrong user or password),
    'rate' (429), 'network' or 'http'; next_at: time of the next login attempt (epoch seconds)."""

    def __init__(self, message, kind, next_at=None):
        DeviceError.__init__(self, message)
        self.kind, self.next_at = kind, next_at


def retry_after(value, now=None):
    """Seconds from a Retry-After header (seconds or an HTTP date), capped at RETRY_AFTER_MAX; None if absent/bad."""
    if not value:
        return None
    value = str(value).strip()
    if value.isdigit():
        secs = int(value)
    else:
        try:
            from email.utils import mktime_tz, parsedate_tz
            secs = mktime_tz(parsedate_tz(value)) - (time.time() if now is None else now)
        except (TypeError, ValueError, OverflowError):
            return None
    return int(min(max(secs, 0), RETRY_AFTER_MAX))


class LoginBackoff(object):
    """Backoff of one console: 30 s, 1 min, 2 min, 5 min, then every 15 min; a longer Retry-After wins. Reset by a
    successful poll or a changed devices file (reset_logins())."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.failures = 0
        self.next_at = 0
        self.error = None  # the LoginError that started the current wait
        self.last_login = None  # time of the last login attempt

    def check(self, now):
        """Raises the LoginError of the current wait (same text, so it is logged once) until next_at."""
        if self.error is not None and now < self.next_at:
            raise LoginError(str(self.error), self.error.kind, self.next_at)

    def failed(self, error, now, wait=None):
        """Starts a wait after a failure; returns the error with next_at set."""
        delay = LOGIN_BACKOFF[min(self.failures, len(LOGIN_BACKOFF) - 1)]
        self.failures += 1
        if wait:
            delay = max(delay, wait)
        self.next_at = now + delay
        error.next_at = self.next_at
        self.error = error
        return error

    def logged_in(self):
        """A login was accepted: no wait now, but the failure count stays until a poll succeeds."""
        self.error = None


class Protect(object):
    """Session on a UniFi OS console (cookie + CSRF token). The console has a self-signed certificate, so the
    certificate is not checked (like the Home Assistant integration's default); only use it on the LAN.
    Logins go through a LoginBackoff (#78): never more than one login per backoff window."""

    def __init__(self, dev, opener=None, backoff=None, clock=None):
        self.dev = dev
        self.base = "https://%s:%d" % (dev["host"], dev["port"])
        self.csrf = None
        self.logged_in = False
        self.cams = {}
        self.cams_at = 0
        self.backoff = backoff or LoginBackoff()
        self.clock = clock or time.time
        self.jar = http.cookiejar.CookieJar()
        if opener is None:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx),
                                                 urllib.request.HTTPCookieProcessor(self.jar))
        self.opener = opener

    def _open(self, req, what):
        try:
            return self.opener.open(req, timeout=TIMEOUT * 2)
        except urllib.error.HTTPError as e:
            wait = retry_after(e.headers.get("Retry-After") if e.headers is not None else None, self.clock())
            raise HttpError("UniFi Protect %s: HTTP %d" % (what, e.code), e.code, wait)
        except Exception as e:  # never the password or the cookie in the message
            raise DeviceError("UniFi Protect %s: not reachable (%s)" % (what, type(e).__name__))

    def login(self):
        now = self.clock()
        self.backoff.check(now)
        b = self.backoff
        if b.last_login is not None and now - b.last_login < LOGIN_BACKOFF[0]:
            # the session was refused right after a login: do not log in again at once (#78)
            raise b.failed(LoginError("UniFi Protect: session refused right after the login (check user/password "
                                      "and the user's role)", "auth"), now)
        b.last_login = now
        self.logged_in = False
        self.jar.clear()  # an old session cookie makes the console refuse the login (403)
        self.csrf = None
        body = json.dumps({"username": self.dev.get("user", ""), "password": self.dev.get("password", ""),
                           "rememberMe": False}).encode("utf-8")
        req = urllib.request.Request(self.base + unifi.LOGIN_PATH, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with self._open(req, "login") as r:
                self.csrf = r.headers.get("X-CSRF-Token") or r.headers.get("X-Updated-CSRF-Token")
                r.read()
        except HttpError as e:
            if e.code in (401, 403):
                err = LoginError("UniFi Protect login refused (check user/password): HTTP %d" % e.code, "auth")
            elif e.code == 429:
                err = LoginError("UniFi Protect login: too many attempts (HTTP 429)", "rate")
            else:
                err = LoginError(str(e), "http")
            raise b.failed(err, now, e.retry_after)
        except DeviceError as e:
            raise b.failed(LoginError(str(e), "network"), now)
        b.logged_in()
        self.logged_in = True

    def get(self, path, raw=False):
        """GET with one new login when the session ran out (401), at most once per backoff window. JSON, or bytes
        with raw=True."""
        self.backoff.check(self.clock())
        for attempt in (0, 1):
            if not self.logged_in:
                self.login()
            headers = {"X-CSRF-Token": self.csrf} if self.csrf else {}
            try:
                with self._open(urllib.request.Request(self.base + path, headers=headers), "request") as r:
                    data = r.read()
                break
            except HttpError as e:
                if e.code == 429:  # the console is rate limiting: wait like after a refused login
                    raise self.backoff.failed(LoginError("UniFi Protect request: too many requests (HTTP 429)",
                                                         "rate"), self.clock(), e.retry_after)
                if attempt == 0 and e.code == 401:
                    self.logged_in = False
                    continue
                raise
        if raw:
            return data
        try:
            return json.loads(data.decode("utf-8", "replace"))
        except ValueError:
            raise DeviceError("UniFi Protect: unexpected answer")

    def cameras(self, now=None):
        now = time.time() if now is None else now
        if not self.cams or now - self.cams_at > BOOTSTRAP_MAX_AGE:
            self.cams = unifi.protect_cameras(self.get(unifi.BOOTSTRAP_PATH))
            self.cams_at = now
        return self.cams

    def state(self, now=None):
        """{'now': ms, 'cams': {id: name}, 'events': [...]} of the last EVENT_WINDOW seconds."""
        now = time.time() if now is None else now
        cams = self.cameras(now)
        ms = int(now * 1000)
        events = self.get(unifi.events_path(ms - EVENT_WINDOW * 1000, ms))
        self.backoff.reset()  # a whole poll worked: the next failure starts at 30 s again
        return {"now": ms, "cams": cams, "events": events if isinstance(events, list) else []}

    def snapshot(self, camera_id, width=1280):
        return self.get(unifi.snapshot_path(camera_id, width), raw=True)


_protect = {}  # (host, port, user, password) -> Protect; the session (cookie) is kept across polls and errors
_backoff = {}  # (host, port) -> LoginBackoff: one per console, whatever the login


def backoff_for(dev):
    return _backoff.setdefault((dev["host"], dev["port"]), LoginBackoff())


def reset_logins():
    """The devices file changed (maybe new credentials): forget the sessions and every login backoff (#78)."""
    _protect.clear()
    for b in _backoff.values():
        b.reset()


def protect_state(dev):
    """Events of the last minute on one Protect console (blocking; run it in a thread). Raises DeviceError
    (LoginError with next_at while a login is refused or postponed)."""
    key = (dev["host"], dev["port"], dev.get("user"), dev.get("password"))
    client = _protect.get(key)
    if client is None:
        for old in [k for k in _protect if k[:2] == key[:2]]:  # other credentials of the same console
            _protect.pop(old)
        client = _protect[key] = Protect(dev, backoff=backoff_for(dev))
    return client.state()
