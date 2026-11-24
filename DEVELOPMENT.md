# Notes for contributors

## Privacy – this repository is public
- Mirrored to GitHub (`kevinrossnl/camalert`). Never add personal data: no real IP addresses, host names, domains, people, camera names, keys or tokens. Use neutral examples (`192.168.1.10`, `front_door`, `garden`).
- CI runs `tools/check_private.py` with a private denylist (CI secret `CAMALERT_DENYLIST`) and blocks the mirror when anything matches. `PUBLIC` in that script lists the only allowed exceptions (the GitHub owner name).
- Commit author: `CamAlert developers <noreply@camalert.invalid>`.
- Only commit when `check_private.py` **and** the tests pass (do not pipe them through `tail`, that hides the exit code).

## Layout
| Path | What |
|---|---|
| `src/CamAlert/` | Enigma2 plugin (Python 3). `logic.py` = pure functions with unit tests; `display.py` (photo window, mosaic, tour, live, controller), `server.py` (HTTP API), `mqtt.py` (MQTT + discovery), `bouquet.py` (camera channel list, auto update), `setup.py` (settings screen), `plugin.py` (entry points), `devices.py` (Foscam/ONVIF client, plain Python), `camlog.py` (camalert.log + syslog, plain Python), `diagnostics.py` (diagnostics + event list screens), `picons.py` (picons, plain Python), `chime.wav` (made by `tools/make_chime.py`) |
| `custom_components/camalert/` | Home Assistant integration (config flow, buttons, sensor, DND switch, remote-button event entity + webhook, diagnostics, actions `show`/`mosaic`/`hide`/`ptz`). Same version number as the plugin (`manifest.json` = `__version__`) |
| `homeassistant/blueprints/` | Blueprints: doorbell, motion (armed / times), alarm, remote button |
| `homeassistant/camalert_package.yaml` | REST-command alternative (YAML) |
| `kodi/service.camalert/` | Kodi add-on. `resources/lib/camalert/`: `klogic.py` (pure, tested), `controller.py` (show/hide/live/resume), `display.py` (windows), `server.py` (same API as Enigma2), `mqtt.py`, `ptz.py`, `sources.py`, `kodiapi.py` (only place that talks to xbmc). `logic.py` and `devices.py` are **copied in from `src/CamAlert/` by `tools/build_kodi.py`** (git-ignored there) |
| `kodi/repository.camalert/` | Kodi repository add-on (`@REPO_URL@` filled in by the build; CI publishes `dist/kodi-repo/` on GitHub Pages) |
| `po/` | Plugin translations (gettext). `custom_components/camalert/translations/` = integration translations |
| `tools/` | `build_ipk.py` (package), `build_feed.py` (opkg Packages index), `build_kodi.py` (Kodi zip + repository), `make_chime.py`, `msgfmt.py`, `strings.py` (POT), `check_private.py` |
| `docs/` | User documentation (English) |

## Rules (learned on real receivers)
- Every setting is created through `_add()` in `__init__.py`: a broken saved value must never stop the plugin from loading.
- Never do network calls on the Enigma2 main thread (it freezes the GUI): use `threads.deferToThread`.
- Screens can be cleared by Enigma2 after closing: late callbacks must use `getattr(self, "active", False)`.
- Skins are designed for 1920x1080 and scaled to the desktop width (many skins are 1280x720).
- Settings are written with `configfile.save()` on save.
- `logic.py`, `devices.py`, `camlog.py` and `picons.py` have no Enigma2 imports: the Kodi add-on (`kodi/`) reuses them.
- Everything that is logged or shown in diagnostics goes through `redact()`; camera passwords live only in
  `/etc/enigma2/camalert_devices.conf`, never in settings.
- Key hooks: `GlobalKeys` (colour keys / PTZ, priority -0x7FFFFFFF) runs before `KeyHook` (photo window, -0x7FFFFFFE).

## Rules (learned on real Kodi boxes)
- Create a window **and** call `doModal()` in one dedicated thread (`display.open_window`): Kodi runs `onAction` in the thread that created the window, and only modal windows get the remote keys.
- Play camera streams with a `ListItem` that has a mime type and `setContentLookup(False)`: otherwise Kodi probes the endless HTTP stream for 20 s and blocks JSON-RPC meanwhile.
- Resume a film with the `StartOffset` property, not with `seekTime()` right after `play()`.
- Kodi only loads the strings of an add-on unpacked by hand after a restart: `kodiapi.tr()` falls back to our own English `strings.po`.
- Every snapshot gets a new file name (Kodi caches images by path).
- Kodi labels: `resources/language/*/strings.po` (ids 30000+), checked by `tests/test_kodi.py`.

## Rules
- Code, comments and docs in English; user-facing texts translated (en, nl, de, fr, it, pl). Tests check completeness:
  - plugin: `python3 tools/strings.py > po/CamAlert.pot`, then add new texts to every `po/*.po`;
  - integration: `strings.json` and every `translations/*.json` need the same keys.
- New logic goes into `logic.py` with a unit test. Enigma2/Home Assistant specific code is tested on a real receiver / Home Assistant before a release.
- API, MQTT topics, HA actions and blueprints must stay backwards compatible within a major version.
- Tests: `python3 -m unittest discover -s tests`. Packages: `python3 tools/build_ipk.py dist`, `python3 tools/build_kodi.py dist`.

## Release
1. Raise the version in `src/CamAlert/__init__.py` and `custom_components/camalert/manifest.json`, update `CHANGELOG.md`.
2. Tag `vX.Y.Z` and push; GitHub Actions builds the `.ipk` and the Kodi zips, runs hassfest and the HACS check, creates the release and publishes GitHub Pages (Settings › Pages › Source: GitHub Actions): the Kodi repository and the opkg feed (`Packages.gz`, `camalert-feed.conf`) in one site. The Kodi add-on version is always `__version__`.
