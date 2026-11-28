# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""HTTP API: a thin http.server adapter around camalert_core.api (routes, validation, access rules and answers
are the same on every player, see docs/integrations/api.md)."""
import os
import ssl
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, kodiapi, sources
from .camalert_core import api, discovery
from .camalert_core.present import SETUP_RECEIVED
from .camalert_core.urls import valid_port
from .klogic import node_from_mac

_server = None
_thread = None
_https = False
# #121: announced as _camalert._tcp while the API is on (the core's mDNS responder; an avahi service file where
# avahi runs and /etc/avahi/services is writable, which LibreELEC's read-only /etc is not)
ADVERTISER = discovery.Advertiser(log=lambda m, level="normal": kodiapi.log(m, level))


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


class Backend(api.Backend):
    """What camalert_core.api needs from the Kodi add-on."""
    platform = "kodi"
    version = __version__

    def settings(self):
        return kodiapi.settings()

    def controller(self):
        from .controller import Controller
        return Controller.instance

    def node(self):
        return node_id(), node_name()

    def cameras(self):
        s = kodiapi.settings()
        cams = []
        for n in sources.all_camera_names(s):
            urls = sources.camera_urls(n, s)
            cams.append({"name": n, "title": urls[2] if urls else n, "snapshot": bool(urls and urls[1])})
        ctl = self.controller()
        if ctl is not None:
            ctl.names, ctl.names_at = [c["name"] for c in cams], time.time()
        return cams

    def set_webhook(self, url, secret=""):
        kodiapi.set_setting("ha_webhook", url)
        kodiapi.set_setting("ha_webhook_secret", secret)  # signs the colour keys (#82)

    def set_display(self, key, value):
        kodiapi.set_setting(key, value)  # window position or size from the API (#84)

    def set_setup(self, server, camera):
        """go2rtc address (and default camera) from Home Assistant (#122); the camera list follows at once."""
        kodiapi.set_setting("server", server)
        if camera:
            kodiapi.set_setting("camera", camera)
        ctl = self.controller()
        if ctl is not None:
            ctl.names_at = 0.0  # refresh the camera list at the next request
        kodiapi.notify("CamAlert", kodiapi.core_tr()(SETUP_RECEIVED), sound=False)

    def log_tail(self, lines):
        return kodiapi.camlog().tail(lines)

    def metrics(self):
        from .controller import metrics
        return metrics()

    def status_extra(self):
        from . import mqtt
        return {"mqtt": mqtt.connected()}

    def log(self, message, level="normal"):
        kodiapi.log(message, level)


BACKEND = Backend()
MAX_BODY = 65536


class Handler(BaseHTTPRequestHandler):
    server_version = "CamAlert"

    def answer(self, method):
        u = urlparse(self.path)
        args = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
        body = b""
        if method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(max(n, 0), MAX_BODY)) if n else b""
        req = api.Request(method, u.path, args, self.client_address[0], self.headers.get("X-CamAlert-Token"),
                          self.headers.get("User-Agent", ""), body, self.headers.get("Content-Type", ""))
        resp = api.handle(BACKEND, req)
        payload = resp.payload()
        try:
            self.send_response(resp.code)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(payload)))
            for k, v in resp.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            pass

    def do_GET(self):
        self.answer("GET")

    def do_POST(self):
        self.answer("POST")

    def do_PUT(self):  # answered by the core (405), like on Enigma2
        self.answer(self.command)

    do_DELETE = do_PATCH = do_PUT

    def log_message(self, fmt, *a):  # requests can contain the token: never log them
        pass


def announce(s=None):
    """#121: Home Assistant finds this Kodi while its API listens and is on; call after the settings changed."""
    s = s or kodiapi.settings()
    info = None
    if _server is not None and discovery.should_advertise(s):
        info = discovery.service_info(node_id(), node_name(s), Backend.platform, Backend.version, api.API_VERSION,
                                      valid_port(s["http_port"], 8099), _https)
    return ADVERTISER.update(info)


def start():
    global _server, _thread, _https
    _stop_server()
    _https = False
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
        _https = https
        _thread = threading.Thread(target=srv.serve_forever, name="camalert-http", daemon=True)
        _thread.start()
        kodiapi.log("listening on port %d%s" % (port, " (https)" if https else ""))
    except OSError as e:
        kodiapi.log("could not start HTTP API: %s" % e)
    announce(s)


def stop():
    """The API goes (Kodi stops the add-on): no longer announced on the network either."""
    ADVERTISER.stop()
    _stop_server()


def _stop_server():
    global _server, _thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
    _server = _thread = None
