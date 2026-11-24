# Translating CamAlert

Every user-facing text is translated **once**, in the master catalogue `core/i18n/` (one gettext file per language:
`nl.po`, `de.po`, `fr.po`, `it.po`, `pl.po`). The Enigma2 `po/` files, the Kodi `strings.po` files and the Home
Assistant `translations/*.json` are generated from it – do not edit those by hand.

- **Improve a translation:** edit the `msgstr` in `core/i18n/<language>.po` (with any text editor or
  [Poedit](https://poedit.net/)), run `python3 tools/i18n/i18n.py build` and open a pull request.
- **Use the glossary:** the CamAlert terms are fixed per language ([glossary](../user/glossary.md)); tone: Dutch
  *je*, German *du*, French *vous*, Italian and Polish impersonal. The check refuses forbidden synonyms.
- Keep placeholders like `%s`, `%d` and `{name}` exactly as they are.
- **Add a language:** open an issue first – the three formats and the tests need the new code.

Developers: after changing English texts in the code run `python3 tools/i18n/i18n.py update`, translate the empty
`msgstr`, then `build`; `python3 tools/i18n/i18n.py check` is what `tests/test_i18n.py` runs. Details:
[core/i18n/README.md](../../core/i18n/README.md).
