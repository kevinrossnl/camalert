# Tests

```sh
python3 -m pytest                       # everything (pytest is the runner; unittest classes work as before)
python3 -m pytest -m kodi               # one area: core, contract, enigma2, kodi, ha, build
python3 -m coverage run -m pytest && python3 -m coverage report   # branch coverage of every layer
python3 -m unittest discover -s tests   # still works without pytest
# core coverage gate (CI): branch coverage of core/camalert_core by tests/core alone must stay >= 90 %
python3 -m coverage run --source=core/camalert_core -m pytest tests/core && python3 -m coverage report --fail-under=90
```

Python 3.8 (Kodi 19) needs `pip install "pytest<8.4"`. Optional: `pyyaml` (blueprint tests).

- `core/` tests one core module each (`test_<module>.py`), no player code.
- `_paths.py` is the only file that knows where things live in the repository. Tests `import _paths` and take
  their paths from it; when files move, only `_paths.py` changes.
- The Kodi add-on is imported from the source tree (`_paths.kodi_package()`), so coverage measures the real files.
  The built zip is still checked, including a smoke import of every module from the extracted zip.
- The Enigma2 plugin runs inside `enigma2/harness/e2fake.py` (fake Enigma2 modules built from API snapshots of real images).
- Privacy: `test_private.py` only finds personal words with the private denylist in `CAMALERT_DENYLIST`
  (see `DEVELOPMENT.md`).
- `contract/`: the HTTP API table (`api_table.py`) runs against `camalert_core.api` directly (`core/test_api.py`),
  the Enigma2 adapter (via e2fake) and the Kodi adapter. Known differences are listed in `KNOWN` with the issue that fixes them; a stale entry fails.
  "Outside the network" can be any public address; since #52 the RFC 5737 / RFC 3849 documentation ranges count as outside too (`access.LAN_NETWORKS`). Webhook host names under `.example` resolve through `tests/fakes/dns.py` (no real DNS).
- `fakes/broker.py`: in-process MQTT 3.1.1 broker (127.0.0.1, random port) on the shared codec;
  `contract/test_mqtt_contract.py` runs both MQTT clients against it and checks `contract/mqtt_table.py`.
- `kodi/stubs.py`: strict xbmc modules per Kodi version (19-22), generated from `kodi/fixtures/kodi_api/`:
  unknown names raise AttributeError, wrong arguments TypeError, every call is recorded, JSON-RPC requests are
  checked against `kodi/fixtures/jsonrpc/` (Kodi's own schema, `tools/kodi_jsonrpc_snapshot.py`), and
  `MONITOR["waits"]` lets the service loop run. The Kodi functional tests run once per version.
- `test_i18n.py`: the master translation catalogue (`core/i18n/`, `tools/i18n/i18n.py check`): every Enigma2, Kodi and
  Home Assistant text translated, same placeholders, no forbidden synonyms or tone, glossary terms verbatim,
  generated files up to date (#38/#43).

## Home Assistant runtime tests (`homeassistant/`, #33)

`pytest-homeassistant-custom-component` runs the integration in a real Home Assistant against `fake_player.py`: an
aiohttp server on 127.0.0.1 that answers through `camalert_core.api.handle()` (the API of every player), with knobs
for the token, capabilities, older players, HTTP errors (403/429/500), delays (timeouts) and a self-signed HTTPS
certificate. `test_contract_fake.py` sends the whole HTTP contract table to it over real HTTP, so the fake answers
exactly like Enigma2 and Kodi. Covered: config flow (errors, duplicates, reconfigure), setup/unload/reload, the
coordinator, entities per capability, the actions (exact request on the player, errors raise), the webhook and the
event entity, diagnostics redaction (`golden/diagnostics.json`, `UPDATE_GOLDEN=1` rewrites it) and the blueprints.

```sh
HA_VERSION=latest sh tools/ci.sh ha   # or min = oldest supported Home Assistant (hacs.json); needs uv + internet
HA_PY=/path/to/venv/bin/python sh tools/ci.sh ha   # with an existing venv (pip install -r tests/homeassistant/requirements-latest.txt)
```
Needs Python 3.13 (min) / 3.14 (latest); without Home Assistant installed (the normal `python3 -m pytest`) this
folder is skipped. Branch coverage of `custom_components/camalert` must stay >= 90 %. When `hacs.json` gets a newer
minimum, raise `requirements-min.txt` to the matching `pytest-homeassistant-custom-component`; raise
`requirements-latest.txt` now and then (its `homeassistant==` pin is the Home Assistant version tested).

## CI

`.forgejo/workflows/tests.yml` runs on every push and pull request; each area is `sh tools/ci.sh <area>`
(`lint`, `core`, `unit`, `build`, `privacy`, `ha`), so `sh tools/ci.sh unit` locally runs exactly what CI runs.
`ha` runs twice on the workstation (oldest and latest Home Assistant) and only with the latest one in the NAS fallback.
Jobs run on the workstation runner when it is online, otherwise all areas run one after another in a single job on
the NAS runner (#54; details in `DEVELOPMENT.md` › CI). `test_ci.py` checks the runner choice
(`tools/ci_pick_runner.py`) and that every area runs in both modes and is checked by `gate`.
