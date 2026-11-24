# Master translation catalogue (#38, #43)

Every user-facing text of CamAlert is translated **once**, here, and the three translation formats are generated
from it. Do not edit `po/*.po`, the Kodi `strings.po` of other languages than English, or
`custom_components/camalert/translations/*.json` by hand: run the tool instead.

| File | What |
|---|---|
| `glossary.json` | The 20 core terms of the UI review (#2) in en/nl/de/fr/it/pl (`terms`), the forbidden synonyms and tone patterns per language (`forbidden`, regex), the tone decision (`tone`: nl *je*, de *du*, fr *vous*, it and pl impersonal) and `contains_languages` |
| `<lang>.po` | One gettext catalogue per language (nl, de, fr, it, pl), keyed by the English text. `#:` lines say where a text is used (`e2`, `kodi:<id>`, `ha:<json path>`); the tool rewrites them |

## Where the English texts come from
- **Enigma2**: `_("...")` in `players/enigma2/CamAlert/*.py`, plus `N_("...")` in `core/camalert_core` (texts the core
  hands to the players, such as event reasons and key hints, #41) – `tools/strings.py`.
- **Kodi**: `players/kodi/service.camalert/resources/language/resource.language.en_gb/strings.po`. Ids are stable (≥ 30000;
  an id never changes meaning – add a new id instead). The core's `N_()` texts get ids in 30500–30699 automatically.
- **Home Assistant**: `custom_components/camalert/strings.json` (`[%key:...%]` references are copied unchanged).

## Workflow
```sh
python3 tools/i18n/i18n.py update   # after changing English texts: adds new msgids (empty msgstr), drops unused ones
# translate the empty msgstr in core/i18n/<lang>.po (glossary terms verbatim, tone as above)
python3 tools/i18n/i18n.py build    # writes po/CamAlert.pot, po/<lang>.po, Kodi strings.po, HA translations
python3 tools/i18n/i18n.py check    # what tests/test_i18n.py runs
```
One English text has one translation everywhere. If a place really needs another wording, add an entry with a
context: `msgctxt "kodi:30231"` / `msgctxt "ha:selector.mode.options.photo"` (one place) or `msgctxt "kodi"` /
`"ha"` / `"e2"` (one format); the most specific one wins.

## What `check` refuses
- a missing (empty) translation, a different set of placeholders (`%s`, `%d`, `%(name)s`, `{name}`, `[%key:...%]`)
  or a different number of line breaks, in any of the three formats;
- a forbidden synonym or tone pattern from `glossary.json` (English sources included);
- a glossary term that is the whole text but not translated verbatim; in `contains_languages` also a text that
  contains a term without its translation (`exact_only` terms such as the priorities inflect and are exempt);
- unused catalogue entries and generated files that are not up to date.
