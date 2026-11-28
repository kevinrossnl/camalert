"""Browser players (#92 web player, #127 browser extension): the CamAlert API over Home Assistant's WebSocket.

A browser cannot be polled like the other players. It subscribes with ``camalert/browser/connect``; Home Assistant
sends the normal CamAlert API requests as events of that subscription and the browser answers with
``camalert/browser/reply``. :class:`BrowserApi` implements :class:`CamAlertApi` on top of it, so the coordinator,
entities, actions and blueprints work unchanged. The integration also serves the web player
(``/camalert_static/page/player.html``), the optional dashboard module, and a view that forwards a browser player's
picture requests to its go2rtc (local network only, the same rule as the webhook), so a browser needs neither CORS
nor plain HTTP to go2rtc.
"""
from __future__ import annotations

import asyncio
import ipaddress
import itertools
import logging
import os
import re
import socket
from urllib.parse import urlsplit

import voluptuous as vol

from .api import CamAlertApi, CamAlertError, CamAlertNotSupported, check_answer
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BROWSER = "browser"  # config entry data "type" of a browser player
CONF_BROWSER_ID = "browser_id"
CONF_TYPE = "type"
STATIC_URL = "/camalert_static"
WWW = os.path.join(os.path.dirname(__file__), "www")
TIMEOUT = 10  # seconds a browser has to answer a request
BROWSER_ID = re.compile(r"^[a-z0-9]{6,32}$")
# what the go2rtc view forwards (GET unless noted); everything else is refused
GO2RTC_PATHS = {"api/streams": "GET", "api/frame.jpeg": "GET", "api/stream.mjpeg": "GET", "api/webrtc": "POST"}
# #131: s<n>/<path> goes to the n-th go2rtc server of the player (s1 = "server", s2... = "more_servers" in its hello)
SERVER_PATH = re.compile(r"^s([2-9]|1[0-6])/(.+)$")
MAX_SERVERS = 16
FRAME_MAX = 8 * 1024 * 1024
LAN = tuple(ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "::1/128", "fe80::/10", "fc00::/7"))
LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal")


def is_browser(data) -> bool:
    return (data or {}).get(CONF_TYPE) == BROWSER


def _lan_ip(text) -> bool:
    try:
        a = ipaddress.ip_address(str(text).split("%", 1)[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return any(a.version == n.version and a in n for n in LAN)


async def lan_server(hass, server: str) -> str | None:
    """The go2rtc base URL when it is http(s) and in the local network, else None (resolves host names)."""
    p = urlsplit(server or "")
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        return None
    host = p.hostname
    if _lan_ip(host):
        return "%s://%s" % (p.scheme, p.netloc)
    if "." not in host or host.endswith(LOCAL_SUFFIXES):
        ok = True
    else:
        try:
            infos = await hass.async_add_executor_job(socket.getaddrinfo, host, None)
        except OSError:
            return None
        ok = bool(infos) and all(_lan_ip(i[4][0]) for i in infos)
    return "%s://%s" % (p.scheme, p.netloc) if ok else None


def server_of(hello: dict, n) -> str:
    """The go2rtc address a browser player asked for: "server" (s1), or n >= 2 for the (n-1)-th entry of its
    "more_servers" (#131: the player sends them in the order of their ids, comma separated)."""
    if n == "server":
        return hello.get("server", "")
    more = [x.strip() for x in (hello.get("more_servers") or "").split(",") if x.strip()][:MAX_SERVERS - 1]
    return more[n - 2] if 2 <= n <= len(more) + 1 else ""


class _Conn:
    __slots__ = ("connection", "msg_id", "hello")

    def __init__(self, connection, msg_id, hello):
        self.connection, self.msg_id, self.hello = connection, msg_id, hello


class BrowserHub:
    """The browsers connected now, their pending requests, and discovery of new ones."""

    def __init__(self, hass):
        self.hass = hass
        self.conns: dict[str, _Conn] = {}
        self.pending: dict[int, tuple[asyncio.Future, object]] = {}
        self.ids = itertools.count(1)
        self.discovered: set[str] = set()

    def connected(self, browser_id: str) -> bool:
        return browser_id in self.conns

    def hello(self, browser_id: str) -> dict:
        c = self.conns.get(browser_id)
        return dict(c.hello) if c else {}

    def connect(self, connection, msg_id: int, hello: dict):
        bid = hello[CONF_BROWSER_ID]
        old = self.conns.get(bid)
        if old is not None and old.connection is not connection:
            _LOGGER.debug("browser %s connected again: the newer connection wins", bid)
        self.conns[bid] = _Conn(connection, msg_id, hello)

        def unsub():
            c = self.conns.get(bid)
            if c is not None and c.connection is connection and c.msg_id == msg_id:
                del self.conns[bid]
            for rid, (fut, conn) in list(self.pending.items()):
                if conn is connection and not fut.done():
                    fut.set_exception(CamAlertError("browser player disconnected"))
                    del self.pending[rid]
        return unsub

    def discover(self, hello: dict) -> None:
        """A browser that is not a player yet: offer it once per Home Assistant run (discovery flow)."""
        bid = hello[CONF_BROWSER_ID]
        if bid in self.discovered:
            return
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.unique_id == bid:
                return
        self.discovered.add(bid)
        self.hass.async_create_task(self.hass.config_entries.flow.async_init(
            DOMAIN, context={"source": BROWSER}, data={CONF_BROWSER_ID: bid, "name": hello.get("name") or ""}))

    async def request(self, browser_id: str, action: str, params: dict, timeout: float = TIMEOUT):
        from homeassistant.components import websocket_api
        c = self.conns.get(browser_id)
        if c is None:
            raise CamAlertError("browser player not connected")
        rid = next(self.ids)
        fut = self.hass.loop.create_future()
        self.pending[rid] = (fut, c.connection)
        c.connection.send_message(websocket_api.event_message(c.msg_id, {
            "type": "request", "id": rid, "action": action,
            "params": {k: v for k, v in (params or {}).items() if v not in (None, "")}}))
        try:
            async with asyncio.timeout(timeout):
                return await fut
        except TimeoutError as err:
            raise CamAlertError("browser player did not answer") from err
        finally:
            self.pending.pop(rid, None)

    def reply(self, connection, request_id: int, code: int, body) -> bool:
        item = self.pending.get(request_id)
        if item is None or item[1] is not connection:  # only the connection that got the request may answer
            return False
        fut = item[0]
        if not fut.done():
            fut.set_result((int(code), body))
        return True


def hub(hass) -> BrowserHub:
    data = hass.data.setdefault(DOMAIN, {})
    if "browser_hub" not in data:
        data["browser_hub"] = BrowserHub(hass)
    return data["browser_hub"]


class BrowserApi(CamAlertApi):
    """CamAlertApi of a browser player: the same calls, delivered over the WebSocket subscription."""

    NOT_HERE = ("webhook", "update", "ptz", "tour")  # what a browser player does not have

    def __init__(self, hass, browser_id: str):
        super().__init__(None, "browser", 0)
        self.hass = hass
        self.browser_id = browser_id

    @property
    def configuration_url(self):
        return None

    async def _get(self, action: str, params: dict | None = None):
        if action in self.NOT_HERE:
            raise CamAlertNotSupported("not supported by this player (%s)" % action)
        code, body = await hub(self.hass).request(self.browser_id, action, params or {})
        return check_answer(code, body)


# --- WebSocket commands -----------------------------------------------------------------------------------------------
def _ws_commands():
    from homeassistant.components import websocket_api

    @websocket_api.websocket_command({
        vol.Required("type"): "camalert/browser/connect",
        vol.Required(CONF_BROWSER_ID): vol.Match(BROWSER_ID),
        vol.Optional("name", default=""): vol.All(str, vol.Length(max=64)),
        vol.Optional("version", default=""): vol.All(str, vol.Length(max=32)),
        vol.Optional("server", default=""): vol.All(str, vol.Length(max=256)),
        vol.Optional("more_servers", default=""): vol.All(str, vol.Length(max=4096)),
    })
    @websocket_api.callback
    def ws_connect(hass, connection, msg):
        hello = {k: msg[k] for k in (CONF_BROWSER_ID, "name", "version", "server", "more_servers")}
        connection.subscriptions[msg["id"]] = hub(hass).connect(connection, msg["id"], hello)
        connection.send_result(msg["id"])
        hub(hass).discover(hello)
        for entry in hass.config_entries.async_entries(DOMAIN):  # a known player came back: refresh it now
            coordinator = getattr(entry, "runtime_data", None)
            if entry.unique_id == hello[CONF_BROWSER_ID] and coordinator is not None:
                hass.async_create_task(coordinator.async_request_refresh())

    @websocket_api.websocket_command({
        vol.Required("type"): "camalert/browser/reply",
        vol.Required("request_id"): int,
        vol.Required("code"): int,
        vol.Optional("body", default=None): vol.Any(dict, None),
    })
    @websocket_api.callback
    def ws_reply(hass, connection, msg):
        if hub(hass).reply(connection, msg["request_id"], msg["code"], msg["body"]):
            connection.send_result(msg["id"])
        else:
            connection.send_error(msg["id"], "not_found", "no such request")

    return ws_connect, ws_reply


# --- the go2rtc view --------------------------------------------------------------------------------------------------
def _view_class():
    from aiohttp import web
    from homeassistant.components.http import HomeAssistantView
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    class Go2rtcView(HomeAssistantView):
        """go2rtc for a browser player: /api/camalert/go2rtc/<browser id>/<api/streams|frame.jpeg|...>."""

        url = "/api/camalert/go2rtc/{browser_id}/{path:.+}"
        name = "api:camalert:go2rtc"
        requires_auth = True

        async def _target(self, request, browser_id, path, method):
            hass = request.app["hass"]
            hello_key, m = "server", SERVER_PATH.match(path)
            if m:
                hello_key, path = int(m.group(1)), m.group(2)
            if GO2RTC_PATHS.get(path) != method:
                raise web.HTTPNotFound()
            known = any(e.unique_id == browser_id and is_browser(e.data)
                        for e in hass.config_entries.async_entries(DOMAIN))
            if not known:
                raise web.HTTPNotFound()
            base = await lan_server(hass, server_of(hub(hass).hello(browser_id), hello_key))
            if not base:
                raise web.HTTPForbidden(text="go2rtc address not set or not in the local network")
            return hass, "%s/%s" % (base, path)

        async def get(self, request, browser_id, path):
            hass, url = await self._target(request, browser_id, path, "GET")
            session = async_get_clientsession(hass, verify_ssl=False)
            import aiohttp
            try:
                if path == "api/stream.mjpeg":
                    upstream = await session.get(url, params=request.query, timeout=aiohttp.ClientTimeout(
                        total=None, sock_connect=10, sock_read=30))
                    resp = web.StreamResponse(status=upstream.status, headers={
                        "Content-Type": upstream.headers.get("Content-Type", "multipart/x-mixed-replace"),
                        "Cache-Control": "no-store"})
                    await resp.prepare(request)
                    try:
                        async for chunk in upstream.content.iter_chunked(65536):
                            await resp.write(chunk)
                    finally:
                        upstream.release()
                    return resp
                async with session.get(url, params=request.query, timeout=aiohttp.ClientTimeout(total=15)) as r:
                    body = await r.content.read(FRAME_MAX + 1)
                    if len(body) > FRAME_MAX:
                        raise web.HTTPBadGateway(text="answer too large")
                    return web.Response(status=r.status, body=body, headers={
                        "Content-Type": r.headers.get("Content-Type", "application/octet-stream"),
                        "Cache-Control": "no-store"})
            except (aiohttp.ClientError, TimeoutError) as err:
                raise web.HTTPBadGateway(text="go2rtc not reachable") from err

        async def post(self, request, browser_id, path):
            hass, url = await self._target(request, browser_id, path, "POST")
            body = await request.read()
            if len(body) > 65536:
                raise web.HTTPRequestEntityTooLarge(max_size=65536, actual_size=len(body))
            session = async_get_clientsession(hass, verify_ssl=False)
            import aiohttp
            try:
                async with session.post(url, params=request.query, data=body, timeout=aiohttp.ClientTimeout(total=15),
                                        headers={"Content-Type": request.headers.get("Content-Type",
                                                                                     "application/sdp")}) as r:
                    return web.Response(status=r.status, body=await r.read(), headers={
                        "Content-Type": r.headers.get("Content-Type", "application/sdp"), "Cache-Control": "no-store"})
            except (aiohttp.ClientError, TimeoutError) as err:
                raise web.HTTPBadGateway(text="go2rtc not reachable") from err

    return Go2rtcView


async def async_setup(hass) -> None:
    """WebSocket commands always; the static files, the go2rtc view and the dashboard module when http runs."""
    from homeassistant.components import websocket_api
    from .api import INTEGRATION_VERSION
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("browser_setup"):
        return
    data["browser_setup"] = True
    for command in _ws_commands():
        websocket_api.async_register_command(hass, command)
    if getattr(hass, "http", None) is None:
        return
    from homeassistant.components.http import StaticPathConfig
    await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, WWW, False)])
    hass.http.register_view(_view_class()())
    if "frontend" in hass.config.components:  # after_dependencies: loaded first wherever it is used
        from homeassistant.components.frontend import add_extra_js_url
        add_extra_js_url(hass, "%s/page/frontend.js?v=%s" % (STATIC_URL, INTEGRATION_VERSION))
