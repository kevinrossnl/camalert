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
- `test_docs.py` (#24/#47, links part of #36): generated doc blocks up to date (`tools/docs.py check`: key table from
  the key map, glossary, settings table), relative links/images/anchors in README, docs and DEVELOPMENT.md files resolve,
  every docs page reachable from `docs/index.md`, no forbidden synonyms, "player" (not "receiver") where Kodi is
  meant, "Kodi 19 or newer" everywhere, one `DEVELOPMENT.md` per main folder naming files that exist. After changing the key map, glossary or schema: `python3 tools/docs.py update`.
- `test_docs_examples.py` (#36): API examples in the docs and the REST package use existing routes, known
  parameters and the right method (scanned from the handlers in `core/camalert_core/api.py`); the MQTT topic table
  equals `contract/mqtt_table.py`; Kodi fixture versions on the compatibility page; CI areas and tool subcommands
  named in DEVELOPMENT.md files and dev docs exist.
- `test_community.py` (#23): the GitHub community files (CONTRIBUTING, SECURITY with private vulnerability
  reporting, Code of Conduct, issue forms asking for player, versions and redacted logs, pull request template)
  exist, parse and link to the public repository.
- `test_images.py` (#8): no metadata in images (`tools/check_images.py`, also run in the CI area `privacy`).
- `e2e/` (#35): the end-to-end runner `tools/e2e` against fake devices (`e2e/e2e_fakes.py`: OpenWebif with mute
  toggle and OSD drawn from the CamAlert state, Kodi JSON-RPC over TCP, an ssh box): safety, restore, scenarios, geometry.
  Real devices only through `tools/e2e/run.py` ([docs/dev/e2e.md](../docs/dev/e2e.md)), never in CI.
- `fakes/go2rtc.py`: fake go2rtc with demo cameras (solid-colour frames, `--unreachable`), for tests and screenshots; the Kodi
  module tests run against it (`FakeGo2rtc().start()` on 127.0.0.1). Error switches (#32): `latency`, `fail` (HTTP 500),
  `hang` (client timeouts), `empty` (no cameras), also on a running server.
- `fakes/camera.py` (#32): colour-coded camera (cam1 red, cam2 green, ... with a big index number; `tile_index()` reads a
  tile of a screenshot back), Foscam CGI and ONVIF with WS-Security that record every call (`start_camera(n)`).
  `fakes/frigate.py`: event sequences (new/update/end) and the event snapshot API.
- `tools/make_test_media.py` writes those pictures (and an ffmpeg test clip); `tools/record_fixture.py` records a real
  answer as a fixture, always anonymised (documentation address ranges, cam1.., no secrets, fixed timestamps) and
  only written when the privacy check passes. New tests use 192.0.2.0/24 and 2001:db8::/32 for remote addresses.
- `core/test_properties.py` (#34): hypothesis property tests for the pure parsers (MQTT codec, redaction, URLs, ports,
  Frigate); CI profile derandomized with 200 examples, `HYPOTHESIS_PROFILE=nightly` for more. A failing example
  becomes an ordinary unit test. Skipped without hypothesis (Python 3.8).
- **Network-free (#73):** `netguard.py`, installed by `conftest.py` for every pytest run, blocks outbound sockets (TCP
  connect, UDP sendto) to anything but loopback with `NetworkBlocked` (an `OSError`) and DNS lookups of real host
  names with `NameBlocked` (a `socket.gaierror`; reserved `.invalid`/`.test`/`.example` names fail at once and are
  allowed), and fails the test that tried,
  also when the code under test swallowed the error; the run ends with a list of blocked addresses. Use a fake on
  127.0.0.1 (`tests/fakes`) instead of a real server; `netguard.expect_blocked()` is only for the guard's own tests
  (`test_network_guard.py`).
- Android TV player (#64): `test_export_contract.py` (the JSON that the Kotlin tests read is up to date with the
  contract tables and the core), `test_androidtv_tools.py` (fake go2rtc on the device, golden APK listing). The
  Kotlin tests themselves (every contract row, MQTT contract, core reference answers) run with Gradle:
  `cd players/androidtv && ./gradlew :api:test`, in CI area `androidtv`.
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
(`lint`, `core`, `unit`, `build`, `privacy`, `ha`, `androidtv`, `pymatrix`), so `sh tools/ci.sh unit` locally runs exactly what CI runs.
`pymatrix` (#21) runs the core, Enigma2, Kodi and contract tests on Python 3.8 .. 3.13, only on the workstation.
`.forgejo/workflows/nightly.yml` runs the long property tests and the matrix every night; it never blocks a push.
`ha` runs twice on the workstation (oldest and latest Home Assistant) and only with the latest one in the NAS fallback.
`androidtv` (JDK 17+, Android SDK from dl.google.com, Gradle) runs only on the workstation; the NAS fallback skips it
with a message (#64).
Jobs run on the workstation runner when it is online, otherwise all areas run one after another in a single job on
the NAS runner (#54; details in `DEVELOPMENT.md` › CI). `test_ci.py` checks the runner choice
(`tools/ci_pick_runner.py`) and that every area runs in both modes and is checked by `gate`.
