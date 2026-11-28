"""#128: the buttons of the blueprints' phone notifications (mobile_app_notification_action), and #90: the
doorbell without an automation (entities chosen in the player's options)."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.camalert import player_device
from custom_components.camalert.phone import parse


def _shows(player):
    return [c for c in player.ctl.calls if c[0] == "show"]


def test_parse():
    assert parse("CAMALERT_SHOW|front_door|a,b") == ("SHOW", "front_door", ["a", "b"])
    assert parse("CAMALERT_DND|60|a") == ("DND", "60", ["a"])
    for bad in (None, 5, "OTHER_APP", "CAMALERT_SHOW|front_door", "CAMALERT_REBOOT|1|a", "CAMALERT_SHOW||a",
                "CAMALERT_DND|60|"):
        assert parse(bad) is None, bad


async def _press(hass, action):
    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()


async def test_show_on_tv_button(hass, player, setup):
    entry = await setup(hass, player)
    dev = player_device(hass, entry).id
    await _press(hass, "CAMALERT_SHOW|front_door|" + dev)
    assert _shows(player)[-1] == ("show", "front_door", None, None, "high", "ha", None)
    await _press(hass, "CAMALERT_SHOW|front_door,garden|" + dev)
    assert _shows(player)[-1][1] in ("front_door,garden", ["front_door", "garden"])


async def test_other_actions_and_unknown_devices_are_ignored(hass, player, setup):
    await setup(hass, player)
    before = list(player.ctl.calls)
    await _press(hass, "SOMETHING_ELSE")
    await _press(hass, "CAMALERT_SHOW|front_door|no-such-device")
    assert [c for c in player.ctl.calls if c not in before and c[0] in ("show", "dnd")] == []


async def test_dnd_button_for_an_hour(hass, player, setup):
    entry = await setup(hass, player)
    dev = player_device(hass, entry).id
    await _press(hass, "CAMALERT_DND|60|" + dev)
    assert ("dnd", True) in player.ctl.calls
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=59))
    await hass.async_block_till_done()
    assert ("dnd", False) not in player.ctl.calls
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=61))
    await hass.async_block_till_done()
    assert player.ctl.calls[-1] == ("dnd", False)


async def _with_doorbell(hass, entry, entities, camera=""):
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(flow["flow_id"], {
        "parent_device": "auto", "doorbell": entities, "doorbell_camera": camera})
    await hass.async_block_till_done()


async def test_doorbell_event_entity(hass, player, setup):
    entry = await setup(hass, player)
    hass.states.async_set("event.door", "unknown", {"event_type": None, "device_class": "doorbell"})
    await _with_doorbell(hass, entry, ["event.door"], "front_door")
    assert entry.options["doorbell"] == ["event.door"]
    clock = [1000.0]
    entry.runtime_data.doorbell.clock = lambda: clock[0]
    hass.states.async_set("event.door", "2026-11-28T10:00:00.000+00:00", {"event_type": "ring"})
    await hass.async_block_till_done()
    assert _shows(player)[-1] == ("show", "front_door", None, None, "high", "ha", "Doorbell")
    n = len(_shows(player))
    hass.states.async_set("event.door", "2026-11-28T10:00:05.000+00:00", {"event_type": "ring"})
    await hass.async_block_till_done()
    assert len(_shows(player)) == n  # cooldown: one window
    clock[0] += 20
    hass.states.async_set("event.door", "2026-11-28T10:00:25.000+00:00", {"event_type": "ring"})
    await hass.async_block_till_done()
    assert len(_shows(player)) == n + 1


async def test_doorbell_binary_sensor_and_not_on_restore(hass, player, setup):
    entry = await setup(hass, player)
    hass.states.async_set("binary_sensor.bell", "unavailable")
    await _with_doorbell(hass, entry, ["binary_sensor.bell"])
    hass.states.async_set("binary_sensor.bell", "on")  # back from unavailable: not a ring
    await hass.async_block_till_done()
    assert _shows(player) == []
    hass.states.async_set("binary_sensor.bell", "off")
    hass.states.async_set("binary_sensor.bell", "on")
    await hass.async_block_till_done()
    assert _shows(player)[-1][4:] == ("high", "ha", "Doorbell")


async def test_doorbell_other_event_types_and_cleared(hass, player, setup):
    entry = await setup(hass, player)
    hass.states.async_set("event.button", "unknown", {"event_type": None})
    await _with_doorbell(hass, entry, ["event.button"])
    hass.states.async_set("event.button", "2026-11-28T10:00:00.000+00:00", {"event_type": "long_press"})
    await hass.async_block_till_done()
    assert _shows(player) == []
    await _with_doorbell(hass, entry, [])  # cleared in the options: no longer watched
    assert entry.options["doorbell"] == []
    hass.states.async_set("event.button", "2026-11-28T10:01:00.000+00:00", {"event_type": "ring"})
    await hass.async_block_till_done()
    assert _shows(player) == []


async def test_doorbell_invalid_camera(hass, player, setup):
    entry = await setup(hass, player)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {
        "parent_device": "auto", "doorbell": [], "doorbell_camera": "front door; rm"})
    assert result["errors"] == {"doorbell_camera": "invalid_camera"}
