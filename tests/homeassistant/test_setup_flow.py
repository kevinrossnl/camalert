"""#122: Home Assistant sends its go2rtc address to a player: right after adding a player that was never set up,
and later in the options (a player that is set up only takes a local-network address)."""
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import DOMAIN
from test_config_flow import form_input
from test_zeroconf import discover

from custom_components.camalert import go2rtc_setup


def suggested(result, key="go2rtc_server"):
    for k in result["data_schema"].schema:
        if str(k) == key:
            return (k.description or {}).get("suggested_value")
    raise KeyError(key)


async def add(hass, player):
    """Starts adding the player through the user step; returns the next step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "player"})  # #95
    return await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))


async def test_new_player_gets_the_go2rtc_address(hass, player):
    player.settings["server"] = ""
    result = await add(hass, player)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "setup"
    assert result["description_placeholders"] == {"name": "Living room"}
    assert suggested(result) == ""  # Home Assistant knows no go2rtc a player can reach
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"go2rtc_server": "192.168.1.10:1984", "camera": "garden"})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["title"] == "Living room"
    assert (player.settings["server"], player.settings["camera"]) == ("http://192.168.1.10:1984", "garden")
    assert "go2rtc_server" not in result["data"]
    await hass.async_block_till_done()


async def test_any_address_for_a_new_player_and_skip(hass, player, kodi):
    player.settings["server"] = ""
    result = await add(hass, player)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"go2rtc_server": "ftp://x"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"go2rtc_server": "invalid_server"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"go2rtc_server": "https://ha.public.example:1984", "camera": "a,b"})
    assert result["errors"] == {"camera": "invalid_camera"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"go2rtc_server": "https://ha.public.example:1984"})
    assert result["type"] is FlowResultType.CREATE_ENTRY  # never set up: any address
    assert player.settings["server"] == "https://ha.public.example:1984"
    kodi.settings["server"] = ""
    result = await add(hass, kodi)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})  # empty = skip
    assert result["type"] is FlowResultType.CREATE_ENTRY and kodi.settings["server"] == ""
    await hass.async_block_till_done()


async def test_no_step_for_a_set_up_or_older_player(hass, player, kodi):
    result = await add(hass, player)  # set up already
    assert result["type"] is FlowResultType.CREATE_ENTRY
    kodi.settings["server"] = ""
    kodi.capabilities = ["cameras", "post", "show", "status"]  # a player from before #122
    result = await add(hass, kodi)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_discovered_new_player_gets_the_step_too(hass, player):
    player.settings["server"] = ""
    result = await discover(hass, player)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "setup"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"go2rtc_server": "192.168.1.10"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert player.settings["server"] == "http://192.168.1.10:1984"
    await hass.async_block_till_done()


async def test_suggested_address(hass):
    assert await go2rtc_setup.suggested_go2rtc(hass) == ""
    MockConfigEntry(domain="go2rtc", data={"url": "http://192.168.1.20:1984/"}).add_to_hass(hass)
    assert await go2rtc_setup.suggested_go2rtc(hass) == "http://192.168.1.20:1984"


async def test_suggested_address_of_ha_itself(hass):
    MockConfigEntry(domain="go2rtc", data={"url": "http://localhost:1984"}).add_to_hass(hass)
    with patch.object(go2rtc_setup, "_ha_address", AsyncMock(return_value="192.168.1.7")):
        assert await go2rtc_setup.suggested_go2rtc(hass) == "http://192.168.1.7:1984"
    with patch.object(go2rtc_setup, "_go2rtc_app_installed", return_value=True), \
            patch.object(go2rtc_setup, "_ha_address", AsyncMock(return_value="192.168.1.7")), \
            patch.object(hass.config_entries, "async_entries", return_value=[]):  # only the go2rtc app
        assert await go2rtc_setup.suggested_go2rtc(hass) == "http://192.168.1.7:1984"


async def test_options_send_the_address(hass, player, setup):
    entry = await setup(hass, player)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert {"go2rtc_server", "camera"} <= {str(k) for k in flow["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"parent_device": "auto", "go2rtc_server": "http://8.8.8.8:1984"})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"go2rtc_server": "already_set_up"}
    assert player.settings["server"] == "http://192.168.1.10:1984"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"parent_device": "auto", "go2rtc_server": "http://192.168.1.20:1984", "camera": "garden"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (player.settings["server"], player.settings["camera"]) == ("http://192.168.1.20:1984", "garden")
    assert entry.options == {"parent_device": "auto", "doorbell": [], "doorbell_camera": ""}  # the address is sent, not kept
    await hass.async_block_till_done()


async def test_options_without_setup_capability(hass, player, setup):
    player.capabilities = ["cameras", "post", "show", "status", "dnd"]
    entry = await setup(hass, player)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    assert "go2rtc_server" not in {str(k) for k in flow["data_schema"].schema}


async def test_send_errors():
    from custom_components.camalert.api import CamAlertError, CamAlertForbidden

    class Api:
        def __init__(self, err):
            self.err = err

        async def setup(self, server, camera):
            raise self.err
    assert await go2rtc_setup.send(Api(CamAlertForbidden("x")), "http://192.168.1.10", None) == {"base": "forbidden"}
    assert await go2rtc_setup.send(Api(CamAlertError("timeout")), "http://192.168.1.10", None) == \
        {"base": "cannot_connect"}
    assert await go2rtc_setup.send(Api(RuntimeError("boom")), "http://192.168.1.10", None) == {"base": "unknown"}


async def test_ha_address(hass):
    with patch("homeassistant.components.network.async_get_source_ip", AsyncMock(return_value="192.168.1.7")):
        assert await go2rtc_setup._ha_address(hass) == "192.168.1.7"
    with patch("homeassistant.components.network.async_get_source_ip", AsyncMock(side_effect=RuntimeError)), \
            patch("homeassistant.helpers.network.get_url", return_value="http://192.168.1.8:8123"):
        assert await go2rtc_setup._ha_address(hass) == "192.168.1.8"
    with patch("homeassistant.components.network.async_get_source_ip", AsyncMock(side_effect=RuntimeError)), \
            patch("homeassistant.helpers.network.get_url", side_effect=RuntimeError):
        assert await go2rtc_setup._ha_address(hass) is None
    assert go2rtc_setup._go2rtc_app_installed(hass) is False  # no Supervisor in tests
