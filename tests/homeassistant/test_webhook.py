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
    resp = await client.post(url, json={"button": "green", "camera": "front_door"})
    assert resp.status == 200
    await hass.async_block_till_done()
    assert events == [{"device_id": player_device(hass, entry).id, "player": "Living room", "receiver": "Living room",
                       "camera": "front_door", "button": "green"}]
    st = hass.states.get(EVENT)
    assert st.attributes["event_type"] == "green" and st.attributes["camera"] == "front_door"
    assert st.attributes["event_types"] == ["red", "green", "yellow", "blue"]
    for bad in ({"button": "purple"}, {}):
        await client.post(url, json=bad)
    resp = await client.post(url, data=b"not json")
    await hass.async_block_till_done()
    assert len(events) == 1
