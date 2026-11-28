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


async def test_show_until_hide(hass, player):
    """#81: seconds 0 = until hide; the player keeps it at most 600 s. A player without the capability "hold"
    gets the longest fixed duration instead (it would read 0 as the shortest)."""
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "seconds": 0})
    assert last(player, "/camalert/show")[1]["sec"] == 0
    assert player.ctl.calls[-1][:3] == ("show", "garden", 600)
    with pytest.raises(vol.Invalid):
        await call(hass, "show", {"camera": "garden", "seconds": 3})


async def test_show_until_hide_on_an_older_player(hass, player):
    player.capabilities = ["cameras", "header_token", "hide", "post", "show", "status"]
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "seconds": 0})
    assert last(player, "/camalert/show")[1]["sec"] == 300


async def test_show_with_announcement(hass, player, monkeypatch):
    """#89: the text goes to a TTS engine once per call; every player gets the text and the WAV address."""
    made = []

    async def fake_say_url(hass_, text, engine=None, language=None):
        made.append((text, engine, language))
        return "http://192.168.1.2:8123/api/tts_proxy/abc.wav"
    monkeypatch.setattr("custom_components.camalert.async_say_url", fake_say_url)
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "priority": "high", "announce": "Someone is at the door",
                              "tts": "tts.piper", "language": "en"})
    body = last(player, "/camalert/show")[1]
    assert body["say"] == "Someone is at the door"
    assert body["say_url"] == "http://192.168.1.2:8123/api/tts_proxy/abc.wav"
    assert made == [("Someone is at the door", "tts.piper", "en")]
    await call(hass, "show", {"camera": "garden"})
    assert "say" not in last(player, "/camalert/show")[1] and len(made) == 1
    with pytest.raises(vol.Invalid):
        await call(hass, "show", {"camera": "garden", "announce": "x" * 301})


async def test_show_announcement_skipped_for_an_older_player(hass, player, monkeypatch):
    async def fake_say_url(*a, **kw):
        return "http://192.168.1.2:8123/api/tts_proxy/abc.wav"
    monkeypatch.setattr("custom_components.camalert.async_say_url", fake_say_url)
    player.capabilities = ["cameras", "header_token", "hide", "post", "show", "status"]
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "announce": "Hello"})
    body = last(player, "/camalert/show")[1]
    assert "say" not in body and "say_url" not in body


def test_announcement_address_rules():
    from custom_components.camalert import speech
    assert speech._plain_host("192.168.1.2") and speech._plain_host("homeassistant.local")
    assert speech._plain_host("homeassistant") and not speech._plain_host("ha.example.com")
    assert speech.OPTIONS == {"preferred_format": "wav"}


async def test_show_and_hide_a_window_with_an_id(hass, player):
    """#87: window_id goes to the player as id (show and hide); empty = the normal window."""
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "window_id": "doorbell"})
    assert last(player, "/camalert/show")[1]["id"] == "doorbell"
    assert player.ctl.calls[-1] == ("show", "garden", None, None, None, "ha", None, "doorbell")
    await call(hass, "hide", {"window_id": "doorbell"})
    assert last(player, "/camalert/hide")[1] == {"id": "doorbell"}
    assert player.ctl.calls[-1] == ("hide", "doorbell")
    await call(hass, "show", {"camera": "garden", "window_id": ""})
    assert "id" not in last(player, "/camalert/show")[1]
    with pytest.raises(vol.Invalid):
        await call(hass, "show", {"camera": "garden", "window_id": "a b"})


async def test_window_id_on_an_older_player(hass, player):
    """#87: a player without the capability "windows" gets the normal window and a normal hide."""
    player.capabilities = ["cameras", "header_token", "hide", "post", "show", "status"]
    await setup_player(hass, player)
    await call(hass, "show", {"camera": "garden", "window_id": "doorbell"})
    assert "id" not in last(player, "/camalert/show")[1]
    await call(hass, "hide", {"window_id": "doorbell"})
    assert player.ctl.calls[-1] == ("hide",)


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


async def test_target_entity_and_area_of_a_player(hass, player, kodi):
    """services.yaml filters the target on CamAlert entities (hassfest): an entity or area of one player works."""
    from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er
    await setup_player(hass, player)
    k = await setup_player(hass, kodi)
    device = player_device(hass, k)
    entity = next(e.entity_id for e in er.async_entries_for_device(er.async_get(hass), device.id))
    await call(hass, "hide", entity_id=entity)
    assert kodi.ctl.calls == [("hide",)] and player.ctl.calls == []
    area = ar.async_get(hass).async_create("Living room").id
    dr.async_get(hass).async_update_device(device.id, area_id=area)
    await call(hass, "hide", area_id=area)
    assert kodi.ctl.calls == [("hide",), ("hide",)] and player.ctl.calls == []


async def test_services_yaml_valid_for_home_assistant(hass, player):
    """The hassfest rules for targets, checked with Home Assistant's own selector schema, and the descriptions load."""
    import os
    import yaml
    from homeassistant.helpers import selector
    from homeassistant.helpers.service import async_get_all_descriptions
    import custom_components.camalert as integration
    services = yaml.safe_load(open(os.path.join(os.path.dirname(integration.__file__), "services.yaml")))
    for name, service in services.items():
        assert "device" not in service["target"], name  # hassfest: no device filter on target
        selector.TargetSelector.CONFIG_SCHEMA(service["target"])
        for field in service.get("fields", {}).values():
            selector.validate_selector(field["selector"])
    await setup_player(hass, player)
    # only CamAlert's actions: the notify (#85) and update (#83) actions pull in conversation (hassil), not
    # installed in these tests
    for domain in ("notify", "update"):
        for name in list(hass.services.async_services().get(domain, {})):
            hass.services.async_remove(domain, name)
    descriptions = (await async_get_all_descriptions(hass))[DOMAIN]
    assert sorted(descriptions) == ["hide", "mosaic", "ptz", "show"]
    assert descriptions["show"]["target"] == {"entity": [{"integration": DOMAIN}]}


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
