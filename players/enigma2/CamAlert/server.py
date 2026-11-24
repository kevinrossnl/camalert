# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""HTTP API of the receiver: a thin Twisted adapter around camalert_core.api (routes, validation, access rules
and answers are the same on every player, see docs/api.md)."""
import os
import subprocess
import time
from urllib.parse import parse_qs

from twisted.web import resource, server
from twisted.internet import reactor, threads
from Components.config import config, configfile

from . import __version__
from .display import Controller, all_camera_names, camera_urls, log
from .camalert_core import api
from .camalert_core.obs.camlog import LOG
from .camalert_core.urls import valid_port

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


class Backend(api.Backend):
    """What camalert_core.api needs from the Enigma2 plugin."""
    platform = "enigma2"
    version = __version__

    def settings(self):
        c = config.plugins.camalert
        return {"enabled": c.enabled.value, "allow": c.allow.value, "token": c.token.value,
                "duration": int(c.duration.value), "camera": c.camera.value, "dnd": bool(c.dnd.value),
                "ha_webhook": c.ha_webhook.value}

    def controller(self):
        return Controller.instance

    def node(self):
        from .mqtt import node_id, node_name
        return node_id(), node_name()

    def cameras(self):
        """Runs in a thread (go2rtc mode needs the network)."""
        cams = []
        for n in all_camera_names():
            urls = camera_urls(n)
            cams.append({"name": n, "title": urls[2] if urls else n, "snapshot": bool(urls and urls[1])})
        ctl = Controller.instance
        if ctl is not None:
            ctl._names, ctl._names_at = [c["name"] for c in cams], time.time()
        return cams

    def set_webhook(self, url):
        """Called from a thread (the webhook route resolves host names, #53): save on the main thread."""
        def save():
            c = config.plugins.camalert
            c.ha_webhook.value = url
            c.ha_webhook.save()
            configfile.save()
        reactor.callFromThread(save)

    def log_tail(self, lines):
        return LOG.tail(lines)

    def metrics(self):
        from .display import metrics
        return metrics()

    def status_extra(self):
        from . import mqtt
        return {"mqtt": mqtt.connected()}

    def log(self, message, level="normal"):
        log(message, level=level)


BACKEND = Backend()


def write(req, resp):
    """Writes an api.Response to a Twisted request; returns the body for render()."""
    req.setResponseCode(resp.code)
    req.setHeader(b"content-type", resp.content_type.encode())
    for k, v in resp.headers.items():
        req.setHeader(k.encode(), v.encode())
    return resp.payload()


def finish(req, resp):
    try:
        req.write(write(req, resp))
        req.finish()
    except Exception:  # client went away
        pass


def to_request(req):
    def text(v):
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else (v or "")
    method = text(req.method).upper()
    body = b""
    if method == "POST" and getattr(req, "content", None) is not None:
        req.content.seek(0)
        body = req.content.read(65536)
    # Twisted puts form bodies into req.args too: only the query string counts as args, the body is parsed by api
    query = text(req.uri).partition("?")[2]
    args = {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}
    return api.Request(method, text(req.path), args, req.getClientAddress().host,
                       text(req.getHeader(b"x-camalert-token")) or None, text(req.getHeader(b"user-agent")), body,
                       text(req.getHeader(b"content-type")))


class Api(resource.Resource):
    isLeaf = True

    def render(self, req):
        r = to_request(req)
        route = api.route_of(r.path)
        if route is not None and route.blocking:  # never block the GUI: answer from a thread
            threads.deferToThread(api.handle, BACKEND, r).addCallbacks(
                lambda resp: finish(req, resp),
                lambda err: finish(req, api.error(500, "internal error")))
            return server.NOT_DONE_YET
        return write(req, api.handle(BACKEND, r))


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
