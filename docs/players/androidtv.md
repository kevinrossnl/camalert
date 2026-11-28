# CamAlert for Android TV and Fire TV

**Status: in development (#64), not in a release yet.** Tested on a Fire TV Stick 4K (1st generation, Fire OS 6,
Android 7.1) with demo cameras: photo window, multi-camera window, notification, mosaic, tour, *Camera not
reachable* tiles, remote keys, settings screen and the API from another network. Not yet tested: live view with
a real camera stream, MQTT with a real broker. The Android TV app shows your cameras on an Android TV
or Fire TV device **without Kodi**: a photo window over whatever app is playing, the multi-camera window, mosaic,
tour and live view. It has the **same HTTP API, MQTT topics and Home Assistant integration** as the other
players (platform `androidtv`), so blueprints and automations work unchanged.

Minimum: Android 7.1 (API 25), which includes Fire OS 6 (Fire TV Stick 4K, 1st generation). No Google Play
Services needed.

## Install (sideload with ADB)

The app is not in an app store. Every [release](https://github.com/kevinrossnl/camalert/releases/latest) has a signed
`camalert-androidtv-X.Y.Z.apk`; you install it from a computer in the same network (or with a downloader app on the
TV device, then run the `appops` line below once from a computer).

1. **Fire TV:** Settings › My Fire TV › About › select the device name **7 times** to show *Developer options*.
   Then Settings › My Fire TV › Developer options: turn on **ADB debugging** (and *Apps from unknown sources*).
   **Android TV / Google TV:** Settings › Device preferences › About › select *Build* 7 times, then Developer
   options › **Network debugging** (or USB debugging).
2. Find the IP address of the TV device (Fire TV: Settings › My Fire TV › About › Network), e.g. `192.168.1.30`.
3. On the computer (Android platform-tools):

   ```sh
   adb connect 192.168.1.30:5555        # confirm "Allow USB debugging" on the TV the first time
   adb install -r camalert-androidtv-X.Y.Z.apk   # from the latest release (assets)
   adb shell appops set org.camalert.tv SYSTEM_ALERT_WINDOW allow   # may draw over other apps
   adb shell am start -n org.camalert.tv/.SettingsActivity           # open the settings once
   ```

   The `appops` line gives the permission to show windows over other apps. On Android TV you can also allow it
   in the app (it asks), but Fire OS has no screen for it: there the `adb` line is the way.
4. Open **CamAlert** from the apps row once (or the command above): this starts the CamAlert service. Fill in the
   go2rtc address and the default camera.

**Start after a reboot:** the app starts its service when the device boots (`BOOT_COMPLETED`). Fire OS starts
apps after a boot only when they were opened once after installing; some Android TV devices also have a list of
apps that may start automatically (Settings › Apps › Special app access › *Autostart*): allow CamAlert there.

**Update:** `adb install -r` with the APK of the new release keeps the settings. From Home Assistant: the
**Install** button of the update entity downloads the release APK (checked against the release's `SHA256SUMS`) and
opens the system installer on the TV; confirm **Install** there (#126). Fire TV asks once to allow CamAlert to install
apps (Android 8+: *Install unknown apps*). A debug or self-built APK has
another signature: replacing it with the release APK (or back) needs `adb uninstall org.camalert.tv` first, which
removes the app's settings. **Remove:** `adb uninstall org.camalert.tv`.

## Settings

Open **CamAlert** from the apps row (or *Settings › Apps › CamAlert › Open*). The settings use the same names,
defaults and levels as on the other players ([all settings](../user/settings.md)); expert settings are hidden
until you turn on *Show expert settings*. The *Players* column of the settings list says which ones Android TV has;
*Volume during live view* starts at 0 here (the app underneath keeps its own sound). Pausing what is playing is not
possible on Android.

**Without go2rtc** (#124): set *Cameras via* to *Directly from the cameras* and fill in **Cameras without go2rtc ›
Camera list** at the bottom of *General*, one camera per line as in the [camera file](../user/without-go2rtc.md)
of the other players: `Front door | rtsp://user:password@192.168.1.20:554/stream1 | http://user:password@192.168.1.20/snapshot.jpg`.
The list is kept in the app's own private storage (its urls usually hold a login), apart from the settings. A login
in the snapshot url works with Basic and Digest; a camera without snapshot url opens live view instead of the photo
window. go2rtc stays recommended: a Fire TV stick plays one direct RTSP stream well, a mosaic of several less so.

**Event list and Frigate clips** (#124): *Events* lists the latest events, newest first. **OK** on an event shows its
camera; with *Frigate address (for clips)* set (expert, *Triggers*) an event from Frigate offers **Play Frigate clip**
as well, a normal full-screen player (**OK** = pause, **◀ ▶** = seek, **BACK** = close).

**Camera control (PTZ) and Foscam alarms** (#66): *Camera control* has **Camera devices** at the bottom, with the
same lines as `devices.conf` on the other players, one camera per line: `front_door|onvif|192.168.1.30:80|user|password`
or `garden|foscam|192.168.1.31:88|user|password` (the name is the CamAlert camera name; empty user and password =
the default camera login below the list). They are kept in the app's own private storage, apart from the settings,
and never appear in the log. A camera in the list gets camera control: **MENU › Camera control** (or its colour key,
*Camera control (PTZ) key*), then **▲ ▼ ◀ ▶** = move, **FF / REW** (or CH+ / CH-) = zoom, **OK** = home position,
**BACK** or **MENU** = end. *Triggers › Foscam motion and sound alarms* asks the Foscam cameras of the list every few
seconds and shows the camera when an alarm starts.

**HTTPS and remote syslog** (#66, expert settings): *Use HTTPS for the API* serves the API with a self-signed
certificate (`CN=CamAlert`) that the app creates once in the Android KeyStore; in Home Assistant turn on *Use HTTPS*
and turn off *Check certificates* for this player. *Remote syslog (host:port)* also sends every log line (redacted)
as RFC 5424 over UDP, e.g. to Loki/Alloy or rsyslog; default port 514.

**UniFi Protect** (#72): *Triggers* has the same UniFi Protect settings as the other players (event types, camera
names, priority, display mode incl. *Log only*, rules per event type and per camera). The console itself goes in
**UniFi Protect console** at the bottom of *Triggers*: address (`192.168.1.1` or `host:port`), a local Protect
user with the role *View Only* and its password. They are kept in the app's own private storage, apart from the
settings, and never appear in the log or in `/camalert/status`. CamAlert only reads (camera list and events); the
console's self-signed certificate is accepted, so use it in your own network only. A refused login is not retried
at every check (30 s, 1 min, 2 min, 5 min, then every 15 min). *Diagnostics* shows the last check, the last
event and, while it waits, the next login attempt.

## What you see

- **Photo window** – a camera in a corner over any app. Remote: **OK** = live, **◀ ▶** = other camera,
  **MENU** = actions, **BACK** = close. Fire TV remotes have no colour keys, so **MENU** (≡) opens a small list in the
  window: *RED / GREEN / YELLOW / BLUE to Home Assistant* (the same event as the colour key, e.g. to open the gate)
  and *Camera control* for a camera with PTZ; ▲ ▼ chooses, OK does it, BACK or MENU closes the list (#118).
  Remotes with colour keys can still use them. All keys: [remote keys](../user/keys.md).
- **Multi-camera window** (2–4 cameras), **mosaic** (up to 9; OK or BACK closes) and **tour** (◀ ▶, OK =
  pause, PLAY/PAUSE = live view, BACK). A camera that does not answer shows a *Camera not reachable* tile.
- **Live view** – the camera full screen over the app (Media3/ExoPlayer: MP4 or HLS from go2rtc, or RTSP over
  TCP). **Muted** by default (on Android TV *Volume during live view* starts at 0 %, because the app underneath keeps playing its own sound); turn it up to hear the camera.
  CamAlert never requests audio focus, so the app underneath is not paused or turned down by a camera window
  (#88; on a Fire TV Stick 4K live view plays muted by default with MP4, HLS and RTSP, #68). While the stream
  opens a still picture of the camera is shown at once, until the first video frame (#91).
- **Notification** – a small window with the snapshot and the title.

Screenshots with demo cameras on a Fire TV Stick 4K (CamAlert 1.3):

| | |
|---|---|
| ![Photo window with a label and the key hint](../images/androidtv/photo-window.png) | **Photo window**: title (*Person · Front door*) with the key hint `OK = live   ◀ ▶ = other camera   MENU = actions   BACK = close` |
| ![Multi-camera window with one camera not reachable](../images/androidtv/multi-camera-window.png) | **Multi-camera window**: 2–4 cameras; a camera that does not answer shows *Camera not reachable* |
| ![Mosaic of four demo cameras](../images/androidtv/mosaic.png) | **Mosaic**: up to 9 cameras, one tile *Camera not reachable*; OK or BACK closes |
| ![Tour with its key hint](../images/androidtv/tour.png) | **Tour**: ◀ ▶ = other camera, OK = pause, GREEN or PLAY = live view, BACK or STOP = close |
| ![Settings of the app](../images/androidtv/settings.png) | **Settings** (open the CamAlert app), in sections; *Show expert settings* shows the rest |

## API and Home Assistant

The app listens on port **8099** (setting *HTTP port*) with exactly the API of the other players:
[HTTP API](../integrations/api.md). Home Assistant: add the integration with the IP address of the TV device; the
device shows as *Android TV* with the same entities. MQTT discovery: [MQTT](../integrations/mqtt.md).

The device must be reachable from Home Assistant on port 8099. If Home Assistant is in another network (VLAN),
allow that port in your firewall from Home Assistant to the TV device.

## Logs and diagnostics

*Diagnostics* and the *event list* are in the settings. The log is also on the API (`/camalert/log`) and in
`adb logcat -s CamAlert`. Passwords and tokens are never logged.

## Testing with demo cameras

Developers test the app with the fake go2rtc (solid-colour demo cameras, never real images). `adb reverse` does
not work with Fire OS 6 over the network, so it runs on the TV device itself:

```sh
python3 players/androidtv/testing/fake_go2rtc_on_device.py start --serial 192.168.1.30:5555
# go2rtc address in the app: http://127.0.0.1:11984 ; requests with test=1 never make sound
curl -X POST -d "cam=front_door,garden,driveway&test=1" http://192.168.1.30:8099/camalert/show
python3 players/androidtv/testing/fake_go2rtc_on_device.py stop --serial 192.168.1.30:5555
```

## Build it yourself

```sh
cd players/androidtv
./gradlew :api:test :app:assembleDebug     # JDK 17 or newer, ANDROID_HOME = Android SDK
```

The APK is `app/build/outputs/apk/debug/app-debug.apk` (debug-signed). A release build needs your own signing
key, which is never stored in the repository:

```sh
keytool -genkeypair -v -keystore ~/camalert-release.jks -alias camalert -keyalg RSA -keysize 4096 -validity 10000
```

Keep the keystore and its password safe (a later update must be signed with the same key).

**Release APK (#65):** a tag `vX.Y.Z` builds `camalert-androidtv-X.Y.Z.apk` on GitHub, signed with the project key from
the repository secrets `ANDROID_KEYSTORE_B64` (the keystore in base64), `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`
and `ANDROID_KEY_PASSWORD`, and adds it to the release. Its versionCode follows the version (`tools/android_version.py`:
1.2.0 → 10200). Without the secrets the release has no APK. A debug build and a release build have different
signatures: switching from one to the other needs one uninstall (the app's settings are lost), later releases update
normally. Local release build: set `CAMALERT_KEYSTORE`, `CAMALERT_KEYSTORE_PASSWORD`, `CAMALERT_KEY_ALIAS`,
`CAMALERT_KEY_PASSWORD` and run `./gradlew :app:assembleRelease -PcamalertVersion=X.Y.Z -PcamalertVersionCode=…`.
