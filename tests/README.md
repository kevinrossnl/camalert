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
- `contract/`: the HTTP API table (`api_table.py`) runs against the Enigma2 handler (via e2fake) and the Kodi
  handler. Known differences are listed in `KNOWN` with the issue that fixes them; a stale entry fails.
  Use public example addresses for "outside the network" (Python treats the RFC 5737 ranges as private).
- `fakes/broker.py`: in-process MQTT 3.1.1 broker (127.0.0.1, random port) on the shared codec;
  `contract/test_mqtt_contract.py` runs both MQTT clients against it and checks `contract/mqtt_table.py`.
- `kodi_stubs.py`: strict xbmc modules per Kodi version (19-22), generated from `compat/fixtures/kodi_api/`:
  unknown names raise AttributeError, wrong arguments TypeError, every call is recorded, JSON-RPC requests are
  checked against `compat/fixtures/jsonrpc/` (Kodi's own schema, `tools/kodi_jsonrpc_snapshot.py`), and
  `MONITOR["waits"]` lets the service loop run. The Kodi functional tests run once per version.
