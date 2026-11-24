# core/ – shared core and master translation catalogue

Read the root [DEVELOPMENT.md](../DEVELOPMENT.md) first (privacy, how we work, CI). This folder is one owner per task.

## Rules
- Plain Python **3.8+** (Kodi 19), no Enigma2, Twisted, Kodi or Home Assistant imports (`tests/test_lint.py` checks
  both). Inside `camalert_core` all imports are relative: the builds copy the whole package into every player
  package as `camalert_core/`.
- Every module has a unit test in `tests/core/test_<module>.py`; branch coverage of `core/camalert_core` by
  `tests/core` alone stays **>= 90 %** (`sh tools/ci.sh core`).
- A new or changed setting goes into `schema.py` first (same id on every player); then the players follow
  (Enigma2 `_add()`, Kodi `settings.xml`) and `python3 tools/docs.py update` refreshes the settings page.
- Which key does what is defined once in `keymap.py`; players translate their key codes only. On-screen key hints
  come from `present.key_hint()`; after a change run `python3 tools/docs.py update` (docs key table).
- Events store codes (`present.reason('cooldown', 30)`), never English; screens translate with
  `present.*_label(code, tr)`. Core texts are marked with `N_()` and every text function takes `tr`.
- Everything that is logged or shown in diagnostics goes through `obs.log.redact()`.
- The HTTP API (`api.py`) is the API of every player: the players' `server.py` are thin adapters. Changes stay
  backwards compatible within a major version (contract tables in `tests/contract/`).
- A change here affects both players: say so in the issue and let the player owners know.

## Translations (`i18n/`)
One master catalogue (#38/#43, format in [i18n/README.md](i18n/README.md)). English stays in the sources (`_()` in
the plugin, `N_()` in the core, Kodi `resource.language.en_gb/strings.po`, HA `strings.json`); after changing them run
`python3 tools/i18n/i18n.py update`, translate the empty `msgstr` in `i18n/<lang>.po`, then `build`. `players/enigma2/po/`, the
other Kodi `strings.po` and HA `translations/*.json` are generated: never edit them by hand. `tests/test_i18n.py`
fails on missing translations, placeholder mismatches, forbidden synonyms/tone and glossary terms not used verbatim
(`i18n/glossary.json`; tone nl *je*, de *du*, fr *vous*, it/pl impersonal). A glossary change also changes the docs
glossary: `python3 tools/docs.py update`.

## Files (`camalert_core/`)

| Module | What |
|---|---|
| `cameras` | names, titles, per-camera maps |
| `urls` | go2rtc and camera URLs |
| `rules` | modes, priorities, do not disturb, hours, cooldown |
| `layout` | geometry (designed at 1920x1080, scaled) |
| `api` | the HTTP API of every player: route table, validation, access rules, answers (#5) |
| `access` | allowlist (`LAN_NETWORKS`), token, rate limit |
| `events` | event list, caller source, diagnostics lines (the event line itself is `present.event_line`) |
| `keymap` | remote-key map per player and screen, colour keys (#42) |
| `present` | what players show as text (#41): event codes and labels, `event_line`/`event_details`, dates, key hints, `tour_status` |
| `i18n` | `N_()` marker, `kodi_ids`/`kodi_translator` |
| `schema` | the one settings schema (id, section, level, type, default, range/step, unit, label/help, platforms) and `migrate()` (#38/#7/#39) |
| `update` | update check |
| `mqtt/` | `codec`, `topics` (incl. discovery) |
| `devices/` | `config`, `foscam`, `onvif`, `unifi` (UniFi Protect helpers, #9), `client` (network calls; `Protect` = read-only Protect session) |
| `obs/` | `log` (levels + `redact()`), `camlog`, `metrics` |
| `triggers/` | registry of trigger sources (`frigate`, `foscam`, `unifi`); a new source is one class with `@register` (#6) |
