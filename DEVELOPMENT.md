# Notes for contributors

This file has the rules for the whole repository. Every main folder has its own `DEVELOPMENT.md` with the rules and the
file table of that folder: read the root file **and** the one of the folder you work in.

| Folder | Rules |
|---|---|
| `core/` – shared core and the master translation catalogue | [core/DEVELOPMENT.md](core/DEVELOPMENT.md) |
| `players/enigma2/` – Enigma2 plugin | [players/enigma2/DEVELOPMENT.md](players/enigma2/DEVELOPMENT.md) |
| `players/kodi/` – Kodi add-on and repository | [players/kodi/DEVELOPMENT.md](players/kodi/DEVELOPMENT.md) |
| `players/androidtv/` – Android TV / Fire TV app (Kotlin, #64) | [players/androidtv/DEVELOPMENT.md](players/androidtv/DEVELOPMENT.md) |
| `custom_components/camalert/` + `homeassistant/` – Home Assistant integration and blueprints | [custom_components/DEVELOPMENT.md](custom_components/DEVELOPMENT.md) |
| `docs/` + `README.md` – documentation | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| `tests/` | [tests/README.md](tests/README.md) |

## Privacy – this repository is public
- Mirrored to GitHub (`kevinrossnl/camalert`). Never add personal data: no real IP addresses, host names, domains,
  people, camera names, keys or tokens. Use neutral examples (`192.168.1.10`, `front_door`, `garden`).
- CI runs `tools/check_private.py` with a private denylist (CI secret `CAMALERT_DENYLIST`) and `tools/check_images.py`
  (no image metadata, #8). The push mirror to GitHub has **no sync on commit and no interval**: the CI job `mirror`
  starts it only after a green `gate` (privacy included), for `main` and `v*` tags (secret `MIRROR_SYNC_TOKEN`,
  #104). Without that secret, start it by hand after a green run. Never put names in commit messages either: they
  are public on GitHub and cannot be removed without rewriting history. `PUBLIC` in `check_private.py` lists the only
  allowed exceptions (the GitHub owner name). Images: the checklist in [docs/dev/privacy.md](docs/dev/privacy.md).
- Commit author: `CamAlert developers <noreply@camalert.invalid>`.
- **Everything in git is in English** (from 28-11-2026): commit messages, issue titles and texts, comments on issues
  and PRs, code comments and docs. The repository is public and read internationally. Translations live only in
  the i18n catalogue (`core/i18n`). Older Dutch commits and issues stay as they are.
- Only commit when `check_private.py` **and** the tests pass (do not pipe them through `tail`, that hides the exit code).

## How we work
- **One person per folder per task.** Several people work in parallel; each task owns one folder of the table
  above (shared files such as `CHANGELOG.md` and `tests/README.md` only get small additions). Need a change in
  another folder? Ask its owner in the issue, or make a new issue.
- **Structure changes only after discussion:** moving or renaming files or folders, new top-level folders, new
  packages, a new CI area or a change to the layout of `core/` are first proposed in an issue and agreed (see #1).
- **Issues (Forgejo) drive the work.** Every commit says `refs #n` or `fixes #n`. Comment on the issue when you
  start, report progress (what changed, commit ids, how it was tested, what is left) and close it with the commit
  (`fixes #n`) or a final comment. Findings outside the task become **new issues** (with labels), not silent extra
  changes. Issues: `#n` in commits and docs refers to the project's issue tracker.
- Git: `git pull --rebase` before you start and before every push; one commit per push; never `--force`, never
  rewrite history. Before every push run the CI areas (`sh tools/ci.sh lint|core|unit|build|privacy`, `privacy`
  with `CAMALERT_DENYLIST` set) and check their exit codes.
- Code, comments and docs in English; user-facing texts translated (en, nl, de, fr, it, pl) in the master catalogue
  `core/i18n/` ([core/DEVELOPMENT.md](core/DEVELOPMENT.md)).
- New shared logic goes into `core/camalert_core/` with a unit test. Player and Home Assistant specific code is
  tested on a real receiver / Kodi / Home Assistant before a release; nothing playing, settings restored. **Never mute
  the player** for a test (mute caused too many problems: a mute left behind, toggles that went the wrong way, chime
  and volume checks that tested nothing); keep the sound quiet with `test=1` (no chime) and the chime setting instead.
- API, MQTT topics, HA actions and blueprints must stay backwards compatible within a major version.
- Tests: `python3 -m pytest` (see `tests/README.md`). Packages: `python3 tools/build_ipk.py dist`,
  `python3 tools/build_kodi.py dist`.

## Layout (top level)

| Path | What |
|---|---|
| `core/camalert_core/`, `core/i18n/` | shared core (both players, plain Python 3.8+) and the master translation catalogue |
| `players/enigma2/CamAlert/` | Enigma2 plugin |
| `players/kodi/service.camalert/`, `players/kodi/repository.camalert/` | Kodi add-on and Kodi repository add-on |
| `players/androidtv/` | Android TV / Fire TV app (Gradle: `api/` pure Kotlin + contract tests, `app/` Android) |
| `custom_components/camalert/` | Home Assistant integration (stays in the root for HACS) |
| `homeassistant/` | blueprints (`blueprints/README.md`: frozen inputs) and the REST-command package |
| `players/enigma2/po/` | Enigma2 translations, generated from `core/i18n/` (never edit by hand) |
| `extras/grafana/` | Grafana dashboard |
| `docs/` | documentation ([docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)) |
| `tools/` | `build_ipk.py`, `build_feed.py`, `build_kodi.py` (packages), `ci.sh` + `ci_pick_runner.py` (CI), `check_private.py` + `check_images.py` (privacy), `docs.py` (generated docs), `apk_listing.py` (golden APK listing), `export_contract.py` (contract and core data as JSON for the Android TV player), `i18n/i18n.py` (translations), `strings.py`, `msgfmt.py`, `make_chime.py`, `make_brand.py` (Home Assistant brand icons), `readme_images.py`, `e2_api_snapshot.py`, `kodi_api_snapshot.py`, `kodi_jsonrpc_snapshot.py`, `e2e/run.py` (end-to-end runner on real players, #35) |
| `tests/` | all tests; `tests/_paths.py` is the only file that knows where things live |

## CI (Forgejo Actions, `.forgejo/workflows/tests.yml`)
- Every area runs `sh tools/ci.sh <area>` (`lint`, `core`, `unit`, `build`, `privacy`, `ha`, `androidtv`); run the same locally before a push.
  `androidtv` (#64) runs only on the workstation runner; in the NAS fallback it is skipped with a message.
  `ha` = Home Assistant runtime tests (#33, `tests/homeassistant/`): oldest (hacs.json) and latest Home Assistant on the
  workstation, latest only in the NAS fallback; integration branch coverage >= 90 %.
- Runner choice (#54): heavy jobs run on the **workstation runner** and fall back to the NAS runner (`truenas`) only
  when no workstation runner is online. The NAS disks cannot take a burst of parallel jobs.
  - `pick-runner` (tiny, on `truenas`, no installs) runs `tools/ci_pick_runner.py`: it asks
    `GET /api/v1/user/actions/runners` with the secret `RUNNER_STATUS_TOKEN` (personal token, scope `read:user`;
    the automatic workflow token cannot see runners) and outputs `runner` + `mode`. Preferred labels, best first:
    `werkstation skills-werkstation` (an idle runner wins over a busy one; a busy one still wins over the NAS).
    No secret or an API error = fallback.
  - `parallel`: one job per area, `runs-on: ${{ needs.pick-runner.outputs.runner }}`.
  - `sequential` (fallback): one job runs every area in turn on the NAS (one container, one package install).
  - `gate` (light, on `truenas`) is the one required check and accepts either mode.
- Test the fallback without stopping the workstation: Actions › tests › Run workflow › `force_runner` = `truenas`
  (or `werkstation` to force the workstation). `tests/test_ci.py` checks the picker and the workflow structure:
  a new area needs a job, a step in `sequential`, a case in `tools/ci.sh` and an entry in the gate.
- If the workstation goes offline after `pick-runner` chose it, its jobs wait in the queue until it is back
  (Forgejo has no queue timeout); cancel the run and start it again with `force_runner` = `truenas`.
- No `actions/cache`: the runner cache server is not reachable from the NAS job containers (timeouts).

## Release
1. Raise the version in `players/enigma2/CamAlert/__init__.py`, `custom_components/camalert/manifest.json` (+
   `INTEGRATION_VERSION` in `api.py`), the Kodi `service.camalert` `addon.xml` and `__version__`, and the example `.ipk`
   download in `docs/players/enigma2.md` (tests check they agree); in
   `CHANGELOG.md` move the *Unreleased* items into `## [X.Y.Z] - YYYY-MM-DD` (real date, user-facing wording, grouped
   by player/area) and add its compare link at the bottom.
2. Tag `vX.Y.Z` and push; GitHub Actions (`.github/workflows/release.yml`) checks tag = `__version__` and a dated
   CHANGELOG section, runs hassfest, the HACS check and the tests, builds the `.ipk`, the Kodi add-on and repository
   zips and the Home Assistant zip, creates the release (notes = that CHANGELOG section) and publishes GitHub Pages
   (Settings › Pages › Source: GitHub Actions): the Kodi repository, the opkg feed (`Packages.gz`,
   `camalert-feed.conf`) and a start page (`index.html` from the template `.github/pages/index.html`, no external
   resources) in one site, **latest release only**. The Kodi add-on version is always `__version__`. No
   Android TV APK until release signing exists (#65).
3. Community files for GitHub: `CONTRIBUTING.md`, `SECURITY.md` (private vulnerability reporting),
   `CODE_OF_CONDUCT.md`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` (`tests/test_community.py`).
