"""#84: window position and size of a player as selects (configuration), changed over /camalert/settings."""
import pytest
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

POSITION = "select.living_room_window_position"
SIZE = "select.living_room_window_size"


async def choose(hass, entity_id, option):
    await hass.services.async_call("select", "select_option", {"entity_id": entity_id, "option": option},
                                   blocking=True)


async def test_selects_show_and_change_the_window(hass, player, setup):
    from camalert_core import api as core_api
    from custom_components.camalert.const import WINDOW_SETTINGS
    assert {k: tuple(v) for k, v in WINDOW_SETTINGS.items()} == core_api.DISPLAY_SETTINGS  # same choices as the core
    player.settings.update(position="bottom_left", size="large")
    await setup(hass, player)
    pos, size = hass.states.get(POSITION), hass.states.get(SIZE)
    assert pos.state == "bottom_left" and size.state == "large"
    assert pos.attributes["options"] == ["top_right", "top_left", "bottom_right", "bottom_left"]
    assert pos.attributes["friendly_name"] == "Living room Window position"
    assert er.async_get(hass).async_get(SIZE).entity_category == EntityCategory.CONFIG
    await choose(hass, POSITION, "top_left")
    assert player.settings["position"] == "top_left"
    assert ("POST", "/camalert/settings") in player.actions()
    assert hass.states.get(POSITION).state == "top_left"  # refreshed from /status
    await choose(hass, SIZE, "small")
    assert player.settings["size"] == "small"


async def test_errors_are_shown(hass, player, setup):
    await setup(hass, player)
    player.status_override = 429
    with pytest.raises(HomeAssistantError, match="too many requests"):
        await choose(hass, SIZE, "small")


async def test_no_selects_on_a_player_without_settings(hass, player, setup):
    player.capabilities = ["cameras", "dnd", "header_token", "hide", "post", "show", "status"]
    entry = await setup(hass, player)
    ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
    assert not any(i.startswith("select.") for i in ids)
