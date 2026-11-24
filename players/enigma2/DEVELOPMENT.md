# players/enigma2/ – Enigma2 plugin

Read the root [DEVELOPMENT.md](../../DEVELOPMENT.md) first (privacy, how we work, CI). Shared logic belongs in
[core](../../core/DEVELOPMENT.md), not here.

## Files (`CamAlert/`)

| File | What |
|---|---|
| `__init__.py` | version (`__version__`) and every setting through `_add()` (schema version 2, `schema.migrate()` on start) |
| `plugin.py` | entry points (plugin menu, extensions: CamAlert, mosaic, tour, events) |
| `setup.py` | settings screen from the schema (sections, setup level, HELP, Test/Create channel list) |
| `display.py` | photo window (`PhotoWindow`), multi-camera window (`StripWindow`), notification (`NotifyWindow`), mosaic, tour, PTZ overlay, key hooks (`GlobalKeys`, `KeyHook`), `Controller` |
| `diagnostics.py` | diagnostics and event list screens |
| `helpable.py` | HELP key: `HelpableScreen`/`HelpableActionMap` when the image has them (#40) |
| `server.py` | HTTP adapter + backend for `camalert_core.api` |
| `mqtt.py` | MQTT + discovery |
| `bouquet.py` | camera channel list, automatic update |
| `services.py` | Enigma2-only pure helpers: service references, channel lists, chime command, update source |
| `keys.py` | remote key codes → key map names, ActionMap contexts |
| `picons.py` | picons for the camera channels (plain Python) |
| `chime.wav` | doorbell chime (made by `tools/make_chime.py`) |

`po/` (next to `CamAlert/`): `CamAlert.pot` and one `<lang>.po` per language, **generated** from the master
catalogue `core/i18n/` by `python3 tools/i18n/i18n.py build`; never edit them by hand. `build_ipk.py` compiles them
into `CamAlert/locale/<lang>/LC_MESSAGES/CamAlert.mo`. `_()` only uses this domain (#56).

Tests: `tests/enigma2/` (fake Enigma2 from API snapshots of real images, `harness/e2fake.py`); package:
`python3 tools/build_ipk.py dist` (golden listing in `tests/build/golden/`).

## Rules (learned on real receivers)
- Every setting is created through `_add()` in `__init__.py`: a broken saved value must never stop the plugin from
  loading. A new setting goes into `core/camalert_core/schema.py` first.
- Never do network calls on the Enigma2 main thread (it freezes the GUI): use `threads.deferToThread`.
- Screens can be cleared by Enigma2 after closing: late callbacks must use `getattr(self, "active", False)`.
- Skins are designed for 1920x1080 and scaled to the desktop width (many skins are 1280x720).
- Settings are written with `configfile.save()` on save.
- Camera passwords live only in `/etc/enigma2/camalert_devices.conf`, never in settings; logs go through `redact()`.
- Keys come from `core/camalert_core/keymap.py` (ActionMap contexts in `keys.ACTIONMAP`); hints from
  `present.key_hint()`. Key hooks: `GlobalKeys` (colour keys / PTZ, priority -0x7FFFFFFF) runs before `KeyHook`
  (photo window, -0x7FFFFFFE).
- The skin fonts of openATV have no ◀ ▶; they are drawn with `/usr/share/fonts/fallback.font` when it exists,
  otherwise `< >`.
- Real receiver tests: mute first (OpenWebif `/api/vol`: `set=mute` *toggles*, check `ismute`), never during a
  recording, restore settings, volume and channel afterwards; screenshots only of the OSD
  ([docs/dev/screenshots.md](../../docs/dev/screenshots.md)).
