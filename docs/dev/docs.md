# The documentation

## Structure

| Folder | For | What goes there |
|---|---|---|
| `docs/index.md` | everyone | the table of contents; every page is linked from here |
| `docs/user/` | users of any player | guide, go2rtc, cameras, features, keys, settings, glossary, recipes, troubleshooting |
| `docs/players/` | one player | `enigma2.md`, `kodi.md`: install, settings screen, what is only on that player |
| `docs/integrations/` | other systems | Home Assistant, MQTT, Frigate, HTTP API, monitoring |
| `docs/dev/` | contributors | compatibility, translating, privacy, screenshots, this page |
| `docs/images/` | | illustrations (drawn) and `enigma2/` screenshots ([screenshots](screenshots.md)) |

One fact lives on one page; other pages link to it. Something that differs per player goes on the player page, the
rest is written for "the player".

## Words

Use the terms of the [glossary](../user/glossary.md) verbatim. **Player** = Enigma2 receiver or Kodi; write
*receiver* only for Enigma2 ("Enigma2 receiver", or on the Enigma2 page). Kodi: **Kodi 19 or newer** everywhere
(the add-on needs `xbmc.python` 3.0.0 = Kodi 19 Matrix).

## Generated parts

`python3 tools/docs.py update` writes the blocks between `<!-- BEGIN generated: ... -->` and
`<!-- END generated: ... -->`; never edit inside them:

| Page | Block | Source |
|---|---|---|
| [keys](../user/keys.md) | `keys` | `core/camalert_core/keymap.py` + key names and hint labels in `present.py` |
| [glossary](../user/glossary.md) | `glossary` | `core/i18n/glossary.json` (terms, `definition`, forbidden English synonyms) |
| [settings](../user/settings.md) | `settings` | `core/camalert_core/schema.py` |

## Docs tests (`tests/test_docs.py`)

- the generated blocks are up to date (`tools/docs.py check`);
- every relative link and image in `README.md`, `docs/**/*.md`, the `DEVELOPMENT.md` files and the other READMEs points
  to an existing file, and every `#anchor` to an existing heading (#36; external links are not checked);
- every page under `docs/` is reachable from `docs/index.md`;
- no forbidden synonym (glossary) and no "receiver" where Kodi is meant, outside the Enigma2 page and the dev pages;
- there is one `DEVELOPMENT.md` per main folder and the files they name exist (#36);
- the Kodi version claim matches the add-on's `xbmc.python` requirement (Kodi 19).

`tests/test_docs_examples.py` (#36) checks the examples:

- every `/camalert/<route>` example (README, `docs/`, `homeassistant/`) names a route of `core/camalert_core/api.py`
  and only parameters its handler reads (query strings, `curl -d`, the JSON bodies in the API table, the REST package
  payload); `POST` is documented only for actions, `GET` only for reads;
- the topic table in [MQTT](../integrations/mqtt.md) is exactly the MQTT contract table (`(published)` included),
  and no page names another `camalert/<id>/...` topic;
- every Kodi version with an API fixture is on the [compatibility](compatibility.md) page;
- the `tools/ci.sh` areas and the `tools/docs.py` / `tools/i18n/i18n.py` subcommands named in the `DEVELOPMENT.md` files,
  `tests/README.md` and `docs/dev/` exist.
