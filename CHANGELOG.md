# Changelog

## Unreleased
- Core (#9): UniFi Protect as a trigger source without Home Assistant: devices-file type `unifi`
  (`name|unifi|host[:443]|user|password`, a local "View Only" Protect user), read-only client (login, bootstrap,
  events, snapshots) and `triggers/unifi.py` (ring, person, vehicle, animal, package, motion). The players and
  their settings follow in separate issues.
- Blueprint *CamAlert - doorbell on the players and an LG webOS TV* (#16): as the doorbell blueprint, plus a
  notification with an optional snapshot on an LG TV through the LG webOS TV integration (only while the TV is on).
- API (#63): `/camalert/status` reports `screen` (`none`, `photo`, `strip`, `notification`, `live`, `mosaic`,
  `tour`); capability `screen`. Enigma2: `hide` (and Home Assistant `camalert.hide`) now also closes the mosaic and
  the tour, also when several are stacked.
- API (#62): `test=1` on any request makes it a test: no doorbell chime, the event gets the source *Test request*
  (translated); capability `test`. The end-to-end runner always sends it.
- Doorbell chime (#20): a muted player plays no chime (Enigma2 plays it through ALSA, which the receiver's mute does
  not reach; `chime skipped` in the log).
- Enigma2: after the go2rtc server or camera source changes, cameras of the new source are no longer refused as
  unknown for up to a minute.
- Kodi: diagnostics show the operating system instead of *Busy* (#59); *Event list*, *Live view* and *Notification*
  as in the glossary instead of *Recent events*, *Switch to live stream* and *Notification only* (#60, #56).
- End-to-end runner: checks `screen` while a screen is open and `none` after `hide`; EXIT cleanup is only a failure
  for players older than 1.0; the multi-camera window waits for its pictures like the photo window.
- Android TV / Fire TV player without Kodi (#64, in development): `players/androidtv/` (Kotlin, Android 7.1+): the
  same HTTP API v1 (all contract rows pass on the JVM), MQTT + Home Assistant discovery (model *Android TV*), photo
  window, multi-camera window, notification, mosaic, tour and live view (Media3, muted by default) as overlays over
  any app, leanback settings from the shared schema, translations from the master catalogue. CI area `androidtv`
  (workstation runner only). Home Assistant shows the device model *Android TV*.
- Enigma2 UI findings (#56): photo and multi-camera window titles stay on one line (font fitted to the window,
  key hints in their own strip at the bottom); mosaic and multi-camera tiles keep the camera name on *Camera not
  reachable*; the event list shows GREEN *Play clip* only for events with a clip; texts come only from CamAlert's own
  catalogue (English images no longer turn *Normal* into *normal*); *Do not disturb blocks* values *Normal priority* /
  *Normal and high priority* (like Kodi); display modes *Live view* / *Notification* (glossary).
- End-to-end runner `tools/e2e/run.py` (#35): show, multi-camera window, mosaic, tour, do not disturb, PTZ against a
  fake camera and Home Assistant calls on a real receiver or Kodi player, with preconditions, verified mute, state
  snapshot and restore (`--restore last`), OSD geometry checks with demo cameras and a local report (`docs/dev/e2e.md`).
- Docs reorganised (#24, #47): `docs/index.md` with `user/`, `players/` (`enigma2.md`, `kodi.md`), `integrations/`
  (Home Assistant, MQTT, Frigate, HTTP API, monitoring) and `dev/`; generated pages from core: remote keys (key map),
  glossary (with translations) and every setting (schema) (`tools/docs.py`); "player" instead of "receiver" where Kodi
  is meant; Kodi 19 or newer everywhere; new screenshots without camera or TV content. `tests/test_docs.py` checks
  links, anchors, generated blocks and wording.
- Tour: GREEN or PLAY switches to live view on both players (Enigma2 had GREEN, Kodi PLAY).
- Kodi: OK closes the mosaic, like BACK (UI guideline: *OK or BACK*, #58).
- Docs: Kodi screenshots (photo window, multi-camera window, mosaic, tour, settings, event list, diagnostics) with demo cameras and the Kodi screenshot procedure (#57).
- Privacy (#8): `tools/check_images.py` refuses images with metadata (EXIF, GPS, XMP, ICC, text) in CI.
- Enigma2: settings screen in sections in the order of the schema (General, Display, Rules, Triggers with Frigate
  and Foscam, Camera control, Home Assistant, API, Channel list, Log and diagnostics); settings follow the image's
  setup level (simple = basic settings, MENU = *Show all settings*); the skin's own Setup layout is used when it has
  one (`description` / `footnote`); title *CamAlert* without key hints; HELP lists the keys on the settings, tour,
  mosaic, diagnostics and event list screens; BLUE *Test* asks before it saves; YELLOW is *Create channel list*;
  Cancel also undoes camera names, orientation, refresh and mosaic chosen in the lists (#40).
- Enigma2: mosaic, multi-camera window, tour and photo window show a dimmed *Camera not reachable* tile instead of
  a frozen or black picture; notification mode shows a small window with a snapshot, the title (who/what) and the
  priority, like Kodi (a text pop-up only without snapshot address) (#49).
- Blueprints (#45): inputs frozen for 1.x – same keys, order and defaults in every blueprint (trigger, `players`,
  `camera`/`cameras`, `mode`, `seconds`, `label`, conditions, `action`; `homeassistant/blueprints/README.md`);
  `receivers` became `players`, doorbell `triggers_in` became `doorbell`, new `label` (doorbell, motion, alarm) and
  `mode` (alarm), glossary option labels. Re-save automations made from an older copy.
- Home Assistant: `camalert.show` with a list of cameras from a template (motion blueprint with several cameras
  typed in) sent the text `['a', 'b']` and the player refused it; lists now stay lists.
- Home Assistant runtime tests (#33): the integration runs in a real Home Assistant (oldest supported 2025.1 and
  latest) against a fake player that answers like Enigma2 and Kodi (contract table); CI area `ha`, integration
  branch coverage 96 %.
- Home Assistant (#44): player-neutral texts (Enigma2 receiver or Kodi), device model from `/camalert/status`
  platform, field descriptions in the config flow, *Check certificates* on by default (and it now really checks:
  before, the shared session never verified), a certificate error and unexpected errors shown in the form,
  *Reconfigure* (address, port, HTTPS, token of the same player), icons in `icons.json`, sensor *Camera on screen*
  as an enum with a translated *Nothing* state, translated action errors (`HomeAssistantError` with translation key)
  for actions, buttons and the switch, entities only for capabilities the player has, diagnostics with platform,
  version, API and capabilities and with address, ids and snapshot URLs redacted; the `camalert_button` event has
  `player` (`receiver` kept). Works with the device registry of Home Assistant 2026.x.
- Enigma2: key hints of the photo window, multi-camera window, mosaic, tour and camera control are built from the
  core key map and translated (`camalert_core.present`, ◀ ▶ with the image's fallback font, otherwise < >); the event
  list stores reason codes and shows source, priority, result and reason translated, dates in the menu
  language's format (#41).
- Kodi: a camera that does not answer is shown as a dimmed tile with *Camera not reachable* in the photo window,
  the multi-camera window, the mosaic and the tour, instead of a frozen or black picture (#49).
- Enigma2: settings follow schema version 2 (#39): *Doorbell chime* off / doorbell and alarm / every request,
  *Not while playing* off / video / all (replaces the yes/no *Not while playing a recording or video*), Frigate and
  Foscam priority with *Alarm*, own display mode and duration for Frigate and Foscam, Foscam check interval
  1-60 s, keys `foscam_enabled` / `foscam_priority`. Settings saved by an older version are migrated on start
  (`schema.migrate()`); an existing install keeps polling its Foscam cameras, new installs start with it off.
- Kodi: key hints (photo window, camera control, live bar, tour, mosaic) and the event list come from the core
  (`camalert_core.present`) and are translated; the photo window shows its hint on a strip under the picture, the
  event list shows date (Kodi's region format) and reason; events store reason codes (#41).
- Kodi: settings have levels from the schema (basic / standard / advanced), so Kodi's settings level button hides
  the expert settings; title size *large* works on every skin (it used `font30`, which Estuary does not have):
  small/large pick a font of the current skin, normal stays `font13` (#46).
- Kodi: the photo window shows *camera not reachable* again when a camera stops answering (the active snapshot
  feeder never reported it); one thread per tile, so a slow camera no longer holds up the others; dead duplicate
  `PtzMode`/`Feeder` classes removed (#51, #46).
- Kodi: settings follow schema version 2 (#39): duration sliders in steps of 5 s, live volume in steps of 10 %,
  keys `live_return` and `refresh` (settings saved under `live_resume` / `refresh_map` are moved on start),
  own labels *Frigate objects*, *Frigate priority*, *Foscam priority*.
- HTTP API version 1, one implementation for every player (`camalert_core.api`, #5): actions with `POST`
  (`GET` still works, deprecated: `Deprecation` header, logged once), token in the `X-CamAlert-Token` header
  (`?token=` deprecated, always redacted), `/camalert/status` has `platform`, `api_version`, `capabilities`,
  `min_ha_version` and `mqtt` on both players, parameters are validated (`400` for invalid camera names, mode,
  priority, `on`, PTZ move), `405` for other methods, `log`/`events`/`metrics` never answer the internet
  without a token, the webhook must point into the local network.
- Home Assistant: actions are sent with `POST` + token header to players with API version 1 (older ones: `GET`),
  services check the player's capabilities; the YAML package uses `POST` + header too.
- Kodi: the mosaic opened with a TypeError on every Kodi version (`ControlLabel(shadowColor=...)` does not exist);
  the camera names now sit on a dark strip instead (#25).
- Enigma2: in PTZ mode YELLOW always left PTZ mode; now only EXIT and the configured PTZ key do, as documented (#42).
- One remote-key map per player in the core (`camalert_core.keymap`); the Enigma2 and Kodi key handlers use it (#42).
- One settings schema for both players (`camalert_core.schema`, schema version 1): the Enigma2 settings and the
  Kodi settings.xml are checked against it; the remaining differences are listed for #39 (#38, #7).
- Kodi: Foscam alarms appear in the event list with source "foscam" (was "api").
- Trigger sources (Frigate, Foscam) are a registry in the core (`camalert_core.triggers`): both players use the
  same parsing; new sources (UniFi Protect, ...) only need a class there (#6).

## 1.0.0 (unreleased)
- Enigma2 plugin: photo window (remote control: OK = live, LEFT/RIGHT = other camera), live view, notification; mosaic and camera tour; settings screen; camera channel list; go2rtc or direct camera mode; pause TV; active hours; ignore while recording; lower volume during live view; priorities normal / high / alarm (wake from standby); HTTP(S) API with token; MQTT with Home Assistant discovery.
- Home Assistant integration: UI setup, buttons per camera, sensor, actions show / mosaic / hide; blueprints for doorbell, motion and alarm.
- Kodi add-on `service.camalert` (Kodi 20+): same HTTP API, MQTT topics and Home Assistant integration as the plugin; photo window (also 2–4 cameras in one window), live view that returns to the film at the same position or to the same TV channel, notification with snapshot, mosaic, tour, do-not-disturb, Frigate and Foscam triggers, PTZ (ONVIF / Foscam), per-camera rotation and refresh interval; who/what label in the title, title size, doorbell sound, colour keys to Home Assistant, own redacted log (camalert.log, levels, remote syslog, `/camalert/log`), event list with snapshots and Frigate clip replay, diagnostics dialog, `/camalert/ptz`, `/camalert/webhook`, `/camalert/events`; Kodi repository for automatic updates.
- Translations: English, Dutch, German, French, Italian, Polish.
- Do not disturb (setting, API, MQTT switch, Home Assistant switch); "not while playing a recording or video".
- 2–4 cameras together in one corner window (layout automatic / below / next to each other / 2 x 2); Home Assistant
  `camalert.show` takes several cameras; motion blueprint can use it instead of the mosaic.
- Per camera: turn / mirror the snapshots (python3-pillow) and refresh interval.
- Frigate events via MQTT without Home Assistant (labels, name mapping, priority, clip playback from the event list).
- Foscam motion/sound alarms and PTZ (ONVIF and Foscam) from the remote, the API and Home Assistant (`camalert.ptz`);
  camera passwords in `/etc/enigma2/camalert_devices.conf`.
- Colour keys while a camera is on screen -> Home Assistant event (`camalert_button`, event entity, MQTT) + blueprint.
- Who/what label in the title ("Person · Front door").
- Own log `camalert.log` (levels, always redacted, optional remote syslog), event list with snapshots, diagnostics screen,
  `/camalert/log`, `/camalert/events`, Home Assistant diagnostics download.
- Update check (once a day, GitHub releases) and an opkg feed on GitHub Pages.
- Doorbell chime, picons for the camera channels, title size for the photo window.
- Robustness: cooldown per camera, substreams for live view (H.265/4K), IPv6 literal go2rtc addresses, "camera not
  reachable" in the photo window, no event snapshots when storage is low, rate limiting and a warning for an API
  reachable from outside without token, Prometheus `/camalert/metrics` + Grafana dashboard, recipes for other NVRs,
  doorbells, cloud cameras and home automation systems.
