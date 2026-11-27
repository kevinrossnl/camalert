"""#86: the player's device hangs under the TV/receiver device (via_device): automatic by address, none, or chosen
in the options."""
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.camalert import player_device


def tv(hass, domain="enigma2", host="127.0.0.1", name="Living room TV"):
    """A device of another integration (only registered, never set up) with that address."""
    other = MockConfigEntry(domain=domain, data={"host": host})
    other.add_to_hass(hass)
    reg = dr.async_get(hass)
    device = reg.async_get_or_create(config_entry_id=other.entry_id, identifiers={(domain, "tv-%s" % name)}, name=name)
    # a second device of that entry that hangs under the first one: never the parent
    sub = reg.async_get_or_create(config_entry_id=other.entry_id, identifiers={(domain, "sub-%s" % name)}, name="Sub")
    reg.async_update_device(sub.id, via_device_id=device.id)
    return device


async def test_automatic_same_address(hass, player, setup):
    device = tv(hass)
    entry = await setup(hass, player)
    assert player_device(hass, entry).via_device_id == device.id


async def test_automatic_kodi_and_android_tv(hass, player, setup):
    tv(hass, "kodi", host="10.0.0.9", name="Other")  # another address: not this one
    device = tv(hass, "androidtv", host=" 127.0.0.1 ", name="Shield")
    entry = await setup(hass, player)
    assert player_device(hass, entry).via_device_id == device.id


async def test_automatic_nothing_found(hass, player, setup):
    tv(hass, "enigma2", host="10.0.0.9")
    tv(hass, "hue", name="Lamp")  # same address, but not a TV integration
    entry = await setup(hass, player)
    assert player_device(hass, entry).via_device_id is None


async def test_options_none_and_chosen(hass, player, setup):
    device = tv(hass)
    chosen = tv(hass, "sonos", host="10.0.0.3", name="Soundbar")
    entry = await setup(hass, player)
    assert player_device(hass, entry).via_device_id == device.id

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["type"] is FlowResultType.FORM
    values = [o["value"] for o in flow["data_schema"].schema["parent_device"].config["options"]]
    assert values[:2] == ["auto", "none"] and chosen.id in values and player_device(hass, entry).id not in values
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {"parent_device": "none"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert player_device(hass, entry).via_device_id is None

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(flow["flow_id"], {"parent_device": chosen.id})
    await hass.async_block_till_done()
    assert entry.options["parent_device"] == chosen.id
    assert player_device(hass, entry).via_device_id == chosen.id

    # the chosen device is removed: no parent, and the form falls back to automatic
    dr.async_get(hass).async_remove_device(chosen.id)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert player_device(hass, entry).via_device_id is None
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert flow["data_schema"]({})["parent_device"] == "auto"


async def test_own_device_is_never_its_parent(hass, player, setup):
    entry = await setup(hass, player)
    hass.config_entries.async_update_entry(entry, options={"parent_device": player_device(hass, entry).id})
    await hass.async_block_till_done()
    assert player_device(hass, entry).via_device_id is None
