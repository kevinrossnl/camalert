"""#85: notify entity per player; notify.send_message shows a notification with a camera picture."""
import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

NOTIFY = "notify.living_room_notification"


async def send(hass, **data):
    await hass.services.async_call("notify", "send_message", dict({"entity_id": NOTIFY}, **data), blocking=True)


async def test_message_is_a_notification(hass, player, setup):
    await setup(hass, player)
    assert hass.states.get(NOTIFY).attributes["friendly_name"] == "Living room Notification"
    await send(hass, message="Parcel  delivered")
    assert player.ctl.calls[-1] == ("show", None, None, "notify", None, "ha", "Parcel delivered")


async def test_title_picks_the_camera(hass, player, setup):
    await setup(hass, player)
    await send(hass, message="Someone at the door", title="Front door")  # the camera's own name
    assert player.ctl.calls[-1][1:3] == ("front_door", None) and player.ctl.calls[-1][-1] == "Someone at the door"
    await send(hass, message="Motion", title="GARDEN")
    assert player.ctl.calls[-1][1] == "garden"


async def test_other_title_goes_before_the_message(hass, player, setup):
    await setup(hass, player)
    await send(hass, message="Washing machine is ready, empty it before it starts to smell", title="Laundry")
    call = player.ctl.calls[-1]
    assert call[1] is None and call[-1] == "Laundry: Washing machine is ready, empty"  # 40 characters, trimmed
    await send(hass, message="", title="Only a title")
    assert player.ctl.calls[-1][-1] == "Only a title"


async def test_errors_are_shown(hass, player, setup):
    await setup(hass, player)
    player.ctl.results["show"] = "error"
    with pytest.raises(HomeAssistantError, match="unknown camera"):
        await send(hass, message="x")
    player.status_override = 429
    with pytest.raises(HomeAssistantError, match="too many requests"):
        await send(hass, message="x")


async def test_no_notify_without_show(hass, player, setup):
    player.capabilities = ["cameras", "header_token", "hide", "post", "status"]
    entry = await setup(hass, player)
    ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
    assert not any(i.startswith("notify.") for i in ids)
