"""Diagnostics download: player info, status, events and log; token, address and ids redacted (#33, #44).
The expected output is tests/homeassistant/golden/diagnostics.json (UPDATE_GOLDEN=1 rewrites it)."""
import json
import os

try:
    from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry
except ImportError:  # older pytest-homeassistant-custom-component (HA 2025.1): download it like the UI does
    from homeassistant.setup import async_setup_component

    async def get_diagnostics_for_config_entry(hass, hass_client, entry):
        assert await async_setup_component(hass, "diagnostics", {})
        client = await hass_client()
        resp = await client.get("/api/diagnostics/config_entry/%s" % entry.entry_id)
        assert resp.status == 200
        return (await resp.json())["data"]

from conftest import setup_player

GOLDEN = os.path.join(os.path.dirname(__file__), "golden", "diagnostics.json")


async def test_diagnostics_redacted(hass, hass_client, player):
    player.settings["token"] = "s3cret-token"
    entry = await setup_player(hass, player, token="s3cret-token")
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    text = json.dumps(diag)
    for secret in ("s3cret-token", "127.0.0.1", "node-1", "/api/webhook/"):
        assert secret not in text, secret
    diag["entry"]["data"]["port"] = "<port>"  # random port of the fake player
    if os.environ.get("UPDATE_GOLDEN"):
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w") as f:
            json.dump(diag, f, indent=2, sort_keys=True)
            f.write("\n")
    with open(GOLDEN) as f:
        assert diag == json.load(f)


async def test_diagnostics_when_the_player_fails(hass, hass_client, player):
    entry = await setup_player(hass, player)
    player.status_override = 403
    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)
    assert diag["error"] == "forbidden (token or network)"
    assert diag["player"]["platform"] == "enigma2" and diag["player"]["model"] == "Enigma2 receiver"
