# CamAlert for Android TV and Fire TV

**Status: in development (#64), not in a release yet.** The Android TV app shows your cameras on an Android TV
or Fire TV device **without Kodi**: a photo window over whatever app is playing, the multi-camera window, mosaic,
tour and live view. It has the **same HTTP API, MQTT topics and Home Assistant integration** as the other
players (platform `androidtv`), so blueprints and automations work unchanged.

Minimum: Android 7.1 (API 25), which includes Fire OS 6 (Fire TV Stick 4K, 1st generation). No Google Play
Services needed.

## Install (sideload with ADB)

The app is not in an app store; you install the APK from a computer in the same network.

1. **Fire TV:** Settings › My Fire TV › About › select the device name **7 times** to show *Developer options*.
   Then Settings › My Fire TV › Developer options: turn on **ADB debugging** (and *Apps from unknown sources*).
   **Android TV / Google TV:** Settings › Device preferences › About › select *Build* 7 times, then Developer
   options › **Network debugging** (or USB debugging).
2. Find the IP address of the TV device (Fire TV: Settings › My Fire TV › About › Network), e.g. `192.168.1.30`.
3. On the computer (Android platform-tools):

   ```sh
   adb connect 192.168.1.30:5555        # confirm "Allow USB debugging" on the TV the first time
   adb install -r camalert-androidtv-debug.apk
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

**Update:** `adb install -r` with the new APK keeps the settings. **Remove:** `adb uninstall org.camalert.tv`.

## Settings

Open **CamAlert** from the apps row (or *Settings › Apps › CamAlert › Open*). The settings use the same names,
defaults and levels as on the other players ([all settings](../user/settings.md)); expert settings are hidden
until you turn on *Show expert settings*. Not yet on Android TV (#64): direct mode with a camera file, Foscam
alarms, camera control (PTZ), HTTPS for the API, remote syslog, pausing what is playing.

## What you see

- **Photo window** – a camera in a corner over any app. Remote: **OK** = live, **◀ ▶** = other camera,
  **BACK** = close. Fire TV remotes have no colour keys; other Android TV remotes send RED / GREEN / YELLOW /
  BLUE to Home Assistant while a camera is shown. All keys: [remote keys](../user/keys.md).
- **Multi-camera window** (2–4 cameras), **mosaic** (up to 9; OK or BACK closes) and **tour** (◀ ▶, OK =
  pause, PLAY/PAUSE = live view, BACK). A camera that does not answer shows a *Camera not reachable* tile.
- **Live view** – the camera full screen over the app (Media3/ExoPlayer: MP4 or HLS from go2rtc, or RTSP over
  TCP). **Muted** by default (on Android TV *Volume during live view* starts at 0 %, because the app underneath keeps playing its own sound); turn it up to hear the camera.
- **Notification** – a small window with the snapshot and the title.

## API and Home Assistant

The app listens on port **8099** (setting *HTTP port*) with exactly the API of the other players:
[HTTP API](../integrations/api.md). Home Assistant: add the integration with the IP address of the TV device; the
device shows as *Android TV* with the same entities. MQTT discovery: [MQTT](../integrations/mqtt.md).

The device must be reachable from Home Assistant on port 8099. If Home Assistant is in another network (VLAN),
allow that port in your firewall from Home Assistant to the TV device.

## Logs and diagnostics

*Diagnostics* and the *event list* are in the settings. The log is also on the API (`/camalert/log`) and in
`adb logcat -s CamAlert`. Passwords and tokens are never logged.

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

Keep the keystore and its password safe (a later update must be signed with the same key). Release signing in CI
is a separate issue.
