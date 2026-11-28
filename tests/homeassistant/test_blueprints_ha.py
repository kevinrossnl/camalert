"""The blueprints in a real Home Assistant (#33, #45): each one passes Home Assistant's blueprint schema, makes a
valid automation with the frozen inputs, and that automation sends the expected action to the player."""
import json
import os
import shutil

import _paths
import pytest
from homeassistant.setup import async_setup_component

from conftest import setup_player
from custom_components.camalert import player_device
from test_blueprints import FROZEN


@pytest.fixture
async def blueprints(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "blueprints" / "automation" / "camalert"
    folder.mkdir(parents=True)
    for name in FROZEN:
        shutil.copy(os.path.join(_paths.BLUEPRINTS, name), folder / name)
    return folder


async def automations(hass, *items):
    config = [{"alias": alias, "use_blueprint": {"path": "camalert/" + name, "input": inputs}}
              for alias, name, inputs in items]
    assert await async_setup_component(hass, "automation", {"automation": config})
    await hass.async_block_till_done()
    for alias, _n, _i in items:  # an invalid blueprint or input leaves no (or an unavailable) automation
        st = hass.states.get("automation.%s" % alias)
        assert st is not None and st.state == "on", alias


async def test_blueprint_schema(hass, blueprints):
    from homeassistant.components.blueprint import models
    from homeassistant.util.yaml import load_yaml
    try:
        from homeassistant.components.automation.config import async_validate_config_item  # noqa: F401
        from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
    except ImportError:  # pragma: no cover - older layouts
        BLUEPRINT_SCHEMA = None
    for name, inputs in FROZEN.items():
        data = load_yaml(str(blueprints / name))
        kwargs = {"expected_domain": "automation"}
        if BLUEPRINT_SCHEMA is not None:
            kwargs["schema"] = BLUEPRINT_SCHEMA
        bp = models.Blueprint(data, **kwargs)
        assert list(bp.inputs) == [k for k, _d in inputs], name


async def test_doorbell(hass, player, blueprints):
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door"}))
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "front_door", 30, "photo", "high", "ha", None)


async def test_doorbell_announcement(hass, player, blueprints):
    """#89 (#12): the text goes to the players with camalert.show and to the speakers with tts.speak."""
    from pytest_homeassistant_custom_component.common import async_mock_service
    spoken = async_mock_service(hass, "tts", "speak")
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("tts.piper", "unknown")
    await automations(hass, ("door", "camalert_doorbell.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "announce": "Someone is at the door", "announce_speakers": ["media_player.kitchen"]}))
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "front_door", 30, "photo", "high", "ha", None)
    show = [json.loads(b) for m, p, h, b in player.requests if p == "/camalert/show"][-1]
    assert show["say"] == "Someone is at the door"
    assert len(spoken) == 1
    assert spoken[0].data["message"] == "Someone is at the door"
    assert spoken[0].data["media_player_entity_id"] == ["media_player.kitchen"]
    assert spoken[0].data["entity_id"] in (["tts.piper"], "tts.piper")


async def test_motion_with_label(hass, player, blueprints):
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("binary_sensor.front_door_person", "off")
    device = player_device(hass, entry).id
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion", "binary_sensor.front_door_person"], "players": [device],
        "when": "always"}), ("visitor", "camalert_motion.yaml", {
        "motion": ["binary_sensor.front_door_person"], "players": [device], "when": "always",
        "cameras": "front_door, garden", "label": "Visitor", "seconds": 60}))
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "garden", 30, "photo", "high", "ha", "Motion")
    hass.states.async_set("binary_sensor.front_door_person", "on")
    await hass.async_block_till_done()
    shows = sorted(c for c in player.ctl.calls if c[0] == "show")
    assert ("show", "front_door", 30, "photo", "high", "ha", "Person") in shows
    assert ("show", "front_door,garden", 60, "strip", "high", "ha", "Visitor") in shows


async def test_motion_until_it_ends(hass, player, blueprints):
    """#81: until_motion_ends shows with seconds 0 (the player keeps it, at most 600 s) and hides when every
    sensor is off again."""
    import asyncio

    async def settle():  # the automation waits (wait_template): async_block_till_done would wait for it
        for _ in range(50):
            await asyncio.sleep(0.01)

    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("binary_sensor.garden_person", "off")
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion", "binary_sensor.garden_person"],
        "players": [player_device(hass, entry).id], "when": "always", "cameras": "garden",
        "until_motion_ends": True}))
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await settle()
    assert player.ctl.calls[-1] == ("show", "garden", 600, "photo", "high", "ha", "Motion")
    hass.states.async_set("binary_sensor.garden_person", "on")
    hass.states.async_set("binary_sensor.garden_motion", "off")
    await settle()
    assert ("hide",) not in player.ctl.calls  # one sensor still on
    hass.states.async_set("binary_sensor.garden_person", "off")
    await settle()
    assert player.ctl.calls[-1] == ("hide",)


async def test_motion_only_when_armed(hass, player, blueprints):
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("alarm_control_panel.home", "disarmed")
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion"], "players": [player_device(hass, entry).id],
        "alarm_panel": "alarm_control_panel.home"}))
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert not [c for c in player.ctl.calls if c[0] == "show"]
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("alarm_control_panel.home", "armed_away")
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1][:2] == ("show", "garden")


async def test_alarm(hass, player, blueprints):
    entry = await setup_player(hass, player)
    hass.states.async_set("alarm_control_panel.home", "armed_away")
    await automations(hass, ("alarm", "camalert_alarm.yaml", {
        "alarm_panel": "alarm_control_panel.home", "players": [player_device(hass, entry).id],
        "camera": "garden"}))
    hass.states.async_set("alarm_control_panel.home", "triggered")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "garden", 300, "live", "alarm", "ha", "Alarm")


async def test_button(hass, player, blueprints):
    entry = await setup_player(hass, player)
    device = player_device(hass, entry).id
    done = []
    hass.bus.async_listen("gate_opened", lambda e: done.append(e.data))
    await automations(hass, ("gate", "camalert_button.yaml", {
        "players": [device], "camera": "front_door", "action": [{"event": "gate_opened"}]}))
    hass.bus.async_fire("camalert_button", {"device_id": device, "camera": "garden", "button": "green"})
    hass.bus.async_fire("camalert_button", {"device_id": device, "camera": "front_door", "button": "red"})
    await hass.async_block_till_done()
    assert done == []
    hass.bus.async_fire("camalert_button", {"device_id": device, "camera": "front_door", "button": "green"})
    await hass.async_block_till_done()
    assert len(done) == 1


def _fake_webos(hass):
    """A notify action as the LG webOS TV integration makes it, and a camera.snapshot that only records."""
    calls = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))
    hass.services.async_register("notify", "lg_webos_tv_living_room", record)
    hass.services.async_register("camera", "snapshot", record)
    return calls


async def test_doorbell_webos_with_snapshot(hass, player, blueprints):
    entry = await setup_player(hass, player)
    calls = _fake_webos(hass)
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("media_player.lg_tv", "on")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "label": "Doorbell", "webos_notify": "notify.lg_webos_tv_living_room",
        "snapshot_camera": "camera.front_door", "tv": "media_player.lg_tv"}))
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "front_door", 30, "photo", "high", "ha", "Doorbell")
    assert calls[0][:2] == ("camera", "snapshot")
    assert calls[0][2]["filename"] == "/media/camalert_webos.jpg"
    assert calls[1] == ("notify", "lg_webos_tv_living_room",
                        {"message": "Doorbell - front_door", "data": {"icon": "/media/camalert_webos.jpg"}})


async def test_doorbell_webos_text_only_and_tv_off(hass, player, blueprints):
    entry = await setup_player(hass, player)
    calls = _fake_webos(hass)
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("media_player.lg_tv", "off")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "webos_notify": "lg_webos_tv_living_room", "message": "Someone at the door", "tv": "media_player.lg_tv"}))
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1][:2] == ("show", "front_door")
    assert calls == []  # TV off: no notification, the players still show the camera
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("media_player.lg_tv", "on")
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert calls == [("notify", "lg_webos_tv_living_room", {"message": "Someone at the door"})]


def _fake_downloader(hass, result):
    """downloader.download_file as the Downloader integration does it: the event fires before the action returns
    (#74). result = "completed", "failed" or None (no event: the wait times out)."""
    calls = []

    async def download(call):
        calls.append(dict(call.data))
        if result:
            hass.bus.async_fire("downloader_download_%s" % result,
                                {"url": call.data["url"], "filename": call.data["filename"]})
    hass.services.async_register("downloader", "download_file", download)
    return calls


from datetime import timedelta  # noqa: E402

from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import async_fire_time_changed  # noqa: E402

SMALL = "http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640"


async def _ring_webos_url(hass, player, blueprints, result):
    entry = await setup_player(hass, player)
    calls = _fake_webos(hass)
    downloads = _fake_downloader(hass, result)
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "webos_notify": "notify.lg_webos_tv_living_room", "snapshot_camera": "camera.front_door",
        "snapshot_url": SMALL}))
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))  # the short delay before the download
    await hass.async_block_till_done()
    return calls, downloads


async def test_doorbell_webos_snapshot_url(hass, player, blueprints):
    """#74: the small picture is downloaded into the snapshot file and sent; the snapshot camera is not used."""
    calls, downloads = await _ring_webos_url(hass, player, blueprints, "completed")
    assert downloads == [{"url": SMALL, "filename": "camalert_webos.jpg", "overwrite": True}]
    assert calls == [("notify", "lg_webos_tv_living_room",
                      {"message": "Doorbell - front_door", "data": {"icon": "/media/camalert_webos.jpg"}})]


async def test_doorbell_webos_snapshot_url_failed(hass, player, blueprints):
    """#74: a failed download sends the notification as text only (never an old picture)."""
    calls, downloads = await _ring_webos_url(hass, player, blueprints, "failed")
    assert len(downloads) == 1
    assert calls == [("notify", "lg_webos_tv_living_room", {"message": "Doorbell - front_door"})]


async def test_doorbell_webos_snapshot_url_timeout(hass, player, blueprints):
    """#74: no answer from the Downloader within 15 s = text only."""
    calls, downloads = await _ring_webos_url(hass, player, blueprints, None)
    assert len(downloads) == 1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=16))
    await hass.async_block_till_done()
    assert calls == [("notify", "lg_webos_tv_living_room", {"message": "Doorbell - front_door"})]


async def _door_with_presence(hass, player, presence):
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "presence": presence}))


async def _ring(hass):
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()


def _shows(player):
    return [c for c in player.ctl.calls if c[0] == "show"]


async def test_presence_person(hass, player, blueprints):
    """#75: with persons, the camera only appears when one of them is home."""
    hass.states.async_set("person.one", "not_home")
    hass.states.async_set("person.two", "not_home")
    await _door_with_presence(hass, player, ["person.one", "person.two"])
    await _ring(hass)
    assert _shows(player) == []
    hass.states.async_set("person.two", "home")
    await _ring(hass)
    assert len(_shows(player)) == 1


async def test_presence_zone(hass, player, blueprints):
    """#75: a zone counts as 'someone home' when its state (persons in it) is above 0."""
    hass.states.async_set("zone.home", "0")
    await _door_with_presence(hass, player, ["zone.home"])
    await _ring(hass)
    assert _shows(player) == []
    hass.states.async_set("zone.home", "2")
    await _ring(hass)
    assert len(_shows(player)) == 1


async def test_presence_motion(hass, player, blueprints):
    entry = await setup_player(hass, player)
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("person.one", "not_home")
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion"], "players": [player_device(hass, entry).id], "when": "always",
        "presence": ["person.one"]}))
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert _shows(player) == []
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("person.one", "home")
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert len(_shows(player)) == 1


async def test_presence_webos_tv_part_too(hass, player, blueprints):
    """#75: nobody home = neither the players nor the LG TV notification."""
    entry = await setup_player(hass, player)
    calls = _fake_webos(hass)
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("person.one", "not_home")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "webos_notify": "notify.lg_webos_tv_living_room", "presence": ["person.one"]}))
    await _ring(hass)
    assert (_shows(player), calls) == ([], [])
    hass.states.async_set("person.one", "home")
    await _ring(hass)
    assert len(_shows(player)) == 1 and len(calls) == 1


def _fake_phone(hass):
    calls = []

    async def record(call):
        calls.append(dict(call.data))
    hass.services.async_register("notify", "mobile_app_phone", record)
    return calls


async def test_phone_with_camera_also_when_nobody_home(hass, player, blueprints):
    """#14: nobody home = no camera on the TV, but the phone gets the doorbell with the picture and a tap target."""
    entry = await setup_player(hass, player)
    phone = _fake_phone(hass)
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("person.one", "not_home")
    await automations(hass, ("door", "camalert_doorbell.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "label": "Doorbell", "presence": ["person.one"], "phone_notify": "mobile_app_phone",
        "phone_camera": "camera.front_door"}))
    await _ring(hass)
    assert _shows(player) == []
    dev = player_device(hass, entry).id
    assert phone == [{"title": "CamAlert", "message": "Doorbell - front_door", "data": {
        "tag": "camalert_front_door", "group": "camalert",
        "image": "/api/camera_proxy/camera.front_door", "entity_id": "camera.front_door",
        "clickAction": "entityId:camera.front_door", "url": "entityId:camera.front_door",
        "actions": [{"action": "CAMALERT_SHOW|front_door|" + dev, "title": "Show on TV"},
                    {"action": "CAMALERT_DND|60|" + dev, "title": "Do not disturb 1 h"}]}}]


async def test_phone_text_only_and_webos(hass, player, blueprints):
    entry = await setup_player(hass, player)
    phone = _fake_phone(hass)
    tv = _fake_webos(hass)
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "webos_notify": "notify.lg_webos_tv_living_room", "phone_notify": "notify.mobile_app_phone"}))
    await _ring(hass)
    assert len(_shows(player)) == 1 and len(tv) == 1
    assert len(phone) == 1 and phone[0]["message"] == "Doorbell - front_door"
    assert "image" not in phone[0]["data"] and len(phone[0]["data"]["actions"]) == 2


def _record_services(hass, *names):
    """Fake actions of other integrations (Cast, Notifications for Android TV, LG webOS, scenes): record only."""
    calls = []

    async def record(call):
        calls.append((call.domain + "." + call.service, dict(call.data)))
    for name in names:
        domain, service = name.split(".")
        hass.services.async_register(domain, service, record)
    return calls


async def test_screens_chromecast_live_and_back(hass, player, blueprints):
    """#16/#93: live view on a Chromecast with camera.play_stream, stopped again after the duration."""
    entry = await setup_player(hass, player)
    calls = _record_services(hass, "camera.play_stream", "media_player.media_stop")
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell_screens.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "seconds": 5, "cast_players": ["media_player.kitchen_tv"], "cast_camera": "camera.front_door"}))
    await _ring(hass)  # the automation runs to its end here, the 5 s delay included
    assert _shows(player)[-1] == ("show", "front_door", 5, "photo", "high", "ha", None)
    assert calls == [("camera.play_stream", {"entity_id": ["camera.front_door"],
                                             "media_player": ["media_player.kitchen_tv"], "format": "hls"}),
                     ("media_player.media_stop", {"entity_id": ["media_player.kitchen_tv"]})]


async def test_screens_android_tv_and_presence(hass, player, blueprints):
    """#16: the Android TV notification (with a picture the TV downloads); nobody home = nothing at all."""
    entry = await setup_player(hass, player)
    calls = _record_services(hass, "notify.android_tv_living_room")
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("person.one", "not_home")
    await automations(hass, ("door", "camalert_doorbell_screens.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "label": "Doorbell", "androidtv_notify": "android_tv_living_room", "androidtv_snapshot_url": SMALL,
        "presence": ["person.one"]}))
    await _ring(hass)
    assert (_shows(player), calls) == ([], [])
    hass.states.async_set("person.one", "home")
    await _ring(hass)
    assert len(_shows(player)) == 1
    assert calls == [("notify.android_tv_living_room", {"title": "CamAlert", "message": "Doorbell - front_door",
                                                        "data": {"duration": 30, "image": {"url": SMALL}}})]


async def test_screens_nothing_extra_by_default(hass, player, blueprints):
    entry = await setup_player(hass, player)
    calls = _record_services(hass, "camera.play_stream", "media_player.media_stop")
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell_screens.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door"}))
    await _ring(hass)
    assert len(_shows(player)) == 1 and calls == []


async def test_webos_live_view_and_back(hass, player, blueprints):
    """#94: the LG TV opens the stream page in its browser and returns to its scene after the duration."""
    entry = await setup_player(hass, player)
    calls = _record_services(hass, "scene.create", "webostv.command", "scene.turn_on",
                             "notify.lg_webos_tv_living_room")
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("media_player.lg_tv", "on")
    page = "http://192.168.1.10:1984/stream.html?src=front_door&mode=mse"
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "seconds": 5, "webos_notify": "notify.lg_webos_tv_living_room", "tv": "media_player.lg_tv",
        "webos_live_url": page}))
    await _ring(hass)  # runs to its end, the 5 s delay included
    names = [c[0] for c in calls]
    assert names == ["notify.lg_webos_tv_living_room", "scene.create", "webostv.command", "scene.turn_on"]
    assert calls[1][1] == {"scene_id": "camalert_webos_before", "snapshot_entities": ["media_player.lg_tv"]}
    assert calls[2][1] == {"entity_id": "media_player.lg_tv", "command": "system.launcher/open",
                           "payload": {"target": page}}
    assert calls[3][1] == {"entity_id": ["scene.camalert_webos_before"]}


async def test_webos_live_view_not_when_tv_off(hass, player, blueprints):
    entry = await setup_player(hass, player)
    calls = _record_services(hass, "scene.create", "webostv.command", "notify.lg_webos_tv_living_room")
    hass.states.async_set("binary_sensor.door", "off")
    hass.states.async_set("media_player.lg_tv", "off")
    await automations(hass, ("door", "camalert_doorbell_webos.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "webos_notify": "notify.lg_webos_tv_living_room", "tv": "media_player.lg_tv",
        "webos_live_url": "http://192.168.1.10:1984/stream.html?src=front_door"}))
    await _ring(hass)
    assert calls == [] and len(_shows(player)) == 1



def _fake_phones(hass, *names):
    """Notify actions of several Companion apps (#128): record (phone, data)."""
    calls = []
    for name in names:
        async def record(call, name=name):
            calls.append((name, dict(call.data)))
        hass.services.async_register("notify", name, record)
    return calls


async def test_phones_several_no_buttons_critical(hass, player, blueprints):
    """#128: comma-separated phones, buttons off, critical on (iOS critical sound, Android alarm channel)."""
    entry = await setup_player(hass, player)
    phones = _fake_phones(hass, "mobile_app_one", "mobile_app_two")
    hass.states.async_set("binary_sensor.door", "off")
    await automations(hass, ("door", "camalert_doorbell.yaml", {
        "doorbell": ["binary_sensor.door"], "players": [player_device(hass, entry).id], "camera": "front_door",
        "phone_notify": "mobile_app_one, notify.mobile_app_two", "phone_buttons": False, "phone_critical": True}))
    await _ring(hass)
    assert [p for p, _d in phones] == ["mobile_app_one", "mobile_app_two"]
    data = phones[0][1]["data"]
    assert "actions" not in data
    assert data["push"] == {"sound": {"name": "default", "critical": 1, "volume": 1.0}}
    assert data["ttl"] == 0 and data["priority"] == "high" and data["channel"] == "alarm_stream"


async def test_motion_phone_when_nobody_home(hass, player, blueprints):
    """#128: presence only gates the TV; the phone gets the motion (same 'when' rules) with the cameras."""
    entry = await setup_player(hass, player)
    phones = _fake_phones(hass, "mobile_app_one")
    hass.states.async_set("binary_sensor.garden_motion", "off")
    hass.states.async_set("person.one", "not_home")
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion"], "players": [player_device(hass, entry).id],
        "when": "always", "presence": ["person.one"], "phone_notify": "mobile_app_one"}))
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert _shows(player) == []
    assert len(phones) == 1 and phones[0][1]["message"] == "Motion - garden"
    assert phones[0][1]["data"]["actions"][0]["action"].startswith("CAMALERT_SHOW|garden|")


async def test_motion_when_rule_also_for_the_phone(hass, player, blueprints):
    entry = await setup_player(hass, player)
    phones = _fake_phones(hass, "mobile_app_one")
    hass.states.async_set("binary_sensor.garden_motion", "off")
    await automations(hass, ("motion", "camalert_motion.yaml", {
        "motion": ["binary_sensor.garden_motion"], "players": [player_device(hass, entry).id],
        "when": "armed", "phone_notify": "mobile_app_one"}))  # no alarm panel: never armed
    hass.states.async_set("binary_sensor.garden_motion", "on")
    await hass.async_block_till_done()
    assert phones == [] and _shows(player) == []


async def test_alarm_phone_is_critical_by_default(hass, player, blueprints):
    entry = await setup_player(hass, player)
    phones = _fake_phones(hass, "mobile_app_one")
    hass.states.async_set("alarm_control_panel.home", "armed_away")
    await automations(hass, ("alarm", "camalert_alarm.yaml", {
        "alarm_panel": "alarm_control_panel.home", "players": [player_device(hass, entry).id],
        "camera": "garden", "phone_notify": "mobile_app_one", "phone_camera": "camera.garden"}))
    hass.states.async_set("alarm_control_panel.home", "triggered")
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("show", "garden", 300, "live", "alarm", "ha", "Alarm")
    assert phones[0][1]["message"] == "Alarm - garden"
    data = phones[0][1]["data"]
    assert data["push"]["sound"]["critical"] == 1 and data["image"] == "/api/camera_proxy/camera.garden"
