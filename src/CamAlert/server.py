# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Small HTTP API on the receiver:

    GET /camalert/show?cam=front_door&sec=30&mode=photo|live|notify[&token=...]
    GET /camalert/mosaic?cam=front_door,garden,drive&sec=60
    GET /camalert/cameras
    GET /camalert/hide
    GET /camalert/status
"""
import json
import os
import subprocess

from twisted.web import resource, server
from twisted.internet import reactor
from Components.config import config

from . import __version__
from .display import Controller, all_camera_names, camera_urls, log
from .logic import client_allowed, clamp_seconds, token_ok

_port = None
CERT = "/etc/enigma2/camalert.crt"
KEY = "/etc/enigma2/camalert.key"


def ensure_certificate():
    """Creates a self-signed certificate (10 years) for the HTTPS API if there is none yet."""
    if os.path.exists(CERT) and os.path.exists(KEY):
        return True
    try:
        subprocess.check_call(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                               "-subj", "/CN=CamAlert", "-keyout", KEY, "-out", CERT],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(KEY, 0o600)
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        log("could not create certificate:", e)
        return False


class Api(resource.Resource):
    isLeaf = True

    def render_GET(self, req):
        c = config.plugins.camalert
        req.setHeader(b"content-type", b"application/json")
        args = {k.decode(): v[0].decode() for k, v in req.args.items()}
        header = req.getHeader(b"x-camalert-token")
        given = args.get("token") or (header.decode() if isinstance(header, bytes) else header or "")
        if not client_allowed(req.getClientAddress().host, c.allow.value) or not token_ok(c.token.value, given):
            req.setResponseCode(403)
            return b'{"result": false, "error": "forbidden"}'
        if not c.enabled.value:
            return b'{"result": false, "error": "disabled"}'
        action = req.path.decode().rstrip("/").rsplit("/", 1)[-1]
        ctl = Controller.instance
        try:
            if action == "hide":
                ctl.hide()
                out = {"result": True, "action": "hide"}
            elif action == "mosaic":
                sec = clamp_seconds(args.get("sec"), 60) if args.get("sec") else 60
                res = ctl.mosaic(args.get("cam"), sec)
                out = {"result": res == "show", "action": res}
            elif action == "cameras":
                cams = []
                for n in all_camera_names():
                    urls = camera_urls(n)
                    cams.append({"name": n, "title": urls[2] if urls else n, "snapshot": bool(urls and urls[1])})
                out = {"result": True, "cameras": cams}
            elif action == "status":
                from .mqtt import node_id, node_name
                out = dict(ctl.status(), result=True, version=__version__, id=node_id(), name=node_name())
            elif action in ("show", "camalert"):
                sec = clamp_seconds(args.get("sec"), int(c.duration.value)) if args.get("sec") else None
                res = ctl.show(args.get("cam"), sec, args.get("mode"))
                out = {"result": res in ("show", "extend"), "action": res, "cam": args.get("cam") or c.camera.value}
            else:
                req.setResponseCode(404)
                out = {"result": False, "error": "unknown action"}
        except Exception as e:
            log("request failed:", e)
            req.setResponseCode(500)
            out = {"result": False, "error": "internal error"}
        return json.dumps(out).encode()


def start():
    global _port
    stop()
    root = resource.Resource()
    root.putChild(b"camalert", Api())
    c = config.plugins.camalert
    try:
        if c.api_https.value and ensure_certificate():
            from twisted.internet import ssl
            ctx = ssl.DefaultOpenSSLContextFactory(KEY, CERT)
            _port = reactor.listenSSL(int(c.http_port.value), server.Site(root), ctx)
            log("listening on port", c.http_port.value, "(https)")
        else:
            _port = reactor.listenTCP(int(c.http_port.value), server.Site(root))
            log("listening on port", c.http_port.value)
    except Exception as e:
        log("could not start HTTP API:", e)


def stop():
    global _port
    if _port is not None:
        _port.stopListening()
        _port = None
CERT = "/etc/enigma2/camalert.crt"
KEY = "/etc/enigma2/camalert.key"


def ensure_certificate():
    """Creates a self-signed certificate (10 years) for the HTTPS API if there is none yet."""
    if os.path.exists(CERT) and os.path.exists(KEY):
        return True
    try:
        subprocess.check_call(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                               "-subj", "/CN=CamAlert", "-keyout", KEY, "-out", CERT],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(KEY, 0o600)
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        log("could not create certificate:", e)
        return False
