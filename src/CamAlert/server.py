# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Small HTTP API on the receiver:

    GET /camalert/show?cam=front_door&sec=30&mode=photo|live|notify|strip&priority=normal|high|alarm[&token=...]
    GET /camalert/mosaic?cam=front_door,garden,drive&sec=60
    GET /camalert/cameras
    GET /camalert/tour?cam=front_door,garden&interval=8
    GET /camalert/dnd?on=1|0         (do not disturb; without "on" it only reports the state)
    GET /camalert/ptz?cam=garden&move=up|down|left|right|zoom_in|zoom_out|home|stop
    GET /camalert/webhook?url=...    (Home Assistant webhook for remote buttons; empty url removes it)
    GET /camalert/log?lines=200      (camalert.log, redacted)
    GET /camalert/events             (last 20 requests with decision)
    GET /camalert/hide
    GET /camalert/status
"""
import json
import os
import subprocess
import time

from twisted.web import resource, server
from twisted.internet import reactor, threads
from Components.config import config, configfile

from . import __version__
from .display import Controller, all_camera_names, camera_urls, log
from .camlog import LOG
from .logic import PTZ_ACTIONS, caller_source, redact, valid_port, client_allowed, clamp_seconds, token_ok

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


def finish(req, out):
    try:
        req.write(json.dumps(out).encode())
        req.finish()
    except Exception:  # client went away
        pass


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
        ua = req.getHeader(b"user-agent")
        source = caller_source(ua.decode("utf-8", "replace") if isinstance(ua, bytes) else ua)
        ctl.last_caller = (time.time(), req.getClientAddress().host, source)
        log("API %s from %s (%s)" % (redact(req.uri.decode("utf-8", "replace")), req.getClientAddress().host, source),
            level="verbose")
        try:
            if action == "hide":
                ctl.hide()
                out = {"result": True, "action": "hide"}
            elif action == "ptz":
                cam, move = args.get("cam"), args.get("move")
                if move not in PTZ_ACTIONS or not ctl.has_ptz(cam):
                    req.setResponseCode(400)
                    out = {"result": False, "error": "camera without PTZ or unknown move"}
                else:
                    out = {"result": ctl.ptz_move(move, cam), "cam": cam, "move": move}
            elif action == "webhook":
                url = args.get("url", "")
                if url and not url.startswith(("http://", "https://")):
                    req.setResponseCode(400)
                    out = {"result": False, "error": "url must start with http:// or https://"}
                else:
                    if url != c.ha_webhook.value:
                        c.ha_webhook.value = url
                        c.ha_webhook.save()
                        configfile.save()
                        log("Home Assistant webhook %s" % ("set" if url else "removed"))
                    out = {"result": True, "webhook": bool(url)}
            elif action == "log":
                n = int(args["lines"]) if args.get("lines", "").isdigit() else 200
                out = {"result": True, "lines": [redact(x) for x in LOG.tail(min(n, 2000))]}
            elif action == "events":
                out = {"result": True, "events": [{k: v for k, v in e.items() if k != "snapshot"}
                                                  for e in ctl.events]}
            elif action == "dnd":
                if "on" in args:
                    ctl.set_dnd(args["on"].lower() in ("1", "true", "on", "yes"))
                out = {"result": True, "dnd": bool(c.dnd.value)}
            elif action == "mosaic":
                sec = clamp_seconds(args.get("sec"), 60) if args.get("sec") else 60
                res = ctl.mosaic(args.get("cam"), sec)
                log("mosaic from %s: cameras=%s -> %s" % (source, args.get("cam") or "-", res))
                out = {"result": res == "show", "action": res}
            elif action == "tour":
                iv = args.get("interval")
                res = ctl.tour(args.get("cam"), max(3, min(60, int(iv))) if iv and iv.isdigit() else None)
                log("tour from %s: cameras=%s -> %s" % (source, args.get("cam") or "-", res))
                out = {"result": res == "show", "action": res}
            elif action == "cameras":
                # go2rtc mode needs a network call: never block the GUI, answer from a thread
                def collect():
                    cams = []
                    for n in all_camera_names():
                        urls = camera_urls(n)
                        cams.append({"name": n, "title": urls[2] if urls else n, "snapshot": bool(urls and urls[1])})
                    return cams

                def done(cams):
                    if Controller.instance:
                        import time
                        Controller.instance._names = [c["name"] for c in cams]
                        Controller.instance._names_at = time.time()
                    finish(req, {"result": True, "cameras": cams})

                def failed(err):
                    log("camera list failed:", err.getErrorMessage())
                    finish(req, {"result": False, "error": "camera source not reachable"})
                threads.deferToThread(collect).addCallbacks(done, failed)
                return server.NOT_DONE_YET
            elif action == "status":
                from .mqtt import node_id, node_name
                out = dict(ctl.status(), result=True, version=__version__, id=node_id(), name=node_name())
            elif action in ("show", "camalert"):
                sec = clamp_seconds(args.get("sec"), int(c.duration.value)) if args.get("sec") else None
                res = ctl.show(args.get("cam"), sec, args.get("mode"), args.get("priority"), source, args.get("label"))
                out = {"result": res in ("show", "extend", "wake"), "action": res, "cam": args.get("cam") or c.camera.value}
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
            _port = reactor.listenSSL(valid_port(c.http_port.value, 8099), server.Site(root), ctx)
            log("listening on port", valid_port(c.http_port.value, 8099), "(https)")
        else:
            _port = reactor.listenTCP(valid_port(c.http_port.value, 8099), server.Site(root))
            log("listening on port", valid_port(c.http_port.value, 8099))
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
