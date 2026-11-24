# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""HTTP API, same paths and answers as the Enigma2 plugin:

    GET /camalert/show?cam=front_door&sec=30&mode=photo|live|notify&priority=normal|high|alarm[&token=...]
    GET /camalert/mosaic?cam=a,b,c&sec=60
    GET /camalert/tour?cam=a,b&interval=8
    GET /camalert/cameras
    GET /camalert/hide
    GET /camalert/status
    GET /camalert/dnd?on=1|0      (without 'on': current state)
"""
import json
import os
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, kodiapi, sources
from .klogic import node_from_mac
from .logic import clamp_seconds, client_allowed, token_ok, valid_port

_server = None
_thread = None


def node_id():
    return node_from_mac(kodiapi.mac_address(), kodiapi.friendly_name())


def node_name(s=None):
    s = s or kodiapi.settings()
    return s["mqtt_name"].strip() or "CamAlert %s" % kodiapi.friendly_name()


def cert_paths():
    d = kodiapi.profile_dir()
    return os.path.join(d, "camalert.crt"), os.path.join(d, "camalert.key")


def ensure_certificate():
    cert, key = cert_paths()
    if os.path.exists(cert) and os.path.exists(key):
        return True
    try:
        subprocess.check_call(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                               "-subj", "/CN=CamAlert", "-keyout", key, "-out", cert],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        kodiapi.log("could not create certificate: %s" % e)
        return False


def handle(ctl, path, args, client_ip, header_token, s):
    """(http code, answer dict) for one request. Pure enough to test with a fake controller."""
    given = args.get("token") or header_token or ""
    if not client_allowed(client_ip, s["allow"]) or not token_ok(s["token"], given):
        return 403, {"result": False, "error": "forbidden"}
    if not s["enabled"]:
        return 200, {"result": False, "error": "disabled"}
    action = path.rstrip("/").rsplit("/", 1)[-1]
    if not path.startswith("/camalert"):
        return 404, {"result": False, "error": "unknown action"}
    try:
        if action == "hide":
            ctl.hide()
            return 200, {"result": True, "action": "hide"}
        if action == "mosaic":
            sec = clamp_seconds(args.get("sec"), 60) if args.get("sec") else 60
            res = ctl.mosaic(args.get("cam"), sec)
            return 200, {"result": res == "show", "action": res}
        if action == "tour":
            iv = args.get("interval")
            res = ctl.tour(args.get("cam"), max(3, min(60, int(iv))) if iv and iv.isdigit() else None)
            return 200, {"result": res == "show", "action": res}
        if action == "cameras":
            try:
                cams = []
                for n in sources.all_camera_names(s):
                    urls = sources.camera_urls(n, s)
                    cams.append({"name": n, "title": urls[2] if urls else n, "snapshot": bool(urls and urls[1])})
            except Exception as e:
                kodiapi.log("camera list failed: %s" % e)
                return 200, {"result": False, "error": "camera source not reachable"}
            ctl.names, ctl.names_at = [c["name"] for c in cams], time.time()
            return 200, {"result": True, "cameras": cams}
        if action == "status":
            return 200, dict(ctl.status(), result=True, version=__version__, id=node_id(), name=node_name(s))
        if action == "dnd":
            on = args.get("on", "").lower()
            if on in ("1", "true", "on", "yes"):
                ctl.set_dnd(True)
            elif on in ("0", "false", "off", "no"):
                ctl.set_dnd(False)
            return 200, {"result": True, "action": "dnd", "dnd": kodiapi.settings()["dnd"]}
        if action in ("show", "camalert"):
            sec = clamp_seconds(args.get("sec"), s["duration"]) if args.get("sec") else None
            res = ctl.show(args.get("cam"), sec, args.get("mode"), args.get("priority"))
            return 200, {"result": res in ("show", "extend", "wake"), "action": res, "cam": args.get("cam") or s["camera"]}
        return 404, {"result": False, "error": "unknown action"}
    except Exception as e:
        kodiapi.log("request failed: %s" % e)
        return 500, {"result": False, "error": "internal error"}


class Handler(BaseHTTPRequestHandler):
    server_version = "CamAlert"

    def do_GET(self):
        from .controller import Controller
        u = urlparse(self.path)
        args = {k: v[0] for k, v in parse_qs(u.query).items()}
        code, out = handle(Controller.instance, u.path, args, self.client_address[0],
                           self.headers.get("X-CamAlert-Token"), kodiapi.settings())
        body = json.dumps(out).encode()
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, fmt, *a):  # requests contain the token: never log them
        pass


def start():
    global _server, _thread
    stop()
    s = kodiapi.settings()
    port = valid_port(s["http_port"], 8099)
    try:
        srv = ThreadingHTTPServer(("", port), Handler)
        srv.daemon_threads = True
        https = bool(s["api_https"] and ensure_certificate())
        if https:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(*cert_paths())
            srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        _server = srv
        _thread = threading.Thread(target=srv.serve_forever, name="camalert-http", daemon=True)
        _thread.start()
        kodiapi.log("listening on port %d%s" % (port, " (https)" if https else ""))
    except OSError as e:
        kodiapi.log("could not start HTTP API: %s" % e)


def stop():
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server = _thread = None
