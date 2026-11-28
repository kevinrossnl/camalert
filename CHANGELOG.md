# Changelog

All notable changes to CamAlert are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and CamAlert uses
[Semantic Versioning](https://semver.org/): within a major version the HTTP API, MQTT topics, Home Assistant
actions and blueprint inputs stay backwards compatible.

## [Unreleased]

### Added

- **All players and Home Assistant:** a spoken announcement with a camera (#89). `camalert.show` has the fields
  `announce` (text), `tts` (TTS engine) and `language`: Home Assistant makes a WAV with its text-to-speech and the
  player plays it after the chime, when the new setting *Spoken announcement* allows it (default: doorbell and
  alarm). The Android TV app can also speak the text with Android's own speech engine. The doorbell blueprint has
  the inputs `announce`, `announce_speakers` (speak it on media players too) and `tts_engine`.
- **All players:** several go2rtc servers at once (#15). The main server stays in *go2rtc address*; *More go2rtc
  servers* lists the others with an optional prefix (`garden=http://192.168.1.20:1984`), whose cameras are called
  `garden.<name>`. Names of the main server do not change. See [cameras](docs/user/cameras.md#several-go2rtc-servers).
- **Home Assistant:** a doorbell without an automation. Choose the doorbell (event entity or binary sensor) and an
  optional camera in the player's options (**Configure**): every ring shows the camera on that player with priority
  high (#90).
- **Home Assistant:** phone notifications in the doorbell, motion and alarm blueprints: several phones, the camera
  picture, the buttons **Show on TV** and **Do not disturb 1 h**, and an optional critical notification (on by
  default for the alarm). Motion now also reaches the phone when nobody is home (#128).
- **Home Assistant:** an **Install** button on the update entity of every player (#126). The player downloads the
  release from CamAlert's own GitHub release (fixed address), only a newer version, checked against the new
  `SHA256SUMS` of the release, and reports the progress. Enigma2 installs in standby without a (coming) recording
  and restarts its GUI quietly; Kodi installs when nothing plays; Android TV opens the system installer, to be
  confirmed on the TV. New setting *Allow updates from Home Assistant* (on), new API route `POST /camalert/update`.
- **Kodi:** smooth **video in the photo window** (#129). When Kodi plays nothing, the photo window plays the camera's
  live stream as video instead of a picture every second; Kodi stays where it is. The new setting *Video in the photo
  window* can also **pause what plays**: a film or live TV stops for the window and plays on from where it was
  afterwards (an alarm always does this unless the setting is off). Music, turned cameras and a stream that does
  not start keep the pictures.
- **Android TV:** cameras without go2rtc (#124): *Cameras via: Directly from the cameras* with a camera list in the
  app (the lines of the other players' camera file, kept in private storage). Snapshot urls with a login work with
  Basic and Digest; a camera without snapshot url opens live view.
- **Android TV:** the event list is a list now (#124): OK shows the camera of an event, and with a Frigate address an
  event from Frigate offers *Play Frigate clip* in a full-screen player.
- **Docs:** screenshots of the Android TV app with demo cameras (photo window, multi-camera window, mosaic, tour,
  settings) in [Android TV and Fire TV](docs/players/androidtv.md#what-you-see) (#69).

### Security

- **Home Assistant and all players:** colour keys are signed (#82). The integration gives every player a fresh secret
  with the webhook; each key press carries a time, a one-time number and an HMAC, and Home Assistant accepts it only
  once and only while it is fresh. Something else on the network can no longer fake or replay a key press (GREEN
  may open a gate). Players from before 1.4 keep working; their presses arrive with `verified: false`.

### Fixed

- **Android TV:** camera control via ONVIF and UniFi Protect's "retry later" with a date no longer crash the app on
  Android 7 (Fire OS 6): they used Java APIs that only exist from Android 8.

## [1.3.1] - 2026-11-27

### Fixed

- **Android TV:** the app no longer stops right after the start on Android 7 (Fire OS 6, for example Fire TV Stick 4K
  of the first generation). 1.3.0 used a regular expression that Android does not support when it announced the
  player on the network.

## [1.3.0] - 2026-11-27

### Added

- **Enigma2 and Kodi:** export and import the settings as one file (`camalert-settings.json`), to copy them to
  another player. Passwords and the access token only when you choose so; the file is checked against the settings
  schema, an older file is updated, a newer one refused. Before every import (and before an update changes the
  settings) the current settings are saved, and *Undo the last import* brings them back (#7).
- **Android TV:** the action menu. Fire TV remotes have no colour keys: **MENU** (≡) in the photo window or the live
  view opens a list with the colour-key actions for Home Assistant (e.g. open the gate) and camera control; ▲ ▼
  chooses, OK does it, BACK or MENU closes it. Remotes with colour keys keep working as before (#118).
- **Android TV:** camera control (PTZ via ONVIF or Foscam) and Foscam motion and sound alarms, with a list of
  camera devices in the app's own private storage (same lines as `devices.conf`); `/camalert/ptz` works on Android
  TV too (#66).
- **All players:** a window can stay as long as there is motion: `sec` 0 on `show` (API, MQTT, Home Assistant
  `seconds: 0`) keeps it until `hide` or a new `show`, at most 10 minutes, so a missed `hide` never leaves it on
  screen. The motion blueprint has a new option **Until the motion ends** (`until_motion_ends`) that hides the camera
  when every sensor is off again. Capability `hold`; older players get the longest fixed duration (#81).
- **All players:** a **Text size** (normal, large, extra large) for every CamAlert screen: window titles, key hints,
  camera control, tour, mosaic and lists; the title bar grows with it (#48).
- **All players:** **Doorbell and alarm marking**: a window for a request with priority high gets an orange frame and
  the word *Doorbell* in its title, alarm a red-orange frame and *ALARM*. Colours from the Okabe-Ito palette (safe
  for colour blindness) and never colour alone; *Flashing* flashes once per second, *Off* turns it off (#48).
- **All players:** **Simple settings** in one step: large text, large window, 60 seconds, camera control key off,
  doorbell chime for doorbell and alarm (Enigma2: MENU in the settings; Kodi and Android TV: in the display
  settings) (#48).
- **All players:** a **Language** per player: CamAlert's texts in English, Dutch, German, French, Italian or Polish
  whatever the language of the receiver, Kodi or Android device (#10). Enigma2 setting names follow after a restart
  of the GUI; Kodi's settings dialog itself stays in Kodi's language; Android TV's overlay follows after a restart
  of the app.
- **Enigma2 and Kodi:** *Look at the door*: one key that shows the default camera at once, without chime
  ([Remote keys](docs/user/keys.md#look-at-the-door-one-key-for-the-default-camera)) (#13).
- **Home Assistant:** sets up a new player. Right after adding a player that has no go2rtc address yet, Home
  Assistant offers to send its go2rtc address (and a default camera); **Configure** on the entry sends one later. A
  player that was never set up takes any address, a player that is set up only one in the local network. New API
  route `/camalert/setup` (capability `setup`); `/camalert/status` reports `configured` (#122).
- **Home Assistant:** selects **Window position** and **Window size** per player, to change where the photo window
  appears and how big it is from Home Assistant or an automation. New API route `/camalert/settings` (capability
  `settings`); `/camalert/status` also reports `position` and `size` (#84).
- **Home Assistant:** players are found automatically. Every player announces itself on the local network
  (`_camalert._tcp`, without a token), Home Assistant shows it as *Discovered* and adds it with one click; it asks for
  the access token only when the player has one, and takes over a new IP address of a player it knows (#121).
- **All players:** a wizard on the first start (no go2rtc address yet): it looks for go2rtc in your network
  (`homeassistant.local`, your Home Assistant, the own network on port 1984), lets you choose the default camera
  with a preview, shows a test notification without chime and tells you how to add the player in Home Assistant.
  It never opens again by itself; *Start the wizard again* is in the menu (#120).
- **Home Assistant:** the player's device is shown under the device of the TV or Enigma2 receiver it runs on, found
  automatically by address from the Enigma2, Kodi or Android TV integration. **Configure** on the CamAlert entry
  (*Show under device*) chooses another device or turns this off.
- **Home Assistant:** a notify entity *Notification* per player: `notify.send_message` shows the message as a
  notification on the TV, with the picture of the camera named in the title (otherwise the default camera).
- **Home Assistant:** an update entity *CamAlert* per player shows when a newer CamAlert release is out, with a
  link to the release notes. GitHub is checked at most every 6 hours, without a token; installing stays on the
  player.
- **Kodi:** CamAlert can be Kodi's screensaver: while Kodi is idle it shows the mosaic cameras (or all cameras,
  up to 9); any key closes it. Choose it under *Settings › Interface › Screensaver › Screensaver mode*
  ([Kodi](docs/players/kodi.md#as-screensaver)).
- **All players:** live view shows a still picture of the camera at once and switches to the moving picture as
  soon as the stream runs, instead of a black screen while it opens. The picture comes from the fastest source
  there is: the warm feed of a ready camera, UniFi Protect, go2rtc's cache, else a new frame (#91). On an
  Enigma2 receiver the stream starts right after the picture is on screen (at most 1.5 s later), because opening a
  stream holds the receiver for a moment.

### Fixed

- **All players:** a live mosaic stream of your own in go2rtc (one stream that combines other streams of the same
  go2rtc) no longer shows up as a tile in the photo mosaic, the tour, the Kodi screensaver and the camera list of the
  Kodi video add-on: no more mosaic inside the mosaic. It stays a camera you can show or choose (#125).
- **Kodi:** a CamAlert window (photo window, live view, notification; every priority) first ends a running
  screensaver, CamAlert's own or another one, so it no longer opens hidden behind it (#119).
- **All players:** a helper stream that only transcodes another camera of the same go2rtc
  (`ffmpeg:<camera>#...`, as *Keep cameras ready* and the live substreams make) is no longer listed as a camera,
  also on players where that setting is off. The Home Assistant button for it disappears at the next reconnect
  (#116, #117).
- **Kodi repository:** the icon and fanart of the add-ons are published next to the zips, so the add-on browser
  shows them instead of an empty box (#123).

## [1.2.0] - 2026-11-27

### Added

- **Android TV / Fire TV:** every release now has a signed app (`camalert-androidtv-X.Y.Z.apk`) to install with
  a downloader app; updates install over it. A test build installed earlier has to be uninstalled once.
- **All players:** *Keep cameras ready* – for the cameras you choose, the player keeps a small MJPEG stream from
  go2rtc open while it is on, so the photo window shows the camera at once. Closed in standby, with the screen off
  or with CamAlert off; go2rtc then stops transcoding by itself. Off by default ([cameras](docs/user/cameras.md#keep-cameras-ready)).
- **All players:** UniFi Protect cameras get the pictures of the photo window, the multi-camera window, the mosaic
  and the tour straight from the UniFi Protect console in the devices file: a fresh picture at once instead of
  waiting 2–5 seconds for the camera's next key frame in go2rtc. New setting *Pictures from UniFi Protect* (on);
  other cameras and a console that does not answer use go2rtc ([devices](docs/user/devices.md#pictures-from-unifi-protect)).
- **Kodi:** a **Choose per camera** button below each per-camera setting (camera names, turn or mirror image,
  refresh interval, cooldown per camera, live view substreams): pick a camera, then a value from a list, instead of
  typing `name=value|...`. **Choose cameras** ticks up to 9 mosaic cameras.
- **Android TV / Fire TV:** UniFi Protect events without Home Assistant, like on Enigma2 and Kodi: the same
  settings and rules, the console login in its own private storage (*Triggers › UniFi Protect console*), login
  backoff and diagnostics ([Android TV](docs/players/androidtv.md#settings)).
- **Android TV / Fire TV:** *Use HTTPS for the API* (self-signed certificate in the Android KeyStore) and
  *Remote syslog* (RFC 5424 over UDP), like on Enigma2 and Kodi.
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

- **Home Assistant:** the integration, its translations and the blueprints now name the Android TV / Fire TV app
  as a player next to Enigma2 receivers and Kodi (the blueprint inputs themselves are unchanged).
- **Enigma2:** the install guide installs through the opkg feed first, so the receiver's software update keeps
  CamAlert up to date; receivers installed from an `.ipk` add the feed once (the `.ipk` stays as a fallback).
- **Photo window, multi-camera window, mosaic and tour:** a tile shows *Loading picture...* at once instead of a
  black or empty picture, and the first picture asks go2rtc for a cached frame (`cache=10s`, go2rtc 1.9.14 or newer;
  older versions ignore it): a camera that was shown a moment ago appears at once instead of after 2–5 seconds.
- **Kodi:** the camera list (*Videos › Video add-ons › CamAlert*) keeps its own order – mosaic, tour, cameras,
  event list, settings – instead of *Sort by: Date*, and every item has a short description in the info panel.
- **Docs:** the [settings list](docs/user/settings.md) now also shows which settings the Android TV / Fire TV
  player has, and its own defaults (live volume 0).

### Fixed

- **MQTT / Home Assistant:** discovery now removes the button of a camera that is gone (renamed, removed, or a helper
  stream of *Keep cameras ready*); turning discovery off removes all of the player's entities. Old leftovers are
  cleaned up the next time the player connects.

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

[Unreleased]: https://github.com/kevinrossnl/camalert/compare/v1.3.1...HEAD
[1.3.1]: https://github.com/kevinrossnl/camalert/releases/tag/v1.3.1
[1.3.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.3.0
[1.2.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.2.0
[1.1.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.1.0
[1.0.1]: https://github.com/kevinrossnl/camalert/releases/tag/v1.0.1
[1.0.0]: https://github.com/kevinrossnl/camalert/releases/tag/v1.0.0
