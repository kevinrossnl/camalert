"""#83: update entity per player: installed version from /camalert/status, latest from a (fake) GitHub release,
cached for every player, never installed."""
import pytest
from aiohttp import web
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError

from custom_components.camalert import update

UPDATE = "update.living_room_camalert"


class FakeGitHub:
    def __init__(self):
        self.release = {"tag_name": "v1.3.0", "html_url": "https://example.invalid/releases/v1.3.0",
                        "body": "## Added\n- update entity"}
        self.status = 200
        self.requests = []

    async def handle(self, request):
        self.requests.append(dict(request.headers))
        if self.status != 200:
            return web.Response(status=self.status, text="rate limited")
        return web.json_response(self.release)


@pytest.fixture
async def github(monkeypatch, socket_enabled):
    gh = FakeGitHub()
    app = web.Application()
    app.router.add_get("/releases/latest", gh.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setattr(update, "RELEASE_URL", "http://127.0.0.1:%d/releases/latest" % port)
    clock = [1000.0]
    monkeypatch.setattr(update.time, "monotonic", lambda: clock[0])
    gh.clock = clock
    yield gh
    await runner.cleanup()


async def test_update_available(hass, player, github, setup, hass_ws_client):
    await setup(hass, player)
    state = hass.states.get(UPDATE)
    assert state.state == "on"
    assert state.attributes["installed_version"] == "1.0.0" and state.attributes["latest_version"] == "1.3.0"
    assert state.attributes["release_url"] == "https://example.invalid/releases/v1.3.0"
    assert state.attributes["title"] == "CamAlert"
    assert not state.attributes["supported_features"] & UpdateEntityFeature.INSTALL
    assert "Authorization" not in github.requests[0]  # never a token
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": "update/release_notes", "entity_id": UPDATE})
    assert (await client.receive_json())["result"] == "## Added\n- update entity"
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("update", "install", {"entity_id": UPDATE}, blocking=True)
    assert player.actions() == [("POST", "/camalert/webhook")]  # nothing sent to the player


async def test_up_to_date_and_cache(hass, player, kodi, github, setup):
    github.release["tag_name"] = "1.0.0"
    await setup(hass, player)
    await setup(hass, kodi)
    assert hass.states.get(UPDATE).state == "off"
    assert hass.states.get("update.bedroom_camalert").state == "off"
    assert len(github.requests) == 1  # one request for every player

    cache = update.release_cache(hass)
    github.release["tag_name"] = "v1.4.0"
    await cache.get()
    assert len(github.requests) == 1  # still cached
    github.clock[0] += update.CACHE_SECONDS + 1
    assert (await cache.get())["version"] == "1.4.0" and len(github.requests) == 2


async def test_github_errors_keep_the_last_release(hass, player, github, setup):
    github.status = 403
    await setup(hass, player)
    assert hass.states.get(UPDATE).state == "unknown"  # never answered: unknown, not "up to date"
    cache = update.release_cache(hass)
    github.status = 200
    await cache.get()
    assert len(github.requests) == 1  # waits RETRY_SECONDS after an error
    github.clock[0] += update.RETRY_SECONDS + 1
    assert (await cache.get())["version"] == "1.3.0"

    github.release = {"name": "no tag"}
    github.clock[0] += update.CACHE_SECONDS + 1
    assert (await cache.get())["version"] == "1.3.0"  # broken answer: the last known release stays


async def test_no_network(hass, player, setup):
    await setup(hass, player)  # RELEASE_URL: a refused port (conftest)
    state = hass.states.get(UPDATE)
    assert state.state == "unknown" and state.attributes["installed_version"] == "1.0.0"
