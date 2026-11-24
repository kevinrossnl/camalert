"""Config flow: add a player, errors, duplicates, reconfigure (#33, #44)."""
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

from conftest import DOMAIN, entry_for, setup_player


def form_input(p, **kw):
    return dict({CONF_HOST: " %s " % p.host, CONF_PORT: p.port, "https": False, "verify_ssl": True, "token": ""}, **kw)


async def start(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    return result


def defaults(result):
    return {str(k): k.default() for k in result["data_schema"].schema if callable(getattr(k, "default", None))}


async def test_add_player(hass, player):
    result = await start(hass)
    assert defaults(result) == {CONF_HOST: "", CONF_PORT: 8099, "https": False, "verify_ssl": True, "token": ""}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room"
    assert result["data"][CONF_HOST] == "127.0.0.1"  # trimmed
    assert result["result"].unique_id == "node-1"
    await hass.async_block_till_done()
    assert result["result"].state is config_entries.ConfigEntryState.LOADED


async def test_already_added_updates_the_address(hass, player):
    entry = entry_for(player, host="192.168.1.99")
    entry.add_to_hass(hass)
    result = await start(hass)
    with patch("custom_components.camalert.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert entry.data[CONF_HOST] == "127.0.0.1"


async def test_cannot_connect(hass, player):
    await player.stop()
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}


async def test_timeout_and_too_many_requests_cannot_connect(hass, player):
    player.delay = 2
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["errors"] == {"base": "cannot_connect"}
    player.delay, player.status_override = 0, 429
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["errors"] == {"base": "cannot_connect"}


async def test_wrong_token_is_forbidden(hass, player):
    player.settings["token"] = "secret"
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player, token="wrong"))
    assert result["errors"] == {"base": "forbidden"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player, token="secret"))
    assert result["type"] is FlowResultType.CREATE_ENTRY
    method, path, headers, _body = player.requests[-1]
    assert headers.get("X-CamAlert-Token") == "secret" and "secret" not in path


async def test_outside_the_network_is_forbidden(hass, player):
    player.caller_ip = "8.8.8.8"
    result = await start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["errors"] == {"base": "forbidden"}


async def test_own_certificate_needs_the_check_off(hass, socket_enabled):
    from fake_player import FakePlayer
    p = await FakePlayer().start(https=True)
    try:
        result = await start(hass)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(p, https=True))
        assert result["errors"] == {"base": "certificate"}
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], form_input(p, https=True, verify_ssl=False))
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    finally:
        for e in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_unload(e.entry_id)
        await p.stop()


async def test_unexpected_error_is_shown_not_raised(hass, player):
    result = await start(hass)
    with patch("custom_components.camalert.api.CamAlertApi.status", side_effect=RuntimeError("boom")):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player))
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "unknown"}


async def reconfigure(hass, entry):
    if hasattr(entry, "start_reconfigure_flow"):
        return await entry.start_reconfigure_flow(hass)
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})


async def test_reconfigure(hass, player):
    entry = await setup_player(hass, player)
    result = await reconfigure(hass, entry)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "reconfigure"
    assert defaults(result)[CONF_PORT] == player.port
    player.settings["token"] = "new"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(player, token="bad"))
    assert result["errors"] == {"base": "forbidden"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], form_input(player, token="new", verify_ssl=False))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data["token"] == "new"
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_reconfigure_to_another_player_is_refused(hass, player, kodi):
    entry = await setup_player(hass, player)
    result = await reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form_input(kodi))
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "wrong_player"
    assert entry.data[CONF_PORT] == player.port
