"""Players announce themselves as _camalert._tcp (#121): discovered, confirmed (token only when the player asks for
one), a known player gets its new address."""
from ipaddress import ip_address
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType

try:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # Home Assistant before 2025.2; its test requirements may lack the zeroconf library
    try:
        from homeassistant.components.zeroconf import ZeroconfServiceInfo
    except ImportError:
        from types import SimpleNamespace as ZeroconfServiceInfo  # the flow only reads the attributes

from conftest import DOMAIN, entry_for


def info(p, **props):
    txt = dict({"id": p.node_id, "name": p.name, "platform": "enigma2", "version": "1.3.0", "api_version": "1",
                "https": "0"}, **props)
    return ZeroconfServiceInfo(ip_address=ip_address(p.host), ip_addresses=[ip_address(p.host)], port=p.port,
                               hostname="camalert-%s.local." % p.node_id, type="_camalert._tcp.local.",
                               name="%s._camalert._tcp.local." % p.name, properties=txt)


async def discover(hass, p, **props):
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_ZEROCONF},
                                                     data=info(p, **props))


async def test_discovered_player_is_added_with_one_click(hass, player):
    result = await discover(hass, player)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "zeroconf_confirm"
    assert result["description_placeholders"] == {"name": player.name, "host": player.host}
    assert list(result["data_schema"].schema) == []  # no token asked while the player needs none
    flow = next(f for f in hass.config_entries.flow.async_progress() if f["flow_id"] == result["flow_id"])
    assert flow["context"]["title_placeholders"] == {"name": player.name}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == player.name
    assert result["data"] == {CONF_HOST: player.host, CONF_PORT: player.port, "https": False, "verify_ssl": True,
                              "token": ""}
    assert result["result"].unique_id == player.node_id
    await hass.async_block_till_done()


async def test_known_player_gets_the_new_address(hass, player):
    entry = entry_for(player, host="192.168.1.99", port=8100)
    entry.add_to_hass(hass)
    with patch("custom_components.camalert.async_setup_entry", return_value=True):
        result = await discover(hass, player)
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"
    assert (entry.data[CONF_HOST], entry.data[CONF_PORT]) == (player.host, player.port)


async def test_token_is_asked_only_when_needed(hass, player):
    player.settings["token"] = "abc123"
    result = await discover(hass, player)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {}  # now it asks, without an error
    assert [str(k) for k in result["data_schema"].schema] == ["token"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": "wrong"})
    assert result["errors"] == {"base": "forbidden"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"token": " abc123 "})
    assert result["type"] is FlowResultType.CREATE_ENTRY and result["data"]["token"] == "abc123"
    await hass.async_block_till_done()


async def test_unreachable_player_shows_an_error(hass, player):
    result = await discover(hass, player)
    await player.stop()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": "cannot_connect"}


async def test_announcement_without_id_or_of_another_player(hass, player):
    result = await discover(hass, player, id="")
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "not_camalert"
    result = await discover(hass, player, id="someone-else")  # the address answers with another id
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "wrong_player"


async def test_https_player_uses_its_own_certificate(hass, player):
    result = await discover(hass, player, https="1")
    with patch("custom_components.camalert.config_flow._check",
               return_value=({"id": player.node_id, "name": player.name}, {})) as check, \
            patch("custom_components.camalert.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
    assert check.call_args[0][1]["https"] is True and check.call_args[0][1]["verify_ssl"] is False
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert (result["data"]["https"], result["data"]["verify_ssl"]) == (True, False)
