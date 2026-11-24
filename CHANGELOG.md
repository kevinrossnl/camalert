# Changelog

## 1.0.0 (unreleased)
- Enigma2 plugin: photo window (remote control: OK = live, LEFT/RIGHT = other camera), live view, notification; mosaic and camera tour; settings screen; camera channel list; go2rtc or direct camera mode; pause TV; active hours; ignore while recording; lower volume during live view; priorities normal / high / alarm (wake from standby); HTTP(S) API with token; MQTT with Home Assistant discovery.
- Home Assistant integration: UI setup, buttons per camera, sensor, actions show / mosaic / hide; blueprints for doorbell, motion and alarm.
- Kodi add-on `service.camalert` (Kodi 20+): same HTTP API, MQTT topics and Home Assistant integration as the plugin; photo window (also 2–4 cameras in one window), live view that returns to the film at the same position or to the same TV channel, notification with snapshot, mosaic, tour, do-not-disturb, Frigate and Foscam triggers, PTZ (ONVIF / Foscam), per-camera rotation and refresh interval; Kodi repository for automatic updates.
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
