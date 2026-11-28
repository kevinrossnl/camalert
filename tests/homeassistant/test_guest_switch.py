"""#11: guest mode of a player as a switch, switched over /camalert/settings."""
from homeassistant.helpers import entity_registry as er

GUEST = "switch.living_room_guest_mode"


async def switch(hass, service):
    await hass.services.async_call("switch", service, {"entity_id": GUEST}, blocking=True)


async def test_guest_switch(hass, player, setup):
    await setup(hass, player)
    state = hass.states.get(GUEST)
    assert state.state == "off"
    assert state.attributes["friendly_name"] == "Living room Guest mode"
    await switch(hass, "turn_on")
    assert player.settings["guest_mode"] is True
    assert ("POST", "/camalert/settings") in player.actions()
    assert hass.states.get(GUEST).state == "on"  # refreshed from /status
    await switch(hass, "turn_off")
    assert player.settings["guest_mode"] is False
    await hass.config_entries.async_entries("camalert")[0].runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(GUEST).state == "off"


async def test_no_guest_switch_on_an_older_player(hass, player, setup):
    player.capabilities = ["cameras", "dnd", "header_token", "hide", "post", "settings", "show", "status"]
    entry = await setup(hass, player)
    ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
    assert "switch.living_room_do_not_disturb" in ids
    assert GUEST not in ids
