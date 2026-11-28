"""Run one HTTP request against a player's API handler and return (status code, answer, controller).

Both adapters take the same request description, so the contract table (test_http_contract.py) runs unchanged
against Enigma2 and Kodi:

    Request(path, args={}, ip="192.168.1.5", header=None, user_agent="", settings={})

settings: enabled, allow, token, camera, duration, dnd (same names on both players).
"""
import json
from urllib.parse import urlencode

import _paths
from fakes import dns
from fakes.controller import RecordingController

dns.install()  # webhook host names under .example resolve without real DNS (#53)

DEFAULTS = {"enabled": True, "allow": "lan", "token": "", "camera": "front_door", "duration": 30, "dnd": False,
            "allow_update": True, "speak": "high",
            "ha_webhook": "", "ha_webhook_secret": "", "position": "top_right", "size": "medium", "server": "", "source": "go2rtc"}


class Request(object):
    def __init__(self, path, args=None, ip="192.168.1.5", header=None, user_agent="", settings=None, method="GET",
                 body=None):
        self.path, self.args, self.ip, self.header, self.user_agent = path, dict(args or {}), ip, header, user_agent
        self.settings = dict(DEFAULTS, **(settings or {}))
        self.method, self.body = method, body


class Answer(object):
    def __init__(self, code, body, content_type, ctl, headers=None):
        self.code, self.body, self.content_type, self.ctl = code, body, content_type, ctl
        self.headers = headers or {}

    @property
    def json(self):
        return self.body if isinstance(self.body, dict) else None


class KodiAdapter(object):
    platform = "kodi"

    def __init__(self):
        from kodi import stubs
        self.store = stubs.install()
        _paths.kodi_package()
        self.server = _paths.kodi_module("server")
        self.klogic = _paths.kodi_module("klogic")
        self.controller = _paths.kodi_module("controller")
        self.api = _paths.kodi_module("camalert_core.api")
        self.reset()

    def reset(self):
        self.api.LIMIT.seen.clear()
        self.api.WARNED.clear()

    def settings(self, values):
        self.store.clear()
        for k, v in values.items():
            self.store[k] = str(v).lower() if isinstance(v, bool) else str(v)
        return self.klogic.parse_settings(self.store)

    def set_cameras(self, names):
        """go2rtc answers with these cameras (None = restore)."""
        src = _paths.kodi_module("sources")
        if not hasattr(self, "_orig"):
            self._orig = (src.all_camera_names, src.camera_urls)
        if names is None:
            src.all_camera_names, src.camera_urls = self._orig
            return
        src.all_camera_names = lambda s=None: list(names)
        src.camera_urls = lambda n, s=None: ("http://x/%s.mp4" % n, "http://x/%s.jpg" % n,
                                              n.replace("_", " ").capitalize())

    def call(self, req, ctl=None):
        ctl = ctl or RecordingController()
        if not hasattr(self.server.Handler, "do_" + req.method):
            return Answer(501, None, "", ctl)  # http.server: "Unsupported method"
        self.settings(req.settings)
        self.controller.Controller.instance = ctl
        args, body, ctype = req.args, b"", ""
        if req.method == "POST" and req.body is None:  # the table's parameters go into a form body
            args, body, ctype = {}, urlencode(req.args).encode(), "application/x-www-form-urlencoded"
        elif req.body is not None:
            body, ctype = req.body, "application/json"
        r = self.api.Request(req.method, req.path, args, req.ip, req.header, req.user_agent, body, ctype)
        self.server.BACKEND.start_update = lambda v: ctl.calls.append(("update", v))  # #126: never download here
        resp = self.api.handle(self.server.BACKEND, r)
        ctype = resp.content_type.split(";")[0]
        return Answer(resp.code, resp.body, ctype, ctl, resp.headers)


class FakeTwistedRequest(object):
    """What Api.render uses of twisted.web.server.Request."""

    def __init__(self, req):
        self.method = req.method.encode()
        self.path = req.path.encode()
        args, body, ctype = req.args, req.body, None
        if req.method == "POST" and body is None:  # the table's parameters go into a form body
            args, body, ctype = {}, urlencode(req.args).encode(), b"application/x-www-form-urlencoded"
        elif body is not None:
            ctype = b"application/json"
        query = urlencode(args)
        self.uri = (req.path + ("?" + query if query else "")).encode()
        self.args = {k.encode(): [str(v).encode()] for k, v in args.items()}
        self.headers = {}
        if ctype:
            self.headers[b"content-type"] = ctype
        if req.header is not None:
            self.headers[b"x-camalert-token"] = req.header.encode()
        if req.user_agent:
            self.headers[b"user-agent"] = req.user_agent.encode()
        self.ip = req.ip
        self.code = 200
        self.out_headers = {}
        self.written = b""
        self.finished = False
        self.content = __import__("io").BytesIO(body or b"")

    def getHeader(self, name):
        return self.headers.get(name.lower() if isinstance(name, bytes) else name.lower().encode())

    def getClientAddress(self):
        return type("Addr", (), {"host": self.ip})()

    def setResponseCode(self, code):
        self.code = code

    def setHeader(self, k, v):
        self.out_headers[k.decode().lower() if isinstance(k, bytes) else k.lower()] = \
            v.decode() if isinstance(v, bytes) else v

    def write(self, data):
        self.written += data

    def finish(self):
        self.finished = True


class Enigma2Adapter(object):
    platform = "enigma2"

    def __init__(self, profile="openatv"):
        from enigma2.harness import e2fake
        self.e2fake = e2fake
        self.env = e2fake.install(profile)
        self.server = self.env.camalert.server
        self.display = self.env.camalert.display
        self.c = self.env.config.plugins.camalert
        import importlib
        self.api = importlib.import_module("CamAlert.camalert_core.api")
        self.reset()

    def close(self):
        self.e2fake.uninstall()

    def reset(self):
        self.api.LIMIT.seen.clear()
        self.api.WARNED.clear()

    def set_cameras(self, names):
        if not hasattr(self, "_orig"):
            self._orig = (self.server.all_camera_names, self.server.camera_urls)
        if names is None:
            self.server.all_camera_names, self.server.camera_urls = self._orig
            return
        self.server.all_camera_names = lambda: list(names)
        self.server.camera_urls = lambda n: ("rtspt://x/%s" % n, "http://x/%s.jpg" % n,
                                             n.replace("_", " ").capitalize())

    def call(self, req, ctl=None):
        ctl = ctl or RecordingController()
        for k, v in req.settings.items():
            getattr(self.c, k).value = v
        self.display.Controller.instance = ctl
        self.server.BACKEND.start_update = lambda v: ctl.calls.append(("update", v))  # #126: never download here
        tw = FakeTwistedRequest(req)
        out = self.server.Api().render(tw)
        if out == 1:  # NOT_DONE_YET: run the deferred work as the reactor thread pool would
            for d in list(self.env.reactor.deferred):
                self.env.reactor.deferred.remove(d)
                d.fire(d.fn(*d.args))
            out = tw.written
        ctype = tw.out_headers.get("content-type", "")
        text = out.decode() if isinstance(out, bytes) else out
        body = json.loads(text) if ctype.startswith("application/json") else text
        return Answer(tw.code, body, ctype.split(";")[0], ctl, tw.out_headers)
