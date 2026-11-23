# Translating CamAlert

Translations live in `po/<language>.po` (for example `po/de.po`). They are standard gettext files; you can edit them with any text editor or with [Poedit](https://poedit.net/).

- Improve a translation: edit the `msgstr` lines and open a pull request.
- Add a language: copy `po/CamAlert.pot` to `po/<code>.po` (two-letter code, like `es` or `sv`), fill in every `msgstr` and open a pull request.
- Keep placeholders like `%s` and `%d` exactly as they are.

Developers: after changing texts in the code, run `python3 tools/strings.py > po/CamAlert.pot` and add the new texts to every `.po` file. The tests check that every language is complete.
