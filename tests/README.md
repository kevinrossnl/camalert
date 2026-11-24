# Tests

```sh
python3 -m pytest                       # everything (pytest is the runner; unittest classes work as before)
python3 -m pytest -m kodi               # one area: core, contract, enigma2, kodi, ha, build
python3 -m coverage run -m pytest && python3 -m coverage report   # branch coverage of every layer
python3 -m unittest discover -s tests   # still works without pytest
```

Python 3.8 (Kodi 19) needs `pip install "pytest<8.4"`. Optional: `pyyaml` (blueprint tests).

- `_paths.py` is the only file that knows where things live in the repository. Tests `import _paths` and take
  their paths from it; when files move, only `_paths.py` changes.
- The Kodi add-on is imported from the source tree (`_paths.kodi_package()`), so coverage measures the real files.
  The built zip is still checked, including a smoke import of every module from the extracted zip.
- The Enigma2 plugin runs inside `compat/e2fake.py` (fake Enigma2 modules built from API snapshots of real images).
- Privacy: `test_private.py` only finds personal words with the private denylist in `CAMALERT_DENYLIST`
  (see `DEVELOPMENT.md`).
