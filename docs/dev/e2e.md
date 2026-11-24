# End-to-end tests on real players

`tools/e2e/run.py` runs a few CamAlert scenarios on a real Enigma2 receiver or Kodi player and puts everything
back afterwards (#35). It runs on demand from a computer in your own network, **never on GitHub** and never in CI.
The unit tests of the runner itself (`tests/e2e/`) use fake devices only.

## Device profiles

Copy `tools/e2e/devices.example.yaml` to `tools/e2e/devices.local.yaml` and describe your players. That file is
git-ignored (a test checks this), so addresses stay on your computer. Secrets are never in the file: only the
names of environment variables (`token_env`, `openwebif_password_env`, ...); the runner refuses keys such as
`token` or `password`.

| Key | What |
|---|---|
| `type` | `enigma2` or `kodi` |
| `host`, `camalert_port` | the player and its CamAlert API port (8099) |
| `allowed_hours` | e.g. `"10:00-22:00"`: outside this window the player is skipped |
| `quiet`, `sleep_hours` | a quiet player (bedroom) also needs `--allow-quiet` and is never used in its sleep hours |
| `watching` | `confirm` (asks, or `--nobody-watching <name>`) or `ha` (`ha_media_player` must be idle/off) |
| `cameras` | `fake` (Enigma2 with `ssh`: demo cameras on the receiver, screenshots, PTZ) or `real` |
| `ssh` | host alias from `~/.ssh/config` (key login) |
| `jsonrpc` | Kodi: `tcp` (port 9090), `http` (8080, user/password from `*_env`) or `ssh` |
| `ha_device_id` | the player's CamAlert device in Home Assistant, for the `ha` scenario |
| `scenarios`, `timeout` | default scenario list, global time limit in seconds (600) |

The `ha` section has `url` and `token_env` (default `HA_TOKEN`, a long-lived token). Without a token the `ha`
scenario is skipped.

## Running

```sh
python3 tools/e2e/run.py --device living_room --dry-run          # preconditions + snapshot, changes nothing
python3 tools/e2e/run.py --device living_room --scenario show,mosaic
python3 tools/e2e/run.py --restore last                          # undo a run that did not finish
```

Scenarios: `show` (photo window), `strip` (multi-camera window), `mosaic`, `tour` (the camera changes), `dnd`
(a normal request is ignored), `ptz` (only against the fake camera) and `ha` (Home Assistant `camalert.show` and
`camalert.hide` end to end).

## Safety

1. **Preconditions**, any failure skips the player (never forced): inside `allowed_hours`; quiet players only with
   `--allow-quiet` and never in `sleep_hours`; not recording and no timer within 30 minutes; nobody watching
   (receiver in standby and `--wake`, Home Assistant reports the media player idle, an interactive confirmation or
   `--nobody-watching <name>`); Kodi: nothing playing.
2. **Snapshot** of channel, volume, mute, standby, do not disturb and the saved CamAlert settings (Kodi: volume, mute,
   window) to `reports/state/` before the first change; every later change is written there first.
3. **Mute and verify.** OpenWebif `/api/vol?set=mute` *toggles*: the runner only sends it when the receiver is not
   muted and reads the state back; if it is not muted then, the volume goes to 0. No verified silence, no scenario.
4. **Nothing that rings or reaches other systems.** On Enigma2 the runner sets (through OpenWebif `saveconfig`)
   chime off, no Home Assistant webhook, no cooldown/time/playing rules, Frigate and Foscam triggers off. It does
   not use a temporary API token: that would block Home Assistant. Requests use priority *normal* and send
   `test=1` (#62: a player that knows the test flag plays no chime and tags the event; older players ignore it). Kodi:
   add-on settings cannot be changed over JSON-RPC, so a Kodi player whose chime is *all* is skipped.
5. **Fake cameras** (`cameras: fake`): the fake go2rtc (`tests/fakes/go2rtc.py`) and a fake Foscam PTZ camera
   (`tools/e2e/fake_ptz.py`) run on the receiver on `127.0.0.1`; the camera devices file is moved aside on the
   receiver itself (never copied off it) and replaced by the fake camera, so PTZ can never move a real camera.
6. **Restore in `finally`**: hide, devices file, fake processes stopped, settings, do not disturb, channel,
   volume and mute (read back), standby. `--restore last` does the same from the state file after a crash.

## Checks and report

State first (`/camalert/status`, OpenWebif, Kodi `GUI.GetProperties`), then OSD screenshots
(`/grab?format=png&mode=osd`: no video layer, so no TV picture) with fake cameras only. There are no pixel diffs:
every demo camera has its own solid colour, and the runner compares where each colour is with the geometry from
`camalert_core.layout` (photo window, multi-camera window, mosaic grid), with tolerances.

The report goes to `reports/<run>/` (git-ignored): `report.json`, `junit.xml`, `report.html` and the screenshots.
Addresses, ssh names, secrets and real camera names (shown as `cam1`, `cam2`) are replaced, and the text is checked
with the patterns of `tools/check_private.py` and the private denylist. Look at screenshots before you share one.
