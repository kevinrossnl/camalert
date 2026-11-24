# players/kodi/ – Kodi add-on and repository

Read the root [DEVELOPMENT.md](../../DEVELOPMENT.md) first (privacy, how we work, CI). Shared logic belongs in
[core](../../core/DEVELOPMENT.md), not here. Minimum: Kodi 19 (`xbmc.python` 3.0.0), Python 3.8.

## Files

| Path | What |
|---|---|
| `service.camalert/addon.xml` | add-on manifest (version = `__version__` of the plugin, set by the build) |
| `service.camalert/resources/settings.xml` | settings (schema version 2; levels from the schema) |
| `service.camalert/resources/language/resource.language.en_gb/strings.po` | English labels (ids 30000+; 30500–30699 = core texts); other languages generated from `core/i18n/` |
| `resources/lib/camalert/klogic.py` | pure, tested logic: key names, settings parsing, fonts, colour keys |
| `resources/lib/camalert/kodiapi.py` | the only place that talks to `xbmc` |
| `resources/lib/camalert/controller.py` | show / hide / live / resume |
| `resources/lib/camalert/display.py` | windows: photo window, multi-camera window, mosaic, tour, live bar, PTZ |
| `resources/lib/camalert/server.py` | HTTP adapter + backend for `camalert_core.api` |
| `resources/lib/camalert/mqtt.py`, `ptz.py`, `sources.py`, `diag.py`, `script.py` | MQTT, camera control + Foscam and UniFi Protect pollers (`ptz.py`), camera sources, diagnostics, settings buttons / event list |
| `repository.camalert/` | Kodi repository add-on (`@REPO_URL@` filled in by the build; CI publishes `dist/kodi-repo/` on GitHub Pages) |

The build (`python3 tools/build_kodi.py dist`) copies `core/camalert_core/` in as `camalert_core/`. Tests:
`tests/kodi/` (strict stubs per Kodi 19–22, JSON-RPC checked against Kodi's schema).

## Rules (learned on real Kodi boxes)
- Create a window **and** call `doModal()` in one dedicated thread (`display.open_window`): Kodi runs `onAction` in
  the thread that created the window, and only modal windows get the remote keys.
- Play camera streams with a `ListItem` that has a mime type and `setContentLookup(False)`: otherwise Kodi probes the
  endless HTTP stream for 20 s and blocks JSON-RPC meanwhile.
- Resume a film with the `StartOffset` property, not with `seekTime()` right after `play()`.
- Kodi only loads the strings of an add-on unpacked by hand after a restart: `kodiapi.tr()` falls back to our own
  English `strings.po`.
- Every snapshot gets a new file name (Kodi caches images by path).
- Colour keys arrive as one action (`ACTION_COLOUR`); the button code says which (`klogic.colour_name`).
- Estuary has no ◀ ▶ and no `font30`: hints use `< >` (`glyphs=False`), fonts come from the skin's Font.xml.
- Real Kodi tests: only when nothing plays, muted, settings file restored afterwards.
