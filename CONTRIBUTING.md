# Contributing to CamAlert

Thank you for helping! CamAlert is a small volunteer project: an Enigma2 plugin, a Kodi add-on, a Home Assistant
integration and a shared core, all in this repository. This page is the short version; the full rules for every
folder are in [DEVELOPMENT.md](DEVELOPMENT.md) and the `DEVELOPMENT.md` of the folder you work in.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Found a security problem? Do **not** open an
issue: see [SECURITY.md](SECURITY.md).

## Questions, bugs and ideas

- First look at [Troubleshooting](docs/user/troubleshooting.md) (our FAQ) and the [documentation](docs/index.md).
- Open an [issue](https://github.com/kevinrossnl/camalert/issues/new/choose) with the matching form (bug, feature,
  question). For a bug we need the player (Enigma2 receiver with image and version, or Kodi with version and
  platform), the CamAlert version, the Home Assistant version if you use it, and a log excerpt.
- **Remove secrets from logs and screenshots**: passwords, tokens, RTSP addresses with keys, public IP addresses,
  host names, e-mail addresses and camera names you do not want to share. The CamAlert log already hides passwords
  and tokens, and the Home Assistant diagnostics download is redacted, but check before you post.

## Code

1. Open or pick an issue first, so nobody does the same work twice. Bigger changes (new folders, moved files, a
   new package, a change of the API, MQTT topics, Home Assistant actions or blueprint inputs) are discussed in the
   issue before you start.
2. Fork, make a branch, keep commits small and mention the issue (`refs #12`, `fixes #12`).
3. **Every change comes with a test** (`tests/`, see [tests/README.md](tests/README.md)): logic in
   `core/camalert_core/` gets a unit test, a bug gets a test that fails first. The tests never use the network.
4. Run the CI areas before you open a pull request and check that each one ends without error:

   ```sh
   python3 -m pip install pytest coverage pyyaml
   sh tools/ci.sh lint && sh tools/ci.sh core && sh tools/ci.sh unit && sh tools/ci.sh build
   ```

   The Home Assistant runtime tests (`HA_VERSION=latest sh tools/ci.sh ha`) and the Android TV build
   (`sh tools/ci.sh androidtv`) need more tools; CI runs them for you.
5. Open a pull request and fill in the checklist.

Some rules that keep CamAlert working on old receivers and Kodi 19:

- Shared logic goes into `core/camalert_core/` (plain Python 3.8+, no player imports); the players only adapt it.
- API, MQTT topics, Home Assistant actions and blueprints stay backwards compatible within a major version.
- Never do network calls on the Enigma2 main thread.
- Code, comments and docs in English.

## Translations

All texts are translated in one master catalogue (`core/i18n/`, English, Dutch, German, French, Italian, Polish).
Never edit the generated `.po`/`.json` files of the players: see [Translating](docs/dev/translating.md). New
languages are welcome.

## Documentation and pictures

Docs live in `docs/` (start at [docs/index.md](docs/index.md); rules in [docs/dev/docs.md](docs/dev/docs.md)).
Pictures are drawn illustrations or screenshots of the on-screen display with **demo cameras only**: never real
camera footage, never a TV programme. Follow the [privacy checklist](docs/dev/privacy.md) and run
`python3 tools/check_images.py --strip` before you add an image.

## Privacy

This repository is public. Use neutral examples (`192.168.1.10`, `front_door`, `garden`, `<password>`) and never
add real IP addresses, host names, camera names, people, keys or tokens. CI checks this, but it cannot see
everything.

## License

CamAlert is licensed under GPL-2.0-only ([LICENSE](LICENSE)). By contributing you agree that your contribution is
published under the same license.
