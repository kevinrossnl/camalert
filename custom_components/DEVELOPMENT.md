# custom_components/camalert/ and homeassistant/ – Home Assistant integration and blueprints

Read the root [DEVELOPMENT.md](../DEVELOPMENT.md) first (privacy, how we work, CI). This file sits next to the integration
folder (not in it), so HACS does not install it into users' Home Assistant.

## Files

| Path | What |
|---|---|
| `camalert/manifest.json` | version = the plugin's `__version__`; `hacs.json` (root) has the oldest supported Home Assistant |
| `camalert/config_flow.py` | config flow + reconfigure (same player only) |
| `camalert/coordinator.py`, `api.py` | polling `/camalert/status`, the HTTP calls (POST + `X-CamAlert-Token`; GET for older players) |
| `camalert/button.py`, `sensor.py`, `switch.py`, `event.py`, `entity.py` | entities, created per player capability |
| `camalert/__init__.py`, `services.yaml` | actions `show`, `mosaic`, `hide`, `ptz`; webhook for the colour keys |
| `camalert/diagnostics.py` | redacted diagnostics |
| `camalert/strings.json`, `icons.json` | English texts (source) and icons; `translations/*.json` are generated from `core/i18n/` |
| `../homeassistant/blueprints/` | blueprints; inputs frozen for 1.x ([README](../homeassistant/blueprints/README.md), `tests/test_blueprints.py`) |
| `../homeassistant/camalert_package.yaml` | REST-command alternative (YAML) |

## Rules
- Texts are player-neutral: "player (Enigma2 receiver or Kodi)"; "receiver" only next to "Enigma2".
- Never edit `translations/*.json` by hand: change `strings.json`, then `python3 tools/i18n/i18n.py update/build`.
- Actions, entities and blueprints stay backwards compatible within a major version; blueprint input keys, order and
  defaults are frozen (`FROZEN` in `tests/test_blueprints.py`).
- Runtime tests in a real Home Assistant against a fake player: `HA_VERSION=latest sh tools/ci.sh ha` (and `min`);
  branch coverage of the integration >= 90 % (`tests/homeassistant/`, see `tests/README.md`).
- hassfest and the HACS check run on GitHub at release time.
