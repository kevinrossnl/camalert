# Notes for contributors

## Privacy – this repository is public
- Mirrored to GitHub (`kevinrossnl/camalert`). Never add personal data: no real IP addresses, host names, domains, people, camera names, keys or tokens. Use neutral examples (`192.168.1.10`, `front_door`, `garden`).
- CI runs `tools/check_private.py` with a private denylist (CI secret `CAMALERT_DENYLIST`) and blocks the mirror when anything matches. `PUBLIC` in that script lists the only allowed exceptions (the GitHub owner name).
- Commit author: `CamAlert developers <noreply@camalert.invalid>`.
- Only commit when `check_private.py` **and** the tests pass (do not pipe them through `tail`, that hides the exit code).

## Layout
| Path | What |
|---|---|
| `src/CamAlert/` | Enigma2 plugin (Python 3). `logic.py` = pure functions with unit tests; `display.py` (photo window, mosaic, tour, live, controller), `server.py` (HTTP API), `mqtt.py` (MQTT + discovery), `bouquet.py` (camera channel list, auto update), `setup.py` (settings screen), `plugin.py` (entry points) |
| `custom_components/camalert/` | Home Assistant integration (config flow, buttons, sensor, actions `show`/`mosaic`/`hide`). Same version number as the plugin (`manifest.json` = `__version__`) |
| `homeassistant/blueprints/` | Blueprints: doorbell, motion (armed / times), alarm |
| `homeassistant/camalert_package.yaml` | REST-command alternative (YAML) |
| `po/` | Plugin translations (gettext). `custom_components/camalert/translations/` = integration translations |
| `tools/` | `build_ipk.py` (package), `msgfmt.py`, `strings.py` (POT), `check_private.py` |
| `docs/` | User documentation (English) |

## Rules (learned on real receivers)
- Every setting is created through `_add()` in `__init__.py`: a broken saved value must never stop the plugin from loading.
- Never do network calls on the Enigma2 main thread (it freezes the GUI): use `threads.deferToThread`.
- Screens can be cleared by Enigma2 after closing: late callbacks must use `getattr(self, "active", False)`.
- Skins are designed for 1920x1080 and scaled to the desktop width (many skins are 1280x720).
- Settings are written with `configfile.save()` on save.

## Rules
- Code, comments and docs in English; user-facing texts translated (en, nl, de, fr, it, pl). Tests check completeness:
  - plugin: `python3 tools/strings.py > po/CamAlert.pot`, then add new texts to every `po/*.po`;
  - integration: `strings.json` and every `translations/*.json` need the same keys.
- New logic goes into `logic.py` with a unit test. Enigma2/Home Assistant specific code is tested on a real receiver / Home Assistant before a release.
- API, MQTT topics, HA actions and blueprints must stay backwards compatible within a major version.
- Tests: `python3 -m unittest discover -s tests`. Package: `python3 tools/build_ipk.py dist`.

## Release
1. Raise the version in `src/CamAlert/__init__.py` and `custom_components/camalert/manifest.json`, update `CHANGELOG.md`.
2. Tag `vX.Y.Z` and push; GitHub Actions builds the `.ipk`, runs hassfest and the HACS check, and creates the release.
