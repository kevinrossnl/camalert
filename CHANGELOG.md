# Changelog

All notable changes to CamAlert are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and CamAlert uses
[Semantic Versioning](https://semver.org/): within a major version the HTTP API, MQTT topics, Home Assistant
actions and blueprint inputs stay backwards compatible.

## [Unreleased]

### Added

- **Kodi:** a **Choose per camera** button below each per-camera setting (camera names, turn or mirror image,
  refresh interval, cooldown per camera, live view substreams): pick a camera, then a value from a list, instead of
  typing `name=value|...`. **Choose cameras** ticks up to 9 mosaic cameras.
- **Android TV / Fire TV:** UniFi Protect events without Home Assistant, like on Enigma2 and Kodi: the same
  settings and rules, the console login in its own private storage (*Triggers › UniFi Protect console*), login
  backoff and diagnostics ([Android TV](docs/players/androidtv.md#settings)).
- **Home Assistant blueprints:** *Only when someone is home* (new optional input `presence`) in the doorbell, LG TV
  and motion blueprints: pick persons, device trackers or `zone.home`, empty = always (as before).
- **Home Assistant blueprints:** the doorbell and LG TV blueprints can also notify a phone (Companion app, new
  optional inputs `phone_notify` and `phone_camera`): the picture of the camera, tapping opens it; also when nobody is
  home.
- **Home Assistant blueprints:** new blueprint *CamAlert - doorbell on the players and other screens*: live view on
  a Chromecast / Google TV (stopped after the duration) and a notification with a picture on an Android TV / Fire TV.
- **Home Assistant blueprints:** the LG TV blueprint can show live view in the TV's browser and then return to the
  input or app the TV showed before (new optional input `webos_live_url`).

### Changed

- **Kodi:** the camera list (*Videos › Video add-ons › CamAlert*) keeps its own order – mosaic, tour, cameras,
  event list, settings – instead of *Sort by: Date*, and every item has a short description in the info panel.
- **Docs:** the [settings list](docs/user/settings.md) now also shows which settings the Android TV / Fire TV
  player has, and its own defaults (live volume 0).

## [1.1.0] - 2026-11-26

### Added

- **Kodi:** opening CamAlert from *Add-ons › Program add-ons* (or from a favourite) now shows a choice list – show
  mosaic, start tour, show a camera, event list, diagnostics, settings – instead of going straight to the settings.
- **Kodi:** CamAlert is now also a video add-on, so the cameras can be opened from the home screen:
  *Videos › Video add-ons › CamAlert* lists the mosaic, the tour, every camera with a fresh snapshot (live view,
  or the photo window from the context menu), the event list and the settings. Add any of them to your favourites.

### Changed

- **Kodi:** the install guide explains that an add-on installed from a zip is updated once through *Install from
  repository*; after that Kodi updates it by itself (Kodi 20 and newer only update from the repository an add-on came from).
- **Home Assistant:** CamAlert is now in the HACS default list. Install it with *Settings › Marketplace*: search for
  **CamAlert**. Adding the custom repository is only needed as a fallback.
- **Settings:** the help of *Access token* now says to send the token in the `X-CamAlert-Token` header; `?token=`
  in the address still works in 1.x but is deprecated.
- **Translations (Dutch):** the same word for the same thing everywhere (for example *Camera kiezen*,
  *beginstand*, *zelfondertekend certificaat*, *ontvanger*).

## [1.0.1] - 2026-11-24

### Fixed

- **Home Assistant:** the integration now lists its categories (*Security & safety › Cameras* and *Media &
  entertainment › TV & streaming*), so the HACS check no longer warns about missing categories.
- **Project website:** <https://kevinrossnl.github.io/camalert/> showed "404 Not Found". It now has a small start page
  with the install steps for each player (opkg feed for Enigma2, Kodi repository, HACS custom repository) and links
  to the latest release; no cookies, no tracking, nothing loaded from other sites.

### Changed

- **Enigma2:** the `.ipk` download example in the [install guide](docs/players/enigma2.md#install) points to the
  current release.
- Enigma2 plugin, Kodi add-on and Home Assistant integration are now version 1.0.1; nothing else changed for them.

## [1.0.0] - 2026-11-24

First public release. CamAlert shows your IP cameras on the TV of a **player**: an Enigma2 receiver or a Kodi
device (Kodi 19 or newer), controlled by Home Assistant, MQTT, Frigate, UniFi Protect or its HTTP API.

### Notable for users

- **No default go2rtc server.** A new install has an empty *go2rtc address* and makes no network calls until you
  enter yours; the diagnostics say *go2rtc address not set*. Earlier test builds used `http://192.168.1.10:1984`
  as default: if your go2rtc really runs there and you never changed it, enter it once. A saved address is kept.
- **HTTP API version 1:** actions are sent with `POST` and the access token in the `X-CamAlert-Token` header.
  `GET` requests and `?token=` in the URL still work in 1.x but are deprecated (the answer has a `Deprecation`
  header and the player logs it once); the Home Assistant integration and the YAML package already use `POST`.
- **Local network only by default:** the API only answers callers in private address ranges; `log`, `events` and
  `metrics` never answer the internet without a token. Set an access token if other people use your network.
- Blueprint inputs are frozen for 1.x. If you made automations from a test copy of the blueprints: `receivers` is
  now `players` and the doorbell input `triggers_in` is now `doorbell`; re-save those automations.

### Enigma2 plugin

- Photo window in a corner of the screen (four positions, three sizes) with a fresh picture every 1–2 seconds
  while you keep watching TV; OK = live view, ◀ ▶ = other camera.
- Multi-camera window with 2 to 4 cameras (automatic, below each other, next to each other or 2 x 2).
- Live view full screen that returns to your channel afterwards, notification with a snapshot, mosaic of up to 9
  cameras, camera tour, and a channel list with all your cameras (updated automatically, optional picons).
- Priorities *normal*, *high* (doorbell, always comes through) and *alarm* (can wake the receiver from standby);
  do not disturb, active hours, cooldown per camera, not during a recording, not while a video plays, pause TV
  meanwhile, lower volume during live view, doorbell chime (silent when the receiver is muted).
- Per camera: turn or mirror the picture and choose the refresh interval; substreams for live view (H.265/4K).
- Cameras through a go2rtc server or directly from the cameras; IPv6 addresses supported.
- Settings screen in sections (General, Display, Rules, Triggers, Camera control, Home Assistant, API, Channel
  list, Log and diagnostics) that follows the image's setup level, with HELP on every CamAlert screen.
- *Camera not reachable* tiles instead of a frozen or black picture.
- Event list (with snapshots and Frigate clip replay) and a diagnostics screen; own log `camalert.log` with levels
  and optional remote syslog, passwords and tokens always removed.
- Updates through the receiver's software update (opkg feed) and a daily update check against the GitHub
  releases.

### Kodi add-on

- Add-on `service.camalert` for **Kodi 19 or newer** (LibreELEC, CoreELEC, OSMC, Windows, Linux, Android) with the
  same features, HTTP API, MQTT topics and Home Assistant integration as the Enigma2 plugin: photo window,
  multi-camera window, live view that resumes your film at the same position or returns to the same TV channel,
  notification, mosaic, tour, do not disturb, triggers, camera control, colour keys, event list and diagnostics.
- Settings with levels (basic / standard / advanced), so Kodi's settings level hides the expert settings; title
  sizes that work on every skin.
- CamAlert repository add-on: install it once and Kodi updates CamAlert by itself.
- The default camera password is no longer kept in Kodi's `settings.xml`: a password typed in *Camera password
  (default)* moves into `devices.conf` and the field is emptied (passwords saved by test builds move on the first
  start); **Change camera password (default)** shows whether one is stored and changes or removes it.

### Android TV / Fire TV app (preview, not part of the 1.0.0 release)

- A third player without Kodi for Android TV and Fire TV (Android 7.1 / Fire OS 6 or newer) is in development in
  `players/androidtv/` ([status](docs/players/androidtv.md)). It has the same HTTP API, MQTT topics and Home
  Assistant integration. There is no release APK yet: only unsigned debug builds for testers, until release
  signing is set up (#65).

### Home Assistant integration and blueprints

- Integration set up in the UI (no YAML), installable through HACS as a custom repository; Home Assistant 2025.1 or
  newer. Buttons per camera, a *Camera on screen* sensor, a do-not-disturb switch, a colour-key event entity and
  only the entities your player supports; *Reconfigure* for address, port, HTTPS and token.
- Actions `camalert.show` (one or several cameras), `camalert.mosaic`, `camalert.hide` (also closes the mosaic and
  the tour) and `camalert.ptz`; translated error messages; redacted diagnostics download.
- Ready-made blueprints: doorbell or person, motion when armed or at set times, alarm, remote button (colour keys,
  for example GREEN opens the gate), show a camera, and doorbell on the players plus a notification on an LG webOS
  TV. For the LG TV use *Snapshot URL* for a small picture: the TV refuses pictures over 100 KB.
- A REST-command package for setups without the integration, and a zip of the integration on every release for a
  manual install without HACS. The integration has its own icon.

### Triggers, API and other systems

- MQTT with Home Assistant discovery (no integration needed).
- Frigate events straight from MQTT, without Home Assistant (labels, name mapping, priority, clip replay).
- UniFi Protect events without Home Assistant on the Enigma2 plugin and the Kodi add-on (ring, person, vehicle,
  animal, package, motion) through a local view-only Protect user, with rules per event type and per camera
  (priority, display mode, duration) and a *Log only* display mode. A refused or rate-limited login (HTTP 401/403/429)
  is not retried at every check: the login backs off from 30 s to 15 min (honouring *Retry-After*), the session is
  kept between checks and the diagnostics show the next login attempt.
- Foscam motion and sound alarms; camera control (PTZ) for ONVIF and Foscam cameras from the remote, the API and
  Home Assistant.
- HTTP API for Node-RED, openHAB and scripts: `/camalert/status` reports the platform, API version, capabilities
  and what is on screen; `test=1` marks a request as a test (no chime).
- Prometheus metrics (`/camalert/metrics`) and a Grafana dashboard.

### Security and privacy

- Access token compared in constant time, rate limiting, warning when the API is reachable from outside without a
  token, webhook only into the local network, certificate checks on by default in Home Assistant.
- Camera passwords only in the devices file (readable for root only on Enigma2, for Kodi's user only on Kodi), never
  in settings or logs – on Kodi the default camera password too (#55); logs, diagnostics and the Home Assistant
  diagnostics download are redacted. Where every password and token is stored:
  [docs](docs/integrations/api.md#where-passwords-and-tokens-are-stored).
- Report vulnerabilities privately: see [SECURITY.md](SECURITY.md).

### Translations

- Every player and the Home Assistant integration in English, Dutch, German, French, Italian and Polish, from one
  master catalogue with a shared glossary ([Translating](docs/dev/translating.md)).

[Unreleased]: https://github.com/kevinrossnl/camalert/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.1.0
[1.0.1]: https://github.com/kevinrossnl/camalert/releases/tag/v1.0.1
[1.0.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.0.0
