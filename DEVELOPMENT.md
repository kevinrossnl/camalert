# Notes for contributors

## Privacy – this repository is public
- Mirrored to GitHub (`kevinrossnl/camalert`). Never add personal data: no real IP addresses, host names, domains, people, camera names, keys or tokens. Use neutral examples (`192.168.1.10`, `front_door`, `garden`).
- CI runs `tools/check_private.py` with a private denylist (CI secret `CAMALERT_DENYLIST`) and blocks the mirror when anything matches. `PUBLIC` in that script lists the only allowed exceptions (the GitHub owner name).
- Commit author: `CamAlert developers <noreply@camalert.invalid>`.
- Only commit when `check_private.py` **and** the tests pass (do not pipe them through `tail`, that hides the exit code).

## Layout
> **The structure is changing (restructure before v1.0.0, see issue #1):** players live in `players/`, shared code moves to
> `core/camalert_core/`. Read the latest comments on #1 before moving or adding files.

| Path | What |
|---|---|
| `core/camalert_core/` | Shared core, plain Python 3.8+ (no Enigma2/Twisted/Kodi/HA imports; `tests/test_lint.py` checks it): one module per domain, unit tests in `tests/core/` (branch coverage >= 90 %): `cameras` (names, titles, per-camera maps), `urls`, `rules` (modes, priorities, DND, hours, cooldown), `layout` (geometry), `api` (the HTTP API of every player: route table, validation, access rules, answers; the players' `server.py` are thin adapters, #5), `access` (allowlist, token, rate limit), `events`, `keymap` (remote-key map per player and screen + colour keys, #42; key codes live in `players/enigma2/CamAlert/keys.py` and Kodi `klogic.py`), `present` (what players show as text, #41: event source/priority/result/reason **codes** with translated labels, `event_line`/`event_details`, date formats, key hints built from the key map, `tour_status`), `i18n` (`N_()` marker for core texts, `kodi_ids`/`kodi_translator`; every text function takes `tr`), `update`, `mqtt/` (`codec`, `topics` incl. discovery), `devices/` (`config`, `foscam`, `onvif`, `client` = network calls), `obs/` (`log` = levels + `redact()`, `camlog`, `metrics`), `schema` (one settings schema: id, section, level, type, default, range/step, unit, label/help msgids, platforms; tests check the Enigma2 `_add()`/setup list and the Kodi settings.xml against it, #38/#7), `triggers/` (registry of trigger sources: `frigate`, `foscam`; a new source is one class with `@register`, #6). The builds copy the whole package into every player package as `camalert_core/`; inside it all imports are relative |
| `players/enigma2/CamAlert/` | Enigma2 plugin (Python 3). `services.py` (service references, channel lists, chime command, update source) and `keys.py` (remote key codes) are the Enigma2-only pure helpers; `display.py` (photo window, mosaic, tour, live, controller), `server.py` (HTTP adapter + backend for `camalert_core.api`), `mqtt.py` (MQTT + discovery), `bouquet.py` (camera channel list, auto update), `setup.py` (settings screen), `plugin.py` (entry points), `diagnostics.py` (diagnostics + event list screens), `picons.py` (picons, plain Python), `chime.wav` (made by `tools/make_chime.py`) |
| `custom_components/camalert/` | Home Assistant integration (config flow, buttons, sensor, DND switch, remote-button event entity + webhook, diagnostics, actions `show`/`mosaic`/`hide`/`ptz`). Same version number as the plugin (`manifest.json` = `__version__`) |
| `homeassistant/blueprints/` | Blueprints: doorbell, motion (armed / times), alarm, remote button |
| `homeassistant/camalert_package.yaml` | REST-command alternative (YAML) |
| `players/kodi/service.camalert/` | Kodi add-on. `resources/lib/camalert/`: `klogic.py` (pure, tested), `controller.py` (show/hide/live/resume), `display.py` (windows), `server.py` (HTTP adapter + backend for `camalert_core.api`), `mqtt.py`, `ptz.py`, `sources.py`, `kodiapi.py` (only place that talks to xbmc). The build copies `core/camalert_core/` in as `camalert_core/` |
| `players/kodi/repository.camalert/` | Kodi repository add-on (`@REPO_URL@` filled in by the build; CI publishes `dist/kodi-repo/` on GitHub Pages) |
| `po/` | Plugin translations (gettext), generated from `core/i18n/` (master catalogue + glossary, `tools/i18n/i18n.py`). `custom_components/camalert/translations/` = integration translations (generated too) |
| `tools/` | `build_ipk.py` (package), `build_feed.py` (opkg Packages index), `build_kodi.py` (Kodi zip + repository), `make_chime.py`, `msgfmt.py`, `strings.py` (POT), `check_private.py` |
| `docs/` | User documentation (English) |

## Rules (learned on real receivers)
- A new or changed setting goes into `core/camalert_core/schema.py` first (same id on every player); then `_add()` / settings.xml.
- Every setting is created through `_add()` in `__init__.py`: a broken saved value must never stop the plugin from loading.
- Never do network calls on the Enigma2 main thread (it freezes the GUI): use `threads.deferToThread`.
- Screens can be cleared by Enigma2 after closing: late callbacks must use `getattr(self, "active", False)`.
- Skins are designed for 1920x1080 and scaled to the desktop width (many skins are 1280x720).
- Settings are written with `configfile.save()` on save.
- `core/camalert_core/` has no Enigma2, Twisted, Kodi or Home Assistant imports and stays Python 3.8 compatible (Kodi 19): both players use it. `picons.py` is plain Python too.
- Everything that is logged or shown in diagnostics goes through `redact()`; camera passwords live only in
  `/etc/enigma2/camalert_devices.conf`, never in settings.
- Which key does what is defined once in `core/camalert_core/keymap.py`; change it there, not in the handlers. On-screen key hints come from `present.key_hint()` (never hard-code `OK = live ...`).
- Events store codes (`present.reason('cooldown', 30)`), never English; screens translate with `present.*_label(code, tr)`.
- Key hooks: `GlobalKeys` (colour keys / PTZ, priority -0x7FFFFFFF) runs before `KeyHook` (photo window, -0x7FFFFFFE).

## Rules (learned on real Kodi boxes)
- Create a window **and** call `doModal()` in one dedicated thread (`display.open_window`): Kodi runs `onAction` in the thread that created the window, and only modal windows get the remote keys.
- Play camera streams with a `ListItem` that has a mime type and `setContentLookup(False)`: otherwise Kodi probes the endless HTTP stream for 20 s and blocks JSON-RPC meanwhile.
- Resume a film with the `StartOffset` property, not with `seekTime()` right after `play()`.
- Kodi only loads the strings of an add-on unpacked by hand after a restart: `kodiapi.tr()` falls back to our own English `strings.po`.
- Every snapshot gets a new file name (Kodi caches images by path).
- Kodi labels: `resources/language/*/strings.po` (ids 30000+), checked by `tests/kodi/test_kodi.py`.

## Rules
- Code, comments and docs in English; user-facing texts translated (en, nl, de, fr, it, pl) in **one master
  catalogue** `core/i18n/` (#38/#43, format in `core/i18n/README.md`). English stays in the sources (`_()` in the
  plugin, `N_()` in the core, Kodi `en_gb/strings.po`, HA `strings.json`); after changing them run
  `python3 tools/i18n/i18n.py update`, translate the empty `msgstr` in `core/i18n/<lang>.po`, then `build`.
  `po/`, the other Kodi `strings.po` and HA `translations/*.json` are generated: never edit them by hand.
  `tests/test_i18n.py` fails on missing translations, placeholder mismatches, forbidden synonyms/tone and
  glossary terms not used verbatim (`core/i18n/glossary.json`; tone nl *je*, de *du*, fr *vous*, it/pl impersonal).
- New shared logic goes into `core/camalert_core/` with a unit test. Enigma2/Home Assistant specific code is tested on a real receiver / Home Assistant before a release.
- API, MQTT topics, HA actions and blueprints must stay backwards compatible within a major version.
- Tests: `python3 -m pytest` (see `tests/README.md`; `python3 -m unittest discover -s tests` also works). Packages: `python3 tools/build_ipk.py dist`, `python3 tools/build_kodi.py dist`.

## CI (Forgejo Actions, `.forgejo/workflows/tests.yml`)
- Every area runs `sh tools/ci.sh <area>` (`lint`, `core`, `unit`, `build`, `privacy`, `ha`); run the same locally before a push.
  `ha` = Home Assistant runtime tests (#33, `tests/homeassistant/`): oldest (hacs.json) and latest Home Assistant on the
  workstation, latest only in the NAS fallback; integration branch coverage >= 90 %.
- Runner choice (#54): heavy jobs run on the **workstation runner** and fall back to the NAS runner (`truenas`) only
  when no workstation runner is online. The NAS disks cannot take a burst of parallel jobs.
  - `pick-runner` (tiny, on `truenas`, no installs) runs `tools/ci_pick_runner.py`: it asks
    `GET /api/v1/user/actions/runners` with the secret `RUNNER_STATUS_TOKEN` (personal token, scope `read:user`;
    the automatic workflow token cannot see runners) and outputs `runner` + `mode`. Preferred labels, best first:
    `werkstation skills-werkstation` (an idle runner wins over a busy one; a busy one still wins over the NAS).
    No secret or an API error = fallback.
  - `parallel`: one job per area, `runs-on: ${{ needs.pick-runner.outputs.runner }}`.
  - `sequential` (fallback): one job runs every area in turn on the NAS (one container, one package install).
  - `gate` (light, on `truenas`) is the one required check and accepts either mode.
- Test the fallback without stopping the workstation: Actions › tests › Run workflow › `force_runner` = `truenas`
  (or `werkstation` to force the workstation). `tests/test_ci.py` checks the picker and the workflow structure:
  a new area needs a job, a step in `sequential`, a case in `tools/ci.sh` and an entry in the gate.
- If the workstation goes offline after `pick-runner` chose it, its jobs wait in the queue until it is back
  (Forgejo has no queue timeout); cancel the run and start it again with `force_runner` = `truenas`.
- No `actions/cache`: the runner cache server is not reachable from the NAS job containers (timeouts).

## Release
1. Raise the version in `players/enigma2/CamAlert/__init__.py` and `custom_components/camalert/manifest.json`, update `CHANGELOG.md`.
2. Tag `vX.Y.Z` and push; GitHub Actions builds the `.ipk` and the Kodi zips, runs hassfest and the HACS check, creates the release and publishes GitHub Pages (Settings › Pages › Source: GitHub Actions): the Kodi repository and the opkg feed (`Packages.gz`, `camalert-feed.conf`) in one site. The Kodi add-on version is always `__version__`.
