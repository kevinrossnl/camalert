## What and why

<!-- What does this change, and why? Link the issue: "fixes #12" or "refs #12". -->

## How it was tested

<!-- New or changed tests; tested on a real receiver / Kodi / Home Assistant? (muted, settings restored) -->

## Checklist

- [ ] There is an issue for this change, and bigger changes were agreed there first.
- [ ] Tests added or changed (`tests/`), and they use no network.
- [ ] `sh tools/ci.sh lint`, `core`, `unit` and `build` pass (each one ends without error).
- [ ] Docs updated (`docs/`), and `python3 tools/docs.py update` run if settings or keys changed.
- [ ] Texts only changed in the English sources and `core/i18n/` (never the generated translation files).
- [ ] API, MQTT topics, Home Assistant actions and blueprint inputs stay backwards compatible.
- [ ] No personal data: no real IP addresses, host names, camera names, keys or tokens; images follow the
      [privacy checklist](https://github.com/kevinrossnl/camalert/blob/main/docs/dev/privacy.md) and went through `python3 tools/check_images.py --strip`.
- [ ] `CHANGELOG.md` has a line under *Unreleased* if users notice the change.
