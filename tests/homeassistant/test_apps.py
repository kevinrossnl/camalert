"""#95: a TV with an existing notification app (PiPup, TvOverlay, Notifications for Android TV / Fire TV) as a
light player: added from the menu, answered in Home Assistant, pictures and streams sent to the app."""
import json

import pytest
from aiohttp import web
from homeassistant import config_entries
from homeassistant.core import ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import DOMAIN

STREAMS = {
    "garden": {"producers": [{"url": "rtsp://192.168.1.11/stream1"}]},
    "front_door": {"producers": [{"url": "rtsp://192.168.1.12/stream1"}]},
    "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg"}]},  # helper stream (#117)
}


class FakeApp:
    """One aiohttp server that plays PiPup (/notify, /cancel), TvOverlay (/get, /notify) and go2rtc (/api/streams)."""

    def __init__(self):
        self.requests = []
        self.runner = self.port = None

    async def start(self):
        app = web.Application()

        async def record(request):
            body = await request.text()
            self.requests.append((request.method, request.path, json.loads(body) if body else None))
            if request.path == "/api/streams":
                return web.json_response(STREAMS)
            return web.json_response({"ok": True})

        app.router.add_route("*", "/{tail:.*}", record)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = self.runner.addresses[0][1]
        return self

    async def stop(self):
        await self.runner.cleanup()

    @property
    def server(self):
        return "http://127.0.0.1:%d" % self.port

    def sent(self, path="/notify"):
        return [b for m, p, b in self.requests if m == "POST" and p == path]


@pytest.fixture
async def app(socket_enabled):
    a = await FakeApp().start()
    yield a
    await a.stop()


async def add_app(hass, data, options=None):
    from custom_components.camalert.apps import node_id
    data = dict({"type": "app", "name": "TV app", "camera": ""}, **data)
    entry = MockConfigEntry(domain=DOMAIN, title="TV app", unique_id=node_id(data), data=data, options=options or {})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entity(hass, entry, key):
    unique = "%s_%s" % (entry.unique_id, key)
    for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if e.unique_id == unique:
            return e.entity_id
    return None


async def show(hass, **data):
    await hass.services.async_call(DOMAIN, "show", data, blocking=True)


async def test_add_from_the_menu(hass, app):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU and result["menu_options"] == ["player", "app"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "app"})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "app"
    form = {"app": "pipup", "name": "", "host": "127.0.0.1", "port": app.port, "go2rtc": "8.8.8.8:1984",
            "camera": ""}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form)
    assert result["errors"] == {"go2rtc": "go2rtc_not_local"}  # the TV fetches from it: local network only
    result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(form, go2rtc="127.0.0.1:%d" % app.port))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "PiPup (TV app) 127.0.0.1"
    assert result["data"]["go2rtc"] == app.server and result["data"]["port"] == app.port
    assert result["result"].unique_id == "app-pipup-127-0-0-1"
    await hass.async_block_till_done()
    assert result["result"].state is config_entries.ConfigEntryState.LOADED


async def test_unreachable_app_and_missing_fields(hass, app, unused_tcp_port):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "app"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "app": "tvoverlay", "host": "", "go2rtc": app.server, "camera": ""})
    assert result["errors"] == {"host": "host_required"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "app": "tvoverlay", "host": "127.0.0.1", "port": unused_tcp_port, "go2rtc": app.server, "camera": ""})
    assert result["errors"] == {"base": "app_unreachable"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "app": "nfandroidtv", "go2rtc": app.server, "camera": ""})
    assert result["errors"] == {"notify_entity": "entity_required"}


async def test_pipup_photo_window(hass, app):
    entry = await add_app(hass, {"app": "pipup", "host": "127.0.0.1", "port": app.port, "go2rtc": app.server})
    assert entry.state is config_entries.ConfigEntryState.LOADED
    api = entry.runtime_data.api
    assert "mosaic" not in api.capabilities and "webhook" not in api.capabilities and "show" in api.capabilities
    assert [c["name"] for c in entry.runtime_data.cameras] == ["front_door", "garden"]  # helper stream left out
    assert entity(hass, entry, "update") is None  # a notification app has no CamAlert to update
    assert entity(hass, entry, "mosaic") is None
    await show(hass, camera="garden", label="Motion")
    body = app.sent()[-1]
    assert body["media"] == {"image": {"uri": app.server + "/api/frame.jpeg?src=garden&width=480", "width": 480}}
    assert (body["title"], body["message"], body["duration"], body["position"]) == ("Garden", "Motion", 30, 0)
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.data["screen"] == "photo" and entry.runtime_data.data["window"] == "garden"
    await show(hass, mode="live", seconds=20)  # no camera: the first one; live = video
    body = app.sent()[-1]
    assert body["media"]["video"]["uri"] == "rtsp://127.0.0.1:8554/front_door" and body["duration"] == 20
    await hass.services.async_call(DOMAIN, "hide", {}, blocking=True)
    assert app.sent("/cancel")  # newer PiPup forks close the popup
    with pytest.raises(HomeAssistantError):
        await show(hass, camera="driveway")  # not a camera of this go2rtc
    with pytest.raises(HomeAssistantError, match="not supported"):
        await hass.services.async_call(DOMAIN, "mosaic", {}, blocking=True)


async def test_tvoverlay_live_and_hide(hass, app):
    entry = await add_app(hass, {"app": "tvoverlay", "host": "127.0.0.1", "port": app.port, "go2rtc": app.server,
                                 "camera": "garden"})
    assert ("GET", "/get", None) in app.requests  # reachable while the app runs
    await show(hass, mode="live", priority="high")
    body = app.sent()[-1]
    assert body["video"] == "rtsp://127.0.0.1:8554/garden" and "image" not in body
    assert (body["id"], body["corner"], body["seconds"]) == ("camalert", "top_end", 30)
    await hass.services.async_call(DOMAIN, "hide", {}, blocking=True)
    assert app.sent()[-1] == {"id": "camalert", "title": "", "message": "", "seconds": 1}
    assert entry.runtime_data.api.screen() is None


async def test_rules_dnd_hours_and_window_settings(hass, app, freezer):
    freezer.move_to("2026-11-28 12:00:00-08:00")  # tests run in US/Pacific
    entry = await add_app(hass, {"app": "pipup", "host": "127.0.0.1", "port": app.port, "go2rtc": app.server},
                          options={"active_from": "18:00:00", "active_until": "23:00:00"})
    await show(hass, camera="garden")
    assert app.sent() == []  # normal priority outside the active hours
    await show(hass, camera="garden", priority="high")
    assert len(app.sent()) == 1
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity(hass, entry, "dnd")}, blocking=True)
    assert entry.options["dnd"] is True and entry.options["active_from"] == "18:00:00"
    await show(hass, camera="garden", priority="high")  # Do not disturb blocks normal; high still comes through
    await show(hass, camera="garden", priority="alarm")
    assert len(app.sent()) == 3
    freezer.move_to("2026-11-28 19:00:00-08:00")
    await show(hass, camera="garden")
    assert len(app.sent()) == 3  # inside the hours, but Do not disturb
    for key, option in (("window_position", "bottom_left"), ("window_size", "large")):
        assert entity(hass, entry, key) is not None
        await hass.services.async_call("select", "select_option",
                                       {"entity_id": entity(hass, entry, key), "option": option}, blocking=True)
    await show(hass, camera="garden", priority="alarm")
    body = app.sent()[-1]
    assert body["position"] == 3 and body["media"]["image"]["width"] == 640


async def test_nfandroidtv_through_its_notify_entity(hass, app):
    calls = []

    async def send_message(call: ServiceCall):
        calls.append(dict(call.data))

    hass.services.async_register("nfandroidtv", "send_message", send_message)
    hass.states.async_set("notify.living_room_tv", "unknown")
    hass.states.async_set("camera.garden", "idle")
    entry = await add_app(hass, {"app": "nfandroidtv", "notify_entity": "notify.living_room_tv",
                                 "go2rtc": app.server})
    assert entry.state is config_entries.ConfigEntryState.LOADED
    await show(hass, camera="garden", mode="live")  # live is not possible here: a picture
    assert calls[-1] == {"entity_id": "notify.living_room_tv", "title": "Garden", "message": "Garden",
                         "duration": {"seconds": 30}, "position": "top-right",
                         "image": {"media_content_id": "media-source://camera/camera.garden",
                                   "media_content_type": "image/jpeg"}}
    await show(hass, camera="front_door", label="Doorbell")
    assert "image" not in calls[-1] and calls[-1]["message"] == "Doorbell"  # no camera.front_door: text only
    hass.states.async_set("notify.living_room_tv", "unavailable")
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data.last_update_success is False  # the TV is off: unavailable, like a player
