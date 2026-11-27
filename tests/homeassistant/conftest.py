"""Home Assistant runtime tests (#33): pytest-homeassistant-custom-component against a fake CamAlert player.

Only collected where Home Assistant is installed (Python >= 3.13, `pip install -r tests/homeassistant/requirements*.txt`);
the normal test run (`python3 -m pytest`, no Home Assistant) skips this folder. Run: `sh tools/ci.sh ha`.
"""
import pytest

try:
    import homeassistant  # noqa: F401
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_*.py"]
    HAVE_HA = False
else:
    HAVE_HA = True

if HAVE_HA:
    import _paths

    _paths.add(_paths.ROOT)
    # import it now, before Home Assistant puts its own testing_config/custom_components on the path
    import custom_components.camalert  # noqa: F401,E402

    from homeassistant.const import CONF_HOST, CONF_PORT
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from fake_player import FakePlayer

    DOMAIN = "camalert"
    INTERNAL_URL = "http://192.168.1.20:8123"

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(enable_custom_integrations):
        yield

    @pytest.fixture(autouse=True)
    def fast_timeout(monkeypatch):
        from custom_components.camalert import api
        monkeypatch.setattr(api, "TIMEOUT", 0.5)

    @pytest.fixture(autouse=True)
    def no_github(monkeypatch):
        """Never GitHub in tests (#83): the release check gets a refused local port unless a test sets a fake."""
        from custom_components.camalert import update
        monkeypatch.setattr(update, "RELEASE_URL", "http://127.0.0.1:9/releases/latest")

    @pytest.fixture
    async def player(socket_enabled):
        p = await FakePlayer().start()
        p.reset()
        yield p
        await p.stop()

    @pytest.fixture
    async def kodi(socket_enabled):
        p = await FakePlayer(platform="kodi", name="Bedroom", node_id="node-2", cameras=("garden",)).start()
        p.reset()
        yield p
        await p.stop()

    def entry_for(p, **data):
        return MockConfigEntry(domain=DOMAIN, title=p.name, unique_id=p.node_id,
                               data=dict({CONF_HOST: p.host, CONF_PORT: p.port, "https": p.https,
                                          "verify_ssl": False, "token": p.settings["token"]}, **data))

    async def setup_player(hass, p, **data):
        """Adds the fake player as a config entry and sets it up; returns the entry."""
        hass.config.internal_url = INTERNAL_URL
        entry = entry_for(p, **data)
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    @pytest.fixture
    def setup():
        return setup_player
