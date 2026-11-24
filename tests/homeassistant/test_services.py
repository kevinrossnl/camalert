"""Actions show / mosaic / hide / ptz: schema, targets, the exact request on the player, errors raise (#33, #4)."""
import json

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component

from conftest import DOMAIN, setup_player
from custom_components.camalert import player_device


def last(player, path):
    for m, p, h, b in reversed(player.requests):
        if p == path:
            return m, (json.loads(b) if b else {}), h
    raise AssertionError("no request to %s" % path)


async def call(hass, service, data=None, **target):
    await hass.services.async_call(DOMAIN, service, dict(data or {}), blocking=True, target=target or None)


async def test_show_sends_exactly_this(hass, player):
    player.settings["token"] = "secret"
    entry = await setup_player(hass, player)
    await call(hass, "show", {"camera": ["garden", "front_door"], "seconds": 20, "priority": "high", "label": "Person"},
               device_id=player_device(hass, entry).id)
    method, body, headers = last(player, "/camalert/show")
    assert (method, body) == ("POST", {"cam": "garden,front_door", "sec": 20, "mode": "strip", "priority": "high",
                                       "label": "Person"})
    assert headers["X-CamAlert-Token"] == "secret"
    assert player.ctl.calls[-1] == ("show", "garden,front_door", 20, "strip", "high", "ha", "Person")


async def test_mosaic_hide_ptz(hass, player):
    await setup_player(hass, player)
    await call(hass, "mosaic", {"cameras": "front_door, garden", "seconds": 60})
    assert last(player, "/camalert/mosaic")[:2] == ("POST", {"cam": "front_door, garden", "sec": 60})
    await call(hass, "hide")
    await call(hass, "ptz", {"camera": "garden", "move": "zoom_in"})
    assert last(player, "/camalert/ptz")[:2] == ("POST", {"cam": "garden", "move": "zoom_in"})
    assert player.ctl.calls[-3:] == [("mosaic", "front_door,garden", 60), ("hide",), ("ptz", "zoom_in", "garden")]


async def test_without_target_every_player(hass, player, kodi):
    await setup_player(hass, player)
    await setup_player(hass, kodi)
    await call(hass, "show", {"camera": "garden"})
    assert player.ctl.calls[-1][:2] == ("show", "garden") and kodi.ctl.calls[-1][:2] == ("show", "garden")


async def test_target_selects_one_player(hass, player, kodi):
    await setup_player(hass, player)
    k = await setup_player(hass, kodi)
    await call(hass, "hide", device_id=player_device(hass, k).id)
    assert kodi.ctl.calls == [("hide",)] and player.ctl.calls == []


@pytest.mark.parametrize("data", [{"seconds": 2}, {"seconds": 301}, {"mode": "corner"}, {"priority": "urgent"}])
async def test_show_schema(hass, player, data):
    await setup_player(hass, player)
    with pytest.raises(vol.Invalid):
        await call(hass, "show", data)
    assert player.actions() == [("POST", "/camalert/webhook")]


async def test_ptz_schema(hass, player):
    await setup_player(hass, player)
    with pytest.raises(vol.Invalid):
        await call(hass, "ptz", {"camera": "garden", "move": "spin"})
    with pytest.raises(vol.Invalid):
        await call(hass, "ptz", {"move": "up"})


async def test_unknown_camera_raises(hass, player):
    player.ctl.results["show"] = "error"
    await setup_player(hass, player)
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "show", {"camera": "nowhere"})
    assert err.value.translation_key == "unknown_camera"
    assert err.value.translation_placeholders == {"name": "Living room"}


async def test_invalid_camera_name_raises(hass, player):
    await setup_player(hass, player)
    with pytest.raises(HomeAssistantError, match="invalid camera name") as err:
        await call(hass, "show", {"camera": "../etc"})
    assert err.value.translation_key == "request_failed"


async def test_refused_request_raises(hass, player):
    await setup_player(hass, player)
    player.status_override = 403
    with pytest.raises(HomeAssistantError, match="forbidden"):
        await call(hass, "hide")


async def test_timeout_raises(hass, player):
    await setup_player(hass, player)
    player.delay = 2
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "hide")
    assert err.value.translation_key == "request_failed"
    player.delay = 0


async def test_missing_capability_raises(hass, player):
    player.capabilities = ["cameras", "header_token", "hide", "post", "show", "status"]
    await setup_player(hass, player)
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "ptz", {"camera": "garden", "move": "up"})
    assert err.value.translation_key == "not_supported"
    assert err.value.translation_placeholders == {"name": "Living room", "action": "ptz"}
    assert not any(p == "/camalert/ptz" for _m, p, _h, _b in player.requests)


async def test_several_players_fail_together(hass, player, kodi):
    await setup_player(hass, player)
    await setup_player(hass, kodi)
    player.status_override = kodi.status_override = 403
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "hide")
    assert err.value.translation_key == "several_failed"
    assert "Living room" in str(err.value) and "Bedroom" in str(err.value)


async def test_one_player_fails_the_other_still_shows(hass, player, kodi):
    await setup_player(hass, player)
    await setup_player(hass, kodi)
    player.status_override = 429
    with pytest.raises(HomeAssistantError, match="Living room: too many requests"):
        await call(hass, "show", {"camera": "garden"})
    assert kodi.ctl.calls[-1][:2] == ("show", "garden")


async def test_player_not_loaded(hass, player):
    await player.stop()
    await setup_player(hass, player)
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "hide")
    assert err.value.translation_key == "not_loaded"


async def test_no_player(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(HomeAssistantError) as err:
        await call(hass, "hide")
    assert err.value.translation_key == "no_player"
