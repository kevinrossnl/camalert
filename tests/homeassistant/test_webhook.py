"""Colour keys: the player posts to Home Assistant's webhook (local only) -> bus event + event entity (#33)."""
from conftest import INTERNAL_URL, setup_player
from custom_components.camalert import player_device

EVENT = "event.living_room_remote_button"


async def test_webhook_set_on_the_player(hass, player):
    entry = await setup_player(hass, player)
    wid = "camalert_%s" % entry.entry_id
    assert player.webhooks == ["%s/api/webhook/%s" % (INTERNAL_URL, wid)]
    assert player.settings["ha_webhook"] == player.webhooks[0]
    reg = hass.data["webhook"][wid]
    get = (lambda k: reg[k]) if isinstance(reg, dict) else (lambda k: getattr(reg, k))  # dict before 2026.x
    assert get("local_only") is True and set(get("allowed_methods")) == {"POST"}


async def test_button_press(hass, player, hass_client_no_auth):
    entry = await setup_player(hass, player)
    events = []
    hass.bus.async_listen("camalert_button", lambda e: events.append(e.data))
    client = await hass_client_no_auth()
    url = "/api/webhook/camalert_%s" % entry.entry_id
    assert len(player.settings["ha_webhook_secret"]) == 64  # #82: the player got a secret and signs its keys
    resp = await client.post(url, json=player.backend.press("front_door", "green"))
    assert resp.status == 200
    await hass.async_block_till_done()
    assert events == [{"device_id": player_device(hass, entry).id, "player": "Living room", "receiver": "Living room",
                       "camera": "front_door", "button": "green", "verified": True}]
    st = hass.states.get(EVENT)
    assert st.attributes["event_type"] == "green" and st.attributes["camera"] == "front_door"
    assert st.attributes["event_types"] == ["red", "green", "yellow", "blue"]
    for bad in ({"button": "purple"}, {}):
        await client.post(url, json=bad)
    resp = await client.post(url, data=b"not json")
    await hass.async_block_till_done()
    assert len(events) == 1


async def test_signed_keys_refuse_fakes_and_replays(hass, player, hass_client_no_auth):
    """#82: a press is accepted once, only with the right signature and only while it is fresh."""
    import time
    entry = await setup_player(hass, player)
    events = []
    hass.bus.async_listen("camalert_button", lambda e: events.append(e.data["button"]))
    client = await hass_client_no_auth()
    url = "/api/webhook/camalert_%s" % entry.entry_id
    good = player.backend.press("gate", "green")
    await client.post(url, json=good)
    await client.post(url, json=good)  # replay of the same press
    await client.post(url, json={"button": "green", "camera": "gate"})  # unsigned
    await client.post(url, json=dict(good, nonce="00" * 16))  # signature no longer fits
    await client.post(url, json=dict(good, button="red"))  # another key with the old signature
    await client.post(url, json=player.backend.press("gate", "yellow", now=time.time() - 300))  # too old
    forged = dict(player.backend.press("gate", "blue"))
    forged["sig"] = "0" * 64
    await client.post(url, json=forged)
    await hass.async_block_till_done()
    assert events == ["green"]
    await client.post(url, json=player.backend.press("gate", "blue"))  # a new, honest press still works
    await hass.async_block_till_done()
    assert events == ["green", "blue"]


async def test_older_player_sends_unsigned_keys(hass, player, hass_client_no_auth):
    """A player without "signed_buttons" gets no secret and its keys still work, marked as not verified."""
    from camalert_core import api as core_api
    player.capabilities = [c for c in core_api.CAPABILITIES if c != "signed_buttons"]
    entry = await setup_player(hass, player)
    assert player.settings["ha_webhook_secret"] == ""
    events = []
    hass.bus.async_listen("camalert_button", lambda e: events.append(e.data))
    client = await hass_client_no_auth()
    await client.post("/api/webhook/camalert_%s" % entry.entry_id, json={"button": "red", "camera": "front_door"})
    await hass.async_block_till_done()
    assert [(e["button"], e["verified"]) for e in events] == [("red", False)]


async def test_secret_sent_again_when_the_player_lost_it(hass, player):
    """The player was reset or imported settings: the next status says so and Home Assistant sends a secret."""
    entry = await setup_player(hass, player)
    first = player.settings["ha_webhook_secret"]
    player.settings["ha_webhook_secret"] = ""
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert player.settings["ha_webhook_secret"] == first
