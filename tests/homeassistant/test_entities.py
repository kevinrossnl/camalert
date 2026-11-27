"""Entities: buttons, sensor, do-not-disturb switch, per capability (#33, #44)."""
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from conftest import setup_player

SENSOR = "sensor.living_room_camera_on_screen"
SWITCH = "switch.living_room_do_not_disturb"


def body(player, path):
    import json
    for m, p, h, b in reversed(player.requests):
        if p == path:
            return m, (json.loads(b) if b else {})
    return None


async def press(hass, entity_id):
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


async def test_entities_of_a_player(hass, player):
    await setup_player(hass, player)
    ids = sorted(e.entity_id for e in er.async_entries_for_config_entry(
        er.async_get(hass), hass.config_entries.async_entries("camalert")[0].entry_id))
    assert ids == ["button.living_room_hide_camera", "button.living_room_mosaic", "button.living_room_show_front_door",
                   "button.living_room_show_garden", "event.living_room_remote_button",
                   "notify.living_room_notification", SENSOR, SWITCH, "update.living_room_camalert"]
    assert hass.states.get("button.living_room_show_front_door").attributes["friendly_name"] == \
        "Living room Show Front door"
    for e in ids:  # icons come from icons.json, not from the entities
        assert "icon" not in hass.states.get(e).attributes, e


async def test_buttons_post_the_action(hass, player):
    player.settings["token"] = "secret"
    await setup_player(hass, player)
    await press(hass, "button.living_room_show_garden")
    assert body(player, "/camalert/show") == ("POST", {"cam": "garden"})
    await press(hass, "button.living_room_mosaic")
    await press(hass, "button.living_room_hide_camera")
    assert player.actions() == [("POST", "/camalert/webhook"), ("POST", "/camalert/show"), ("POST", "/camalert/mosaic"),
                                ("POST", "/camalert/hide")]
    assert player.ctl.calls[-3:] == [("show", "garden", None, None, None, "ha", None), ("mosaic", None, 60), ("hide",)]
    assert all(h.get("X-CamAlert-Token") == "secret" for _m, _p, h, _b in player.requests)


async def test_button_error_is_shown(hass, player):
    await setup_player(hass, player)
    player.status_override = 403
    with pytest.raises(HomeAssistantError) as err:
        await press(hass, "button.living_room_show_garden")
    assert err.value.translation_key == "request_failed"
    assert "forbidden" in str(err.value)


async def test_sensor_state_and_attributes(hass, player):
    entry = await setup_player(hass, player)
    st = hass.states.get(SENSOR)
    assert st.state == "none"  # translated in the UI ("Nothing")
    assert st.attributes["device_class"] == SensorDeviceClass.ENUM
    assert st.attributes["options"] == ["none", "front_door", "garden"]
    assert st.attributes["cameras"] == ["front_door", "garden"] and st.attributes["mode"] is None
    player.ctl.status = lambda: {"window": "garden", "live": None, "paused": False, "dnd": False}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    st = hass.states.get(SENSOR)
    assert (st.state, st.attributes["mode"]) == ("garden", "photo")
    player.ctl.status = lambda: {"window": None, "live": "mosaic_all", "paused": True, "dnd": False}
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    st = hass.states.get(SENSOR)
    assert (st.state, st.attributes["mode"], st.attributes["paused"]) == ("mosaic_all", "live", True)
    assert st.attributes["options"][-1] == "mosaic_all"  # a stream that is not in the camera list


async def test_dnd_switch(hass, player):
    await setup_player(hass, player)
    assert hass.states.get(SWITCH).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": SWITCH}, blocking=True)
    await hass.async_block_till_done()
    assert body(player, "/camalert/dnd") == ("POST", {"on": "1"})
    assert player.ctl.calls[-1] == ("dnd", True)
    await hass.config_entries.async_entries("camalert")[0].runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": SWITCH}, blocking=True)
    assert body(player, "/camalert/dnd") == ("POST", {"on": "0"})
    player.status_override = 429
    with pytest.raises(HomeAssistantError, match="too many requests"):
        await hass.services.async_call("switch", "turn_on", {"entity_id": SWITCH}, blocking=True)


async def test_entities_follow_capabilities(hass, player):
    player.capabilities = ["cameras", "header_token", "hide", "post", "show", "status"]
    entry = await setup_player(hass, player)
    ids = sorted(e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
    assert ids == ["button.living_room_hide_camera", "button.living_room_show_front_door",
                   "button.living_room_show_garden", "notify.living_room_notification", SENSOR,
                   "update.living_room_camalert"]
    assert player.webhooks == []  # no webhook capability: colour keys only via MQTT
