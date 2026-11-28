"""Browser players (#92 web player, #127 extension): the CamAlert API over Home Assistant's WebSocket, discovery,
BrowserApi, the go2rtc view (local network only) and the served web player."""
import asyncio
from unittest.mock import patch

from aiohttp import web
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import DOMAIN

BID = "webtest0000001"


class FakeBrowser:
    """A browser player on a Home Assistant WebSocket test client: answers the requests like the JS core."""

    def __init__(self, ws, bid=BID, name="Wall tablet", server="http://127.0.0.1:1984", more=None):
        self.ws, self.bid, self.name, self.server, self.more = ws, bid, name, server, more
        self.requests = []
        self.screen = "none"
        self.task = None
        self.next = 100
        self.answer = None  # override: f(action, params) -> (code, body) or None

    async def connect(self):
        hello = {"id": 1, "type": "camalert/browser/connect", "browser_id": self.bid, "name": self.name,
                 "version": "1.3.1", "server": self.server}
        if self.more is not None:
            hello["more_servers"] = self.more
        await self.ws.send_json(hello)
        msg = await self.ws.receive_json()
        assert msg["success"], msg
        self.task = asyncio.create_task(self._loop())
        return self

    def _default(self, action, params):
        if action == "status":
            return 200, {"result": True, "version": "1.3.1", "id": self.bid, "name": self.name, "platform": "browser",
                         "api_version": 1, "capabilities": ["cameras", "dnd", "events", "hide", "hold", "log", "mosaic",
                                                            "screen", "settings", "setup", "show", "status", "test"],
                         "min_ha_version": "1.0.0", "window": None, "live": None, "paused": False, "dnd": False,
                         "mqtt": False, "screen": self.screen, "configured": True, "position": "top_right",
                         "size": "medium"}
        if action == "cameras":
            return 200, {"result": True, "cameras": [{"name": "front_door", "title": "Front door", "snapshot": True}]}
        if action == "show":
            self.screen = "photo"
            return 200, {"result": True, "action": "show", "cam": params.get("cam", "front_door")}
        if action == "hide":
            self.screen = "none"
            return 200, {"result": True, "action": "hide"}
        if action in ("events", "log"):
            return 200, {"result": True, "events": [], "lines": []}
        if action == "settings":
            return 200, {"result": True, "position": "top_right", "size": "medium"}
        return 404, {"result": False, "error": "unknown action"}

    async def _loop(self):
        while True:
            msg = await self.ws.receive_json()
            if msg.get("type") != "event" or msg["event"].get("type") != "request":
                continue
            r = msg["event"]
            self.requests.append((r["action"], r["params"]))
            out = (self.answer and self.answer(r["action"], r["params"])) or self._default(r["action"], r["params"])
            if out == "silent":
                continue
            self.next += 1
            await self.ws.send_json({"id": self.next, "type": "camalert/browser/reply", "request_id": r["id"],
                                     "code": out[0], "body": out[1]})

    async def close(self):
        if self.task:
            self.task.cancel()
        await self.ws.close()


async def _ha(hass):
    assert await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


def browser_entry(bid=BID, title="Wall tablet"):
    return MockConfigEntry(domain=DOMAIN, title=title, unique_id=bid, data={"type": "browser", "browser_id": bid})


async def test_a_new_browser_is_discovered_and_added(hass, hass_ws_client):
    await _ha(hass)
    b = await FakeBrowser(await hass_ws_client(hass)).connect()
    await hass.async_block_till_done()
    flows = [f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN]
    assert len(flows) == 1 and flows[0]["context"]["source"] == "browser"
    assert flows[0]["context"]["title_placeholders"] == {"name": "Wall tablet"}
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"type": "browser", "browser_id": BID}
    assert result["title"] == "Wall tablet"
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.runtime_data.api.model == "Web browser"
    assert entry.runtime_data.data["platform"] == "browser"
    assert ("status", {}) in b.requests
    # the same browser again: no second offer
    b2 = await FakeBrowser(await hass_ws_client(hass)).connect()
    await hass.async_block_till_done()
    assert not [f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN]
    await b.close()
    await b2.close()


async def test_confirm_fails_while_the_browser_is_gone(hass, hass_ws_client):
    await _ha(hass)
    b = await FakeBrowser(await hass_ws_client(hass), bid="webgone0000001", name="").connect()
    await hass.async_block_till_done()
    flow = [f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN][0]
    assert flow["context"]["title_placeholders"]["name"].endswith("0001")
    await b.close()
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}


async def test_actions_reach_the_browser(hass, hass_ws_client):
    await _ha(hass)
    entry = browser_entry()
    entry.add_to_hass(hass)
    b = await FakeBrowser(await hass_ws_client(hass)).connect()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["screen"] == "none"
    await hass.services.async_call(DOMAIN, "show", {"camera": "front_door", "seconds": 20, "priority": "high"},
                                   blocking=True)
    action, params = [r for r in b.requests if r[0] == "show"][-1]
    assert params["cam"] == "front_door" and params["sec"] == 20 and params["priority"] == "high"
    await hass.services.async_call(DOMAIN, "hide", {}, blocking=True)
    assert b.requests[-1][0] == "hide" or ("hide", {}) in b.requests
    # what a browser player does not have is refused at once, without asking it
    api = entry.runtime_data.api
    from custom_components.camalert.api import CamAlertNotSupported
    for call in (api.webhook("http://192.168.1.20:8123/x"), api.update("9.9.9"), api.ptz("front_door", "up")):
        try:
            await call
        except CamAlertNotSupported:
            pass
        else:
            raise AssertionError("not refused")
    assert api.configuration_url is None
    await b.close()


async def test_answers_map_like_http_and_timeouts(hass, hass_ws_client, monkeypatch):
    from custom_components.camalert import browser
    from custom_components.camalert.api import CamAlertError
    monkeypatch.setattr(browser, "TIMEOUT", 0.3)
    await _ha(hass)
    b = await FakeBrowser(await hass_ws_client(hass)).connect()
    api = browser.BrowserApi(hass, BID)
    b.answer = lambda a, p: (400, {"result": False, "error": "invalid camera name"}) if a == "show" else None
    try:
        await api.show("bad name")
    except CamAlertError as err:
        assert "invalid camera name" in str(err)
    b.answer = lambda a, p: "silent" if a == "hide" else None
    try:
        await api.hide()
    except CamAlertError as err:
        assert "did not answer" in str(err)
    assert (await api.status())["platform"] == "browser"
    await b.close()
    await hass.async_block_till_done()
    try:
        await api.status()
    except CamAlertError as err:
        assert "not connected" in str(err) or "disconnected" in str(err)
    else:
        raise AssertionError("no error")


async def test_only_the_asked_connection_may_answer(hass, hass_ws_client):
    from custom_components.camalert import browser
    await _ha(hass)
    b = await FakeBrowser(await hass_ws_client(hass)).connect()
    b.answer = lambda a, p: "silent"
    other = await hass_ws_client(hass)
    task = asyncio.create_task(browser.BrowserApi(hass, BID).status())
    for _ in range(50):
        if b.requests:
            break
        await asyncio.sleep(0.02)
    await other.send_json({"id": 5, "type": "camalert/browser/reply", "request_id": 1, "code": 200, "body": {}})
    msg = await other.receive_json()
    assert msg["success"] is False and msg["error"]["code"] == "not_found"
    await b.close()
    try:
        await task
    except Exception:  # noqa: BLE001 - disconnected or timed out: either way not answered by the other client
        pass
    await other.close()


async def test_reconfigure_is_refused_for_a_browser(hass):
    await _ha(hass)
    entry = browser_entry()
    entry.add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "browser_player"


async def go2rtc_fake():
    seen = []

    async def frame(request):
        seen.append(("GET", request.path, request.query_string))
        return web.Response(body=b"\xff\xd8jpeg", content_type="image/jpeg")

    async def streams(request):
        seen.append(("GET", request.path, request.query_string))
        return web.json_response({"front_door": {"producers": []}})

    async def mjpeg(request):
        resp = web.StreamResponse(headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"})
        await resp.prepare(request)
        await resp.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\r\n")
        return resp

    async def webrtc(request):
        seen.append(("POST", request.path, await request.text()))
        return web.Response(text="v=0 answer", content_type="application/sdp")

    app = web.Application()
    app.router.add_get("/api/frame.jpeg", frame)
    app.router.add_get("/api/streams", streams)
    app.router.add_get("/api/stream.mjpeg", mjpeg)
    app.router.add_post("/api/webrtc", webrtc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, "http://127.0.0.1:%d" % port, seen


async def test_go2rtc_view_and_static_files(hass, hass_ws_client, hass_client, socket_enabled):
    await _ha(hass)
    runner, url, seen = await go2rtc_fake()
    entry = browser_entry()
    entry.add_to_hass(hass)
    b = await FakeBrowser(await hass_ws_client(hass), server=url).connect()
    client = await hass_client()
    r = await client.get("/api/camalert/go2rtc/%s/api/frame.jpeg?src=front_door&cache=10s" % BID)
    assert r.status == 200 and await r.read() == b"\xff\xd8jpeg"
    assert seen[-1] == ("GET", "/api/frame.jpeg", "src=front_door&cache=10s")
    r = await client.get("/api/camalert/go2rtc/%s/api/streams" % BID)
    assert (await r.json()) == {"front_door": {"producers": []}}
    r = await client.get("/api/camalert/go2rtc/%s/api/stream.mjpeg?src=front_door" % BID)
    assert r.status == 200 and (await r.content.read(9)) == b"--frame\r\n"
    r = await client.post("/api/camalert/go2rtc/%s/api/webrtc?src=front_door" % BID, data="v=0 offer",
                          headers={"Content-Type": "application/sdp"})
    assert r.status == 200 and await r.text() == "v=0 answer"
    # refused: other paths, wrong method, unknown browser, too large
    assert (await client.get("/api/camalert/go2rtc/%s/api/config" % BID)).status == 404
    assert (await client.get("/api/camalert/go2rtc/%s/api/webrtc" % BID)).status == 404
    assert (await client.get("/api/camalert/go2rtc/webnobody00001/api/streams")).status == 404
    big = await client.post("/api/camalert/go2rtc/%s/api/webrtc" % BID, data=b"x" * 70000)
    assert big.status == 413
    # the web player itself is served without login
    page = await client.get("/camalert_static/page/player.html")
    assert page.status == 200 and "CamAlert" in await page.text()
    await b.close()
    await runner.cleanup()
    # go2rtc gone: 502
    b2 = await FakeBrowser(await hass_ws_client(hass), server=url).connect()
    assert (await client.get("/api/camalert/go2rtc/%s/api/streams" % BID)).status == 502
    await b2.close()


async def test_go2rtc_view_with_several_servers(hass, hass_ws_client, hass_client, socket_enabled):
    """#131: /s<n>/ goes to the n-th go2rtc server of the player's hello (s1 = server, s2... = more_servers)."""
    await _ha(hass)
    main, url1, seen1 = await go2rtc_fake()
    other, url2, seen2 = await go2rtc_fake()
    browser_entry().add_to_hass(hass)
    b = await FakeBrowser(await hass_ws_client(hass), server=url1, more=url2 + ",http://203.0.113.5:1984").connect()
    client = await hass_client()
    assert (await client.get("/api/camalert/go2rtc/%s/api/frame.jpeg?src=a" % BID)).status == 200
    assert seen1[-1] == ("GET", "/api/frame.jpeg", "src=a") and not seen2
    assert (await client.get("/api/camalert/go2rtc/%s/s2/api/frame.jpeg?src=b" % BID)).status == 200
    assert seen2[-1] == ("GET", "/api/frame.jpeg", "src=b")
    r = await client.post("/api/camalert/go2rtc/%s/s2/api/webrtc?src=b" % BID, data="v=0 offer")
    assert r.status == 200 and seen2[-1] == ("POST", "/api/webrtc", "v=0 offer")
    # the third server is outside the local network; a fourth does not exist; s1/ is not a server path
    assert (await client.get("/api/camalert/go2rtc/%s/s3/api/streams" % BID)).status == 403
    assert (await client.get("/api/camalert/go2rtc/%s/s4/api/streams" % BID)).status == 403
    assert (await client.get("/api/camalert/go2rtc/%s/s1/api/streams" % BID)).status == 404
    assert (await client.get("/api/camalert/go2rtc/%s/s2/api/config" % BID)).status == 404
    await b.close()
    await main.cleanup()
    await other.cleanup()


def test_server_of():
    from custom_components.camalert.browser import server_of
    hello = {"server": "http://a:1984", "more_servers": "http://b:1984, http://c:1984"}
    assert server_of(hello, "server") == "http://a:1984"
    assert [server_of(hello, n) for n in (2, 3, 4)] == ["http://b:1984", "http://c:1984", ""]
    assert server_of({}, 2) == "" and server_of({"more_servers": ""}, "server") == ""


async def test_go2rtc_view_only_in_the_local_network_and_with_login(hass, hass_ws_client, hass_client,
                                                                     hass_client_no_auth):
    await _ha(hass)
    browser_entry().add_to_hass(hass)
    b = await FakeBrowser(await hass_ws_client(hass), server="http://203.0.113.5:1984").connect()
    client = await hass_client()
    assert (await client.get("/api/camalert/go2rtc/%s/api/streams" % BID)).status == 403
    anon = await hass_client_no_auth()
    assert (await anon.get("/api/camalert/go2rtc/%s/api/streams" % BID)).status == 401
    await b.close()


async def test_lan_server_rule(hass):
    from custom_components.camalert.browser import lan_server
    assert await lan_server(hass, "http://192.168.1.10:1984/x") == "http://192.168.1.10:1984"
    assert await lan_server(hass, "http://[fd00::1]:1984") == "http://[fd00::1]:1984"
    assert await lan_server(hass, "http://nas.local:1984") == "http://nas.local:1984"
    assert await lan_server(hass, "http://go2rtc:1984") == "http://go2rtc:1984"
    assert await lan_server(hass, "http://203.0.113.5:1984") is None
    assert await lan_server(hass, "ftp://192.168.1.10") is None
    assert await lan_server(hass, "http://u:p@192.168.1.10") is None
    assert await lan_server(hass, "") is None
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("192.168.1.30", 0))]):
        assert await lan_server(hass, "https://go2rtc.example.org") == "https://go2rtc.example.org"
    with patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("203.0.113.9", 0))]):
        assert await lan_server(hass, "https://go2rtc.example.org") is None
    with patch("socket.getaddrinfo", side_effect=OSError("no such host")):
        assert await lan_server(hass, "https://go2rtc.example.org") is None


async def test_setup_twice_and_without_http(hass):
    from custom_components.camalert import browser
    await browser.async_setup(hass)  # no http here: only the WebSocket commands
    await browser.async_setup(hass)  # once is enough
    assert hass.data[DOMAIN]["browser_setup"] is True
