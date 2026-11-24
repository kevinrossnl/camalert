# Changelog

## Unreleased
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
