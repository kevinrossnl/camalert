"""Fakes for the e2e runner tests (#35): an Enigma2 receiver (OpenWebif + CamAlert API + ssh box) and a Kodi player
(JSON-RPC over TCP + CamAlert API). No devices: everything runs on 127.0.0.1.

The receiver keeps the same state a real one has (volume, mute toggle, standby, service, saved settings, devices
file) and draws its OSD from the CamAlert state, with the fake camera colours and camalert_core.layout geometry.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from socketserver import BaseRequestHandler, ThreadingTCPServer
from urllib.parse import parse_qs, urlsplit

import _paths

_paths.core()
_paths.e2e()
from camalert_core import api, layout, schema  # noqa: E402
from camalert_e2e import fakes, geometry  # noqa: E402
from camalert_e2e.adapters.enigma2 import PREFIX, config_text  # noqa: E402
from contract.adapters import DEFAULTS  # noqa: E402

SCREEN = (320, 180)
REAL_DEVICES = "front_door|foscam|192.168.1.50:88|admin|real\n"


class Clock(object):
    """Fake time: sleep() moves it on."""

    def __init__(self, t=1000000.0):
        self.t, self.slept = t, 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s
        self.slept += s


class SimController(object):
    """What the player shows (photo window, strip, mosaic, tour) and its rules (dnd)."""

    def __init__(self, clock, box=None, on_change=None):
        self.clock, self.box, self.on_change = clock, box, on_change or (lambda: None)
        self.screen, self.dnd, self.calls, self.events, self.last_caller = None, False, [], [], None

    def show(self, stream=None, seconds=None, mode=None, priority=None, source="api", label=None, event_id=None):
        self.calls.append(("show", stream, mode, priority, source))
        if self.dnd and priority in (None, "normal"):
            return "ignore"
        cams = (stream or "front_door").split(",")
        self.screen = ("strip" if len(cams) > 1 else "photo", cams, self.clock())
        self.on_change()
        return "show"

    keeps = ()  # Enigma2 before 1.0: ("tour", "mosaic") stayed open on hide (#63)
    reports_screen = True  # status "screen" (#63); False = a player older than 1.0

    def hide(self, resume=True):
        self.calls.append(("hide",))
        if not (self.screen and self.screen[0] in self.keeps):
            self.screen = None
        self.on_change()

    def mosaic(self, streams=None, seconds=0):
        self.calls.append(("mosaic", streams))
        self.screen = ("mosaic", (streams or "").split(","), self.clock())
        self.on_change()
        return "show"

    def tour(self, streams=None, interval=None):
        self.calls.append(("tour", streams, interval))
        self.screen = ("tour", (streams or "").split(","), self.clock(), interval or 8)
        self.on_change()
        return "show"

    def has_ptz(self, name):
        return True

    def ptz_move(self, action, name=None):
        self.calls.append(("ptz", action, name))
        if self.box is None or name not in self.box.devices or "127.0.0.1" not in self.box.devices:
            self.calls.append(("REAL CAMERA MOVED", name))
            return True
        self.box.ptz.append({"left": "ptzMoveLeft"}.get(action, action))
        return True

    def set_dnd(self, on):
        self.dnd = bool(on)

    def status(self):
        window = ",".join(self.screen[1]) if self.screen and self.screen[0] in ("photo", "strip") else None
        out = {"window": window, "live": None, "paused": False, "dnd": self.dnd}
        if self.reports_screen:
            out["screen"] = self.screen[0] if self.screen else "none"
        return out


class Backend(api.Backend):
    platform, version = "fake", "1.0.0"

    def __init__(self, ctl, cameras):
        self.ctl, self.camera_list = ctl, cameras

    def settings(self):
        return dict(DEFAULTS, dnd=self.ctl.dnd)

    def controller(self):
        return self.ctl

    def node(self):
        return "node1", "CamAlert fake"

    def cameras(self):
        return [{"name": n, "title": n, "snapshot": True} for n in self.camera_list()]

    def log(self, message, level="normal"):
        pass


def api_server(backend):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _do(self, method):
            url = urlsplit(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            api.LIMIT.seen.clear()
            resp = api.handle(backend, api.Request(method, url.path, {k: v[0] for k, v in parse_qs(url.query).items()},
                                                   "192.168.1.5", self.headers.get("X-CamAlert-Token"),
                                                   self.headers.get("User-Agent"), body,
                                                   self.headers.get("Content-Type", "")))
            if isinstance(resp.body, dict) and not getattr(backend.ctl, "reports_screen", True):
                resp.body.pop("screen", None)  # a player older than 1.0 (#63)
            data = resp.payload()
            self.send_response(resp.code)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._do("GET")

        def do_POST(self):
            self._do("POST")
    return _start(ThreadingHTTPServer(("127.0.0.1", 0), Handler))


def _start(srv):
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return srv


class FakeBox(object):
    """The ssh side of the receiver (Box interface of adapters/enigma2.py)."""

    def __init__(self):
        self.devices, self.backup, self.files, self.procs, self.ptz, self.next_pid = REAL_DEVICES, None, {}, {}, [], 100
        self.fail_go2rtc = False

    def upload(self, name, text):
        self.files[name] = text

    def start(self, name, args):
        self.next_pid += 1
        self.procs[self.next_pid] = name
        return self.next_pid

    def stop(self, pid):
        self.procs.pop(pid, None)

    def fetch(self, url):
        if self.fail_go2rtc or "go2rtc.py" not in self.procs.values():
            raise OSError("connection refused")
        return json.dumps({n: {} for n in fakes.NAMES})

    def swap_devices(self):
        if self.backup is not None:
            from camalert_e2e.errors import Skip
            raise Skip("an old devices backup is still on the receiver: run --restore last first")
        if self.devices is None:
            return "absent"
        self.backup = self.devices
        return "existed"

    def write_devices(self, content):
        self.devices = content

    def restore_devices(self, how):
        if how == "existed" and self.backup is not None:
            self.devices, self.backup = self.backup, None
        elif how == "absent":
            self.devices = None
        return self.backup is None

    def cleanup(self):
        self.files = {}

    def read_ptz_calls(self):
        return "\n".join(self.ptz)


def schema_text(key):
    return config_text(schema.defaults("enigma2")[key])


class Receiver(object):
    """Fake Enigma2 receiver: OpenWebif on one port, the CamAlert API on another, a FakeBox for ssh."""

    def __init__(self, clock, standby=False, volume=30, muted=False, saved=None, recording=False, timers=(),
                 mute_works=True, set0_works=True):
        self.clock, self.box = clock, FakeBox()
        self.volume, self.muted, self.standby, self.recording = volume, muted, standby, recording
        self.timers, self.mute_works, self.set0_works = list(timers), mute_works, set0_works
        self.service = "1:0:19:1:1:1:C00000:0:0:0:"
        self.saved = dict(saved or {})
        self.saveconfig_calls, self.grabs, self.blank_grabs, self.keys = [], 0, 0, []
        self.ctl = SimController(clock, self.box)
        self.api = api_server(Backend(self.ctl, lambda: fakes.NAMES if "127.0.0.1" in self.saved.get("server", "")
                                      else ["porch", "shed"]))
        self.owif = _start(HTTPServer(("127.0.0.1", 0), self._handler()))

    def close(self):
        for s in (self.api, self.owif):
            s.shutdown()
            s.server_close()

    def profile(self, **kw):
        p = {"type": "enigma2", "host": "127.0.0.1", "camalert_port": self.api.server_address[1],
             "openwebif_port": self.owif.server_address[1], "ssh": "fake-box", "cameras": "fake",
             "allowed_hours": "00:00-23:59"}
        p.update(kw)
        return p

    # --- the OSD ------------------------------------------------------------------------------------------------
    def settings_for_geometry(self):
        d = schema.defaults("enigma2")
        return {k: self.saved.get(k, d[k]) for k in ("position", "size", "title_size", "strip_layout")}

    def osd(self):
        w, h = SCREEN
        rects = []
        s = self.ctl.screen
        g = self.settings_for_geometry()
        if s and s[0] == "photo":
            x, y, pw, ph, title = layout.window_geometry(g["position"], g["size"], w, h, g["title_size"])
            rects = [((x, y + title, pw, ph), s[1][0])]
        elif s and s[0] == "strip":
            rects = list(zip(geometry.strip_rects(len(s[1]), g, w, h), s[1]))
        elif s and s[0] == "mosaic":
            rects = list(zip(layout.grid(len(s[1]), w, h), s[1]))
        elif s and s[0] == "tour":
            cams, start, iv = s[1], s[2], s[3]
            rects = [((0, 0, w, h), cams[int((self.clock() - start) // iv) % len(cams)])]
        colours = fakes.CAMERAS if "127.0.0.1" in self.saved.get("server", "") else {}

        def pixel(px, py):
            for (x, y, rw, rh), cam in rects:
                if x <= px < x + rw and y <= py < y + rh:
                    return colours.get(cam, (200, 200, 200)) + (255,)
            return (0, 0, 0, 0)
        return geometry.encode_png(w, h, pixel)

    # --- OpenWebif ----------------------------------------------------------------------------------------------
    def _handler(self):
        rx = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, body, ctype="application/json", code=200):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlsplit(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                self._send(*rx.route(url.path, q))

            def do_POST(self):
                url = urlsplit(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                q = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
                self._send(*rx.route(url.path, q))
        return Handler

    def route(self, path, q):
        if path == "/api/statusinfo":
            return ({"inStandby": "true" if self.standby else "false", "isRecording": "true" if self.recording
                     else "false", "volume": self.volume, "muted": self.muted,
                     "currservice_serviceref": self.service},)
        if path == "/api/vol":
            cmd = q.get("set")
            if cmd == "mute" and self.mute_works:
                self.muted = not self.muted
            elif cmd and cmd.startswith("set") and (self.set0_works or cmd != "set0"):
                self.volume = int(cmd[3:])
            return ({"result": True, "current": self.volume, "ismute": self.muted},)
        if path == "/api/timerlist":
            return ({"result": True, "timers": self.timers},)
        if path == "/api/settings":
            return ({"result": True, "settings": [["config.av.videomode.HDMI", "1080i"]]
                     + [[PREFIX + k, v] for k, v in sorted(self.saved.items())]},)
        if path == "/api/saveconfig":
            key, value = q["key"][len(PREFIX):], q["value"]
            self.saveconfig_calls.append((key, value))
            if isinstance(schema.defaults("enigma2")[key], bool):
                # like OpenWebif saveConfig: a boolean is True only for exactly "true"; /api/settings shows "True"
                value = "True" if value == "true" else "False"
                if (value == "True") == schema.defaults("enigma2")[key]:
                    value = schema_text(key)
            if value == schema_text(key):
                self.saved.pop(key, None)
            else:
                self.saved[key] = value
            return ({"result": True, "value": value},)
        if path == "/api/powerstate":
            self.standby = {"4": False, "5": True}.get(q.get("newstate"), self.standby)
            return ({"result": True, "instandby": self.standby},)
        if path == "/api/remotecontrol":
            self.keys.append(int(q.get("command", 0)))
            if q.get("command") == "174":
                self.ctl.screen = None
            return ({"result": True},)
        if path == "/api/zap":
            self.service = q.get("sRef", self.service)
            return ({"result": True},)
        if path == "/grab":
            self.grabs += 1
            if self.blank_grabs:  # the window is there, its picture is not loaded yet
                self.blank_grabs -= 1
                return (geometry.encode_png(SCREEN[0], SCREEN[1], lambda x, y: (0, 0, 0, 0)), "image/png")
            return (self.osd(), "image/png")
        return ({"result": False}, "application/json", 404)


class FakeKodi(object):
    """Kodi JSON-RPC on a raw TCP port (with a notification before every answer) + the CamAlert API."""

    def __init__(self, clock, playing=0, volume=60, muted=False, window=10000, mute_works=True):
        self.clock, self.playing, self.volume, self.muted, self.win = clock, playing, volume, muted, window
        self.mute_works, self.requests = mute_works, []
        self.ctl = SimController(clock, on_change=self._changed)
        self.api = api_server(Backend(self.ctl, lambda: ["porch", "shed", "yard"]))
        kodi = self

        class Handler(BaseRequestHandler):
            def handle(self):
                dec, buf = json.JSONDecoder(), ""
                while True:
                    try:
                        obj, _end = dec.raw_decode(buf)
                        break
                    except ValueError:
                        data = self.request.recv(65536)
                        if not data:
                            return
                        buf += data.decode()
                note = {"jsonrpc": "2.0", "method": "GUI.OnScreensaverDeactivated", "params": {"data": None}}
                self.request.sendall((json.dumps(note) + json.dumps(kodi.answer(obj))).encode())
        ThreadingTCPServer.allow_reuse_address = True
        self.rpc = _start(ThreadingTCPServer(("127.0.0.1", 0), Handler))

    def _changed(self):
        s = self.ctl.screen
        self.win = 13001 if s and s[0] == "mosaic" else 13000 if s else 10000

    def close(self):
        for s in (self.api, self.rpc):
            s.shutdown()
            s.server_close()

    def profile(self, **kw):
        p = {"type": "kodi", "host": "127.0.0.1", "camalert_port": self.api.server_address[1], "jsonrpc": "tcp",
             "jsonrpc_port": self.rpc.server_address[1], "allowed_hours": "00:00-23:59"}
        p.update(kw)
        return p

    def answer(self, req):
        m, p = req["method"], req.get("params") or {}
        self.requests.append(m)
        res = None
        if m == "Application.GetProperties":
            res = {"volume": self.volume, "muted": self.muted}
        elif m == "Application.SetMute":
            if self.mute_works:
                self.muted = bool(p["mute"])
            res = self.muted
        elif m == "Application.SetVolume":
            self.volume = int(p["volume"])
            res = self.volume
        elif m == "Player.GetActivePlayers":
            res = [{"playerid": 1, "type": "video"}] * self.playing
        elif m == "GUI.GetProperties":
            res = {"currentwindow": {"id": self.win, "label": "x"}}
        elif m == "GUI.ActivateWindow":
            self.win = 10000 if p.get("window") == "home" else self.win
            res = "OK"
        else:
            return {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32601, "message": "Method not found."}}
        return {"jsonrpc": "2.0", "id": req["id"], "result": res}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port
