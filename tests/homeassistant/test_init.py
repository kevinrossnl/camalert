"""Setup, unload, reload, coordinator and device info (#33, #44)."""
import logging

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from custom_components.camalert import player_device

from conftest import DOMAIN, setup_player
from fake_player import FakePlayer

SENSOR = "sensor.living_room_camera_on_screen"


async def test_setup_unload_reload(hass, player):
    entry = await setup_player(hass, player)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SENSOR).state == "none"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert "camalert_%s" % entry.entry_id not in hass.data.get("webhook", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(SENSOR).state == "none"


async def test_player_off_retries_later(hass, player):
    await player.stop()
    entry = await setup_player(hass, player)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_device_model_from_platform(hass, player, kodi):
    await setup_player(hass, player)
    await setup_player(hass, kodi)
    e2, k = (player_device(hass, e) for e in hass.config_entries.async_entries(DOMAIN))
    assert (e2.model, e2.manufacturer, e2.sw_version, e2.name) == ("Enigma2 receiver", "CamAlert", "1.0.0",
                                                                  "Living room")
    assert k.model == "Kodi"


async def test_android_tv_player(hass, socket_enabled):
    """#64: a player with platform androidtv (the Android TV / Fire TV app) is a normal CamAlert player."""
    atv = await FakePlayer(platform="androidtv", name="Fire TV", node_id="node-3").start()
    try:
        entry = await setup_player(hass, atv)
        assert entry.state is ConfigEntryState.LOADED
        dev = player_device(hass, entry)
        assert (dev.model, dev.manufacturer) == ("Android TV", "CamAlert")
        assert hass.states.get("sensor.fire_tv_camera_on_screen").state == "none"
        await hass.services.async_call(DOMAIN, "hide", {}, blocking=True)
        assert atv.actions()[-1] == ("POST", "/camalert/hide")
    finally:
        await atv.stop()


async def test_older_player_without_api_version(hass, player):
    player.legacy = True
    entry = await setup_player(hass, player)
    assert entry.state is ConfigEntryState.LOADED
    dev = player_device(hass, entry)
    assert dev.model == "Enigma2 receiver"
    await hass.services.async_call(DOMAIN, "hide", {}, blocking=True)
    assert player.actions()[-1] == ("GET", "/camalert/hide")  # older players only know GET


async def test_coordinator_unavailable_and_back(hass, player):
    entry = await setup_player(hass, player)
    coordinator = entry.runtime_data
    player.status_override = 500
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    assert hass.states.get(SENSOR).state == STATE_UNAVAILABLE
    player.status_override = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(SENSOR).state == "none"


async def test_camera_list_is_refreshed(hass, player):
    entry = await setup_player(hass, player)
    assert hass.states.get("button.living_room_show_driveway") is None
    player.cameras.append("driveway")
    entry.runtime_data._cameras_at = 0  # older than CAMERA_REFRESH_SECONDS
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("button.living_room_show_driveway") is not None


async def test_newer_player_warns_about_an_old_integration(hass, player, caplog):
    player.min_ha_version = "9.0.0"
    with caplog.at_level(logging.WARNING):
        await setup_player(hass, player)
    assert "needs CamAlert integration 9.0.0 or newer" in caplog.text


async def test_remove_entry_unhooks_the_player(hass, player):
    entry = await setup_player(hass, player)
    assert player.webhooks and player.webhooks[-1]
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert player.webhooks[-1] == ""
