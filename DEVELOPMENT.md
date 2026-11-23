# Notes for contributors

- This repository is **public** (mirrored to GitHub). Never add personal data: no real IP addresses, host names, domains, people or camera names, keys or tokens. Use neutral examples (`192.168.1.10`, `front_door`).
- CI runs `tools/check_private.py` with a private denylist (CI secret `CAMALERT_DENYLIST`) and blocks the mirror when anything matches.
- Code, comments and docs in English. User-facing texts go through `_()`; after changing them run `python3 tools/strings.py > po/CamAlert.pot` and update every `po/*.po` (the tests check completeness).
- Pure logic lives in `src/CamAlert/logic.py` and has unit tests; Enigma2-specific code in `display.py`, `server.py`, `setup.py`, `plugin.py`.
- Tests: `python3 -m unittest discover -s tests`. Package: `python3 tools/build_ipk.py dist`.
