"""A fake CamAlert player for the Home Assistant runtime tests (#33): a real aiohttp server on 127.0.0.1 that
answers through `camalert_core.api.handle()`, the one API implementation of every player. The HTTP contract
table (tests/contract/api_table.py) holds for it (test_contract_fake.py), so the integration is tested against
exactly what Enigma2 and Kodi answer.

    player = FakePlayer(platform="kodi"); await player.start(); ...; await player.stop()

Knobs: `settings` (token, allow, dnd, ...), `cameras`, `ctl` (RecordingController: calls, results, fail),
`status_override` (force an HTTP status, e.g. 429), `delay` (seconds before answering: timeouts), `legacy`
(a player from before API version 1: no api_version/capabilities in /status), `capabilities` (subset).
`caller_ip` is the address the core sees (a test header can override it per request, for the contract table).
"""
import asyncio
import ssl
import tempfile

import _paths
from aiohttp import web
from fakes import dns

dns.install()  # webhook host names under .example (contract table) without real DNS; before the core binds it
_paths.core()
from camalert_core import api  # noqa: E402
from fakes.controller import RecordingController  # noqa: E402

LAN = "192.168.1.5"
CALLER_HEADER = "X-Test-Caller"  # only this fake: which address the core sees as the caller
DEFAULTS = {"enabled": True, "allow": "lan", "token": "", "camera": "front_door", "duration": 30, "dnd": False,
            "ha_webhook": "", "position": "top_right", "size": "medium",
            "server": "http://192.168.1.10:1984", "source": "go2rtc"}  # set up; "" = a new player (#122)


class Backend(api.Backend):
    def __init__(self, player):
        self.player = player
        self.platform = player.platform
        self.version = "1.0.0"
        self.logged = []

    def settings(self):
        return self.player.settings

    def controller(self):
        return self.player.ctl

    def node(self):
        return self.player.node_id, self.player.name

    def cameras(self):
        if self.player.cameras is None:
            raise OSError("go2rtc down")
        return [{"name": n, "title": n.replace("_", " ").capitalize(), "snapshot": True}
                for n in self.player.cameras]

    def set_webhook(self, url):
        self.player.settings["ha_webhook"] = url
        self.player.webhooks.append(url)

    def set_display(self, key, value):
        self.player.settings[key] = value

    def set_setup(self, server, camera):
        self.player.settings["server"] = server
        if camera:
            self.player.settings["camera"] = camera

    def log_tail(self, lines):
        return ["CamAlert started", "show front_door token=[redacted]"][-lines:]

    def metrics(self):
        return "camalert_uptime_seconds 1\ncamalert_requests_total{key=\"show\"} 0\n"

    def status_extra(self):
        return {"mqtt": False}

    def log(self, message, level="normal"):
        self.logged.append((level, message))


class FakePlayer(object):
    def __init__(self, platform="enigma2", name="Living room", node_id="node-1", cameras=("front_door", "garden")):
        self.platform, self.name, self.node_id = platform, name, node_id
        self.settings = dict(DEFAULTS)
        self.cameras = list(cameras) if cameras is not None else None
        self.ctl = RecordingController()
        self.webhooks = []
        self.requests = []  # (method, path, headers, body text)
        self.status_override = None
        self.delay = 0.0
        self.legacy = False
        self.capabilities = None  # None = everything the core has
        self.min_ha_version = None  # None = the core's
        self.caller_ip = LAN
        self.backend = Backend(self)
        self._runner = self.port = None
        self.https = False

    # --- the server ---------------------------------------------------------------------------------------------
    async def start(self, https=False):
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        context = None
        if https:
            context = self._ssl_context()
            self.https = True
            # a client that refuses the certificate drops the handshake: expected here, not a test failure
            loop = asyncio.get_running_loop()
            self._handler = loop.get_exception_handler()

            def quiet(loop_, ctx):
                if isinstance(ctx.get("exception"), (ConnectionResetError, ssl.SSLError)):
                    return
                if self._handler:
                    self._handler(loop_, ctx)
                else:
                    loop_.default_exception_handler(ctx)
            loop.set_exception_handler(quiet)
        site = web.TCPSite(self._runner, "127.0.0.1", 0, ssl_context=context)
        await site.start()
        self.port = self._runner.addresses[0][1]
        return self

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self.https:
            asyncio.get_running_loop().set_exception_handler(self._handler)
            self.https = False

    @property
    def host(self):
        return "127.0.0.1"

    def reset(self):
        api.LIMIT.seen.clear()
        api.WARNED.clear()

    async def _handle(self, request):
        body = await request.read()
        self.requests.append((request.method, request.path, dict(request.headers), body.decode("utf-8", "replace")))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.status_override:
            return web.json_response({"result": False, "error": "forced"}, status=self.status_override)
        ip = request.headers.get(CALLER_HEADER) or self.caller_ip
        req = api.Request(request.method, request.path, dict(request.query), ip,
                          request.headers.get("X-CamAlert-Token"), request.headers.get("User-Agent", ""), body,
                          request.headers.get("Content-Type", ""))
        resp = api.handle(self.backend, req)
        data = resp.body
        if isinstance(data, dict) and request.path.endswith("/status"):
            data = self._status(data)
        if isinstance(data, dict):
            out = web.json_response(data, status=resp.code)
        else:
            out = web.Response(text=data, status=resp.code, content_type=resp.content_type.split(";")[0])
        for k, v in resp.headers.items():
            out.headers[k] = v
        return out

    def _status(self, data):
        data = dict(data)
        if self.legacy:  # a player from before API version 1
            for k in ("api_version", "capabilities", "platform", "min_ha_version"):
                data.pop(k, None)
            return data
        if self.capabilities is not None:
            data["capabilities"] = list(self.capabilities)
        if self.min_ha_version:
            data["min_ha_version"] = self.min_ha_version
        return data

    # --- what Home Assistant sent --------------------------------------------------------------------------------
    def actions(self):
        """[(method, path)] of every request except the polling reads."""
        return [(m, p) for m, p, _h, _b in self.requests if not p.endswith(("/status", "/cameras"))]

    def _ssl_context(self):
        """A self-signed certificate, like the one CamAlert makes for its own HTTPS."""
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "camalert")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(1).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        with tempfile.TemporaryDirectory() as d:
            with open(d + "/c.pem", "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            with open(d + "/k.pem", "wb") as f:
                f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                          serialization.NoEncryption()))
            ctx.load_cert_chain(d + "/c.pem", d + "/k.pem")
        return ctx
