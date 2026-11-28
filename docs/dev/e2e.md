# End-to-end tests on real players

`tools/e2e/run.py` runs a few CamAlert scenarios on a real Enigma2 receiver, Kodi player or Android TV / Fire TV
player and puts everything
back afterwards (#35). It runs on demand from a computer in your own network, **never on GitHub** and never in CI.
The unit tests of the runner itself (`tests/e2e/`) use fake devices only.

## Device profiles

Copy `tools/e2e/devices.example.yaml` to `tools/e2e/devices.local.yaml` and describe your players. That file is
git-ignored (a test checks this), so addresses stay on your computer. Secrets are never in the file: only the
names of environment variables (`token_env`, `openwebif_password_env`, ...); the runner refuses keys such as
`token` or `password`.

| Key | What |
|---|---|
| `type` | `enigma2`, `kodi` or `androidtv` |
| `host`, `camalert_port` | the player and its CamAlert API port (8099) |
| `allowed_hours` | e.g. `"10:00-22:00"`: outside this window the player is skipped |
| `quiet`, `sleep_hours` | a quiet player (bedroom) also needs `--allow-quiet` and is never used in its sleep hours |
| `watching` | `confirm` (asks, or `--nobody-watching <name>`) or `ha` (`ha_media_player` must be idle/off) |
| `cameras` | `fake` (demo cameras on the player itself) or `real`. Enigma2 with `ssh`: screenshots and PTZ. Kodi with `ssh` (CamAlert 1.3+): no screenshots, no PTZ. Android TV with `restore_server`: screenshots, no PTZ |
| `ssh` | host alias from `~/.ssh/config` (key login) |
| `jsonrpc` | Kodi: `tcp` (port 9090), `http` (8080, user/password from `*_env`) or `ssh` |
| `ha_device_id` | the player's CamAlert device in Home Assistant, for the `ha` scenario |
| `scenarios`, `timeout` | default scenario list, global time limit in seconds (600) |
| `resume_file` | Kodi: a short test film on the player (path or URL), for the `kodi_resume` scenario |
| `adb`, `adb_port` | Android TV: the adb binary (`adb`) and the device's adb port over the network (5555; enable network debugging on the device) |
| `restore_server` | Android TV with `cameras: fake`: the app's own go2rtc address, sent back after the run (the app's settings are private, so the runner cannot read it) |

The `ha` section has `url` and `token_env` (default `HA_TOKEN`, a long-lived token). Without a token the `ha`
scenario is skipped. The optional `mqtt` section (`host`, `port`, `user_env`, `password_env`, `prefix`) is the
broker the players use; without it the `mqtt` scenario is skipped.

## Running

```sh
python3 tools/e2e/run.py --device living_room --dry-run          # preconditions + snapshot, changes nothing
python3 tools/e2e/run.py --device living_room --scenario show,mosaic
python3 tools/e2e/run.py --restore last                          # undo a run that did not finish
```

Scenarios: `show` (photo window), `strip` (multi-camera window), `mosaic`, `tour` (the camera changes), `dnd`
(a normal request is ignored), `ptz` (only against the fake camera) and `ha` (Home Assistant `camalert.show` and
`camalert.hide` end to end).

More scenarios (#77), only when named with `--scenario` or in the profile's list:

| Scenario | What it checks | Restores |
|---|---|---|
| `alarm_wake` | Enigma2: an `alarm` request wakes the receiver from standby (setting `alarm_wake` on for the scenario). Never on a `quiet` device | standby / on as before, `alarm_wake` |
| `chime_muted` | a test request is tagged `test` in the event list and the chime setting rings no normal request | nothing changed |
| `mqtt` | a show command on `camalert/<id>/show` (as Home Assistant's MQTT buttons send it) reaches the player | nothing changed |
| `settings` | window position and size over `/camalert/settings` (#84), an invalid value is refused, the next window uses them (OSD geometry with fake cameras) | position and size |
| `kodi_resume` | Kodi: the `resume_file` film plays on after a CamAlert window | the film is stopped |

The CI runs every scenario against the fake devices (`tests/e2e/test_e2e_v13.py`), never against a real one.

## Safety

1. **Preconditions**, any failure skips the player (never forced): inside `allowed_hours`; quiet players only with
   `--allow-quiet` and never in `sleep_hours`; not recording and no timer within 30 minutes; nobody watching
   (receiver in standby and `--wake`, Home Assistant reports the media player idle, an interactive confirmation or
   `--nobody-watching <name>`); Kodi and Android TV: nothing playing (Android: no media session in state playing;
   a screen that is off counts as standby and needs `--wake`).
2. **Snapshot** of channel, volume, mute, standby, do not disturb and the saved CamAlert settings (Kodi: volume, mute,
   window) to `reports/state/` before the first change; every later change is written there first.
3. **Never mute** (#102). Muting caused too many problems (a mute left behind, OpenWebif `set=mute` *toggles*, checks
   that tested nothing), so the runner does not touch volume or mute. Silence comes from step 4 (`test=1`, chime off).
   The snapshot still has volume and mute: the restore puts them back only when they differ.
4. **Nothing that rings or reaches other systems.** On Enigma2 the runner sets (through OpenWebif `saveconfig`)
   chime off, no Home Assistant webhook, no cooldown/time/playing rules, Frigate and Foscam triggers off. It does
   not use a temporary API token: that would block Home Assistant. Requests use priority *normal* and send
   `test=1` (#62: a player that knows the test flag plays no chime and tags the event; older players ignore it). Kodi:
   add-on settings cannot be changed over JSON-RPC, so a Kodi player whose chime is *all* is skipped.
5. **Fake cameras** (`cameras: fake`): the fake go2rtc (`tests/fakes/go2rtc.py`) and a fake Foscam PTZ camera
   (`tools/e2e/fake_ptz.py`) run on the receiver on `127.0.0.1`; the camera devices file is moved aside on the
   receiver itself (never copied off it) and replaced by the fake camera, so PTZ can never move a real camera.
   **Kodi** (CamAlert 1.3+, `ssh`): the fake go2rtc runs on the Kodi device, the runner reads the add-on's go2rtc
   address from its settings.xml, points the add-on at the fake with `/camalert/setup` (#122) and sends the old
   address back the same way (checked in settings.xml). **Android TV** (CamAlert 1.3+): the fake go2rtc of
   `players/androidtv/testing/fake_go2rtc_on_device.py` runs on the device (adb), and `/camalert/setup` switches to it
   and back to `restore_server`.
6. **Nothing left on screen.** Before the run the receiver's OSD must be clear (no menu or dialog: someone may be
   using it). After every scenario and in the restore, the runner looks at the OSD (only counted, never stored) and
   closes screens that are still open with EXIT. Every scenario checks `/camalert/status` `screen` while its screen
   is open and `none` after `hide` (#63); that check fails when `hide` leaves something open. A later EXIT cleanup is
   then only a note. With a player older than 1.0 (no `screen`), the EXIT cleanup itself counts as a failed check.
7. **Restore in `finally`**: hide, close leftover screens, devices file, fake processes stopped, settings, do not disturb, channel,
   volume and mute (read back), standby. `--restore last` does the same from the state file after a crash.
   Enigma2 keeps settings changed through OpenWebif `saveconfig` in memory only, but writes them to
   `/etc/enigma2/settings` whenever it saves (entering standby does, e.g. in `alarm_wake`). With `ssh` the runner
   therefore also compares the CamAlert lines of that file with the restored settings and rewrites only those lines
   when they differ (#77, found on a real receiver). Without `ssh` the file follows at Enigma2's next save.

## Checks and report

State first (`/camalert/status`, OpenWebif, Kodi `GUI.GetProperties`), then OSD screenshots
(`/grab?format=png&mode=osd`: no video layer, so no TV picture) with fake cameras only. There are no pixel diffs:
every demo camera has its own solid colour, and the runner compares where each colour is with the geometry from
`camalert_core.layout` (photo window, multi-camera window, mosaic grid), with tolerances.

Android TV screenshots come from `adb exec-out screencap -p` (fake cameras only); only the geometry checks use them,
and they stay in the git-ignored report folder.

The report goes to `reports/<run>/` (git-ignored): `report.json`, `junit.xml`, `report.html` and the screenshots.
Addresses, ssh names, secrets and real camera names (shown as `cam1`, `cam2`) are replaced, and the text is checked
with the patterns of `tools/check_private.py` and the private denylist. Look at screenshots before you share one.

## No scheduled runs

The runner is started by hand. A nightly run on the workstation runner was considered (#77) and dropped: every run
switches real TVs on or shows windows on them, the allowed hours of a household do not match a fixed schedule, and
the CI already runs every scenario against the fake devices on every push. Run it after a release on the players
you test on.
