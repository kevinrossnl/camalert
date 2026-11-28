"""#132: the Problem report button saves the player's report plus the diagnostics and links to the issue form."""
import json
import os
import shutil

from homeassistant.helpers import entity_registry as er

BUTTON = "button.living_room_problem_report"


async def test_problem_report_button(hass, player, setup):
    folder = hass.config.path("camalert_reports")
    shutil.rmtree(folder, ignore_errors=True)  # the test config folder is shared between runs
    entry = await setup(hass, player)
    assert hass.states.get(BUTTON) is not None
    await hass.services.async_call("button", "press", {"entity_id": BUTTON}, blocking=True)
    await hass.async_block_till_done()
    assert ("GET", "/camalert/report") in player.actions()
    files = os.listdir(folder)
    assert len(files) == 1 and files[0].startswith("living_room-") and files[0].endswith(".json")
    with open(os.path.join(folder, files[0]), encoding="utf-8") as f:
        data = json.load(f)
    assert data["player_report"]["report"] == 1
    assert data["player_report"]["platform"] == player.platform
    assert "diagnostics" in data and data["integration"]
    assert "token" not in data["player_report"]["settings"]
    assert entry is not None


async def test_no_report_button_on_an_older_player(hass, player, setup):
    player.capabilities = ["cameras", "dnd", "header_token", "hide", "post", "settings", "show", "status"]
    entry = await setup(hass, player)
    ids = [e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)]
    assert BUTTON not in ids
