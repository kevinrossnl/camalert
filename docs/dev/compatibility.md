# Compatibility

What is tested where. **CI** = automated tests with fake modules built from the real API of that image/version
(`tests/enigma2/`, `tests/kodi/`), **box** = tested on a real receiver/player, **untested** = neither.

## Enigma2 images

| Image | Profile | Python | Status | Notes |
|---|---|---|---|---|
| openATV 7.x / 8.x | `openatv` | 3.12 (7.x), 3.13 (8.x) | CI + box (openATV 8.0.1 on Vu+ Uno 4K SE, Duo 4K, Uno 4K, Solo 4K) | |
| OpenPLi 9.x / develop | `openpli` | 3.12+ | CI | |
| OpenBH 5.x | `openbh` | 3.12+ | CI | |
| VTi (Vu+) | `vti` | unknown | CI (assumed API) | VTi sources are not public; modelled with the OpenPLi API |
| DreamOS (Dreambox OE 2.5 / 2.6) | `dreamos` | 2.7 | not supported | Python 2.7; `eTimer` has no `callback` list (only `timeout.connect`); no `eActionMap.unbindAction`; `ConfigListScreen` creates no `HelpWindow`/`VKeyIcon`; no `getCurrentlyPlayingServiceOrGroup` |

The API snapshots (`tests/enigma2/harness/fixtures/e2api/*.json`) are made with `tools/e2_api_snapshot.py` from the
enigma2 sources of each image; the source and commit are in each file. Not covered by the fakes: the C++ part
(`enigma` module, only the known differences are modelled), real skin rendering, remote control, video.

## Kodi

| Kodi | Status | Notes |
|---|---|---|
| 19 Matrix, 20 Nexus, 21 Omega, 22 Piers | CI: every Kodi call checked against Kodistubs of that version (`tests/kodi/compat/test_kodi_versions.py`) and strict stubs per version (`tests/kodi/stubs.py`) | #25 fixed (mosaic) |
| Minimum | `xbmc.python` 3.0.0 = **Kodi 19 Matrix**; the docs say "Kodi 19 or newer" everywhere (`tests/test_docs.py`) | no real Kodi 19/20 box tested yet |
| LibreELEC 12.2 (Kodi 21.3) | 2 boxes: fresh install, upgrades, e2e runner (#18, #35) | |
| Windows 11 (Kodi 21.2) | box: install from zip, e2e runner (#18) | |
| Fire TV / Android | untested (#19) | different paths (`special://` only), no ffmpeg |

Not yet: a CI matrix over several Python versions (#21; today the device code is checked against the Python 3.8
grammar in the `lint` area) and a headless Kodi container smoke test (#37).
