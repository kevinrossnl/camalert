"""Quick replies (#98): a signed colour key speaks a prepared text on the doorbell's speaker via tts.speak."""
from conftest import setup_player
from pytest_homeassistant_custom_component.common import async_mock_service

SPEAKER = "media_player.front_door_speaker"


async def _options(hass, entry, **values):  # noqa: D103
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    data = {"parent_device": "auto", "doorbell": [], "doorbell_camera": ""}
    data.update(values)
    result = await hass.config_entries.options.async_configure(flow["flow_id"], data)
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()


async def _press(hass, client, entry, payload):
    await client.post("/api/webhook/camalert_%s" % entry.entry_id, json=payload)
    await hass.async_block_till_done()


async def test_reply_on_a_signed_key(hass, player, hass_client_no_auth):
    entry = await setup_player(hass, player)
    hass.states.async_set("tts.test", "unknown")
    calls = async_mock_service(hass, "tts", "speak")
    replies, buttons = [], []
    hass.bus.async_listen("camalert_reply", lambda e: replies.append(e.data))
    hass.bus.async_listen("camalert_button", lambda e: buttons.append(e.data["button"]))
    await _options(hass, entry, reply_speaker=SPEAKER, reply_red="  Please leave the parcel at the door.  ",
                   reply_green="", reply_yellow="I'm coming.", reply_blue="")
    assert entry.options["reply_red"] == "Please leave the parcel at the door."
    client = await hass_client_no_auth()
    await _press(hass, client, entry, player.backend.press("front_door", "red"))
    await _press(hass, client, entry, player.backend.press("front_door", "green"))  # no text: only the event
    assert [c.data for c in calls] == [{"entity_id": "tts.test", "media_player_entity_id": SPEAKER,
                                        "message": "Please leave the parcel at the door.", "cache": True}]
    assert replies == [{"player": "Living room", "camera": "front_door", "button": "red",
                        "text": "Please leave the parcel at the door.", "speaker": SPEAKER}]
    assert buttons == ["red", "green"]  # the colour keys' own events still fire


async def test_no_reply_without_speaker_or_signature(hass, player, hass_client_no_auth):
    from camalert_core import api as core_api
    player.capabilities = [c for c in core_api.CAPABILITIES if c != "signed_buttons"]
    entry = await setup_player(hass, player)
    hass.states.async_set("tts.test", "unknown")
    calls = async_mock_service(hass, "tts", "speak")
    client = await hass_client_no_auth()
    await _options(hass, entry, reply_speaker=SPEAKER, reply_yellow="I'm coming.")
    await _press(hass, client, entry, {"button": "yellow", "camera": "front_door"})  # unsigned: refused
    await _options(hass, entry, reply_yellow="I'm coming.")  # speaker field emptied
    await _press(hass, client, entry, {"button": "yellow", "camera": "front_door"})  # no speaker: nothing
    assert calls == []


async def test_options_show_suggested_replies(hass, player):
    entry = await setup_player(hass, player)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    keys = {str(k): k for k in flow["data_schema"].schema}
    for key in ("reply_speaker", "reply_tts", "reply_red", "reply_green", "reply_yellow", "reply_blue"):
        assert key in keys
    assert keys["reply_yellow"].description["suggested_value"] == "I'm coming."
    # submitting without a speaker keeps the options clean: the suggestions are not stored
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {
        "parent_device": "auto", "reply_yellow": "I'm coming.", "reply_red": "Please leave the parcel at the door."})
    assert not any(k.startswith("reply_") for k in entry.options)
    # once set up, the stored texts are shown (no suggestions) and an emptied text stays empty
    await _options(hass, entry, reply_speaker=SPEAKER, reply_yellow="I'm coming.")
    assert entry.options["reply_red"] == "" and entry.options["reply_yellow"] == "I'm coming."
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    keys = {str(k): k for k in flow["data_schema"].schema}
    assert keys["reply_red"].description["suggested_value"] == ""
