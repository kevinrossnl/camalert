# CamAlert for Kodi

The Kodi add-on **CamAlert** (`service.camalert`) does the same as the Enigma2 plugin, on any Kodi 20 or newer:
LibreELEC, CoreELEC, OSMC, Windows, Linux, macOS and Android TV boxes. It uses the **same HTTP API, MQTT topics
and Home Assistant integration**, so blueprints and automations work unchanged – a Kodi is just another CamAlert
device.

## Install

**With automatic updates (recommended)**

1. Download `repository.camalert-x.y.z.zip` from the [latest release](../../../releases/latest) and copy it to
   the Kodi device (USB stick, network share, or the Kodi download folder).
2. Kodi › **Settings › System › Add-ons**: turn on **Unknown sources** (needed once for a zip file).
3. Kodi › **Add-ons › Install from zip file** › choose the repository zip.
4. **Add-ons › Install from repository › CamAlert repository › Services › CamAlert › Install**.

Kodi now checks the repository and updates CamAlert by itself.

**Just the add-on:** install `service.camalert-x.y.z.zip` with *Install from zip file* (no automatic updates).

After installing, open **Add-ons › My add-ons › Services › CamAlert › Configure**.

## Settings

| Tab | What |
|---|---|
| General | go2rtc address (or *Directly from the cameras* with `cameras.conf`), default camera (**Choose camera** lists them), camera titles, mosaic cameras, test buttons |
| Display | photo window / live / notification, duration, corner and size, layout for 2–4 cameras in one window, rotate/mirror and refresh interval per camera, remote control in the window, pause what is playing, return to what was playing, volume during live view, live format, tour speed |
| Rules | do not disturb, only between certain times, *not while playing* (off / films and recordings / everything), wake the screen on alarm (HDMI-CEC) |
| MQTT / Home Assistant | broker, login, discovery, name |
| Triggers | Frigate detections (via MQTT), Foscam motion/sound alarm |
| Camera control | default camera login for PTZ / Foscam, create `devices.conf` |
| API | port (8099), allowed callers, token, HTTPS |
| Log and diagnostics | log level (off / errors / normal / verbose), remote syslog, **Diagnostics** (checks go2rtc, every camera's snapshot, API, MQTT, last caller) and **Recent events** (last 20 requests with snapshot; OK shows the camera again or replays the Frigate clip) |

Display also has the **title size** (small / normal / large) and the **doorbell sound** (off / doorbell and alarm / every
request; it follows Kodi's volume and mute).

Passwords are stored by Kodi in the add-on's own `settings.xml` in its data folder and are never written to the log.

## What you see

- **Photo window** – a camera in a corner while the film or TV keeps playing. Remote: **OK** = live,
  **◀ ▶** = other camera, **MENU** (or **INFO**) = camera control (PTZ), **BACK** = close, any other key closes the
  window and does what it normally does. Volume keys keep working.
- **Several cameras** – a request for 2 to 4 cameras (`cam=front_door,garden`) shows them together in one corner
  window (below each other, next to each other or 2×2); more cameras open the mosaic.
- **Live** – the camera full screen with a small bar: **◀ ▶** other camera, **MENU** = PTZ, **BACK** = back. When the
  time is up (or after BACK) Kodi **continues the film at the same position** or **returns to the same TV channel**.
  The volume can be lowered meanwhile.
- **Notification** – a Kodi notification with a snapshot as icon.
- **Who/what in the title** – `label=Person` (API, MQTT JSON, blueprints) or Frigate's label / recognised name
  shows as "Person · Front door".
- **Colour keys → Home Assistant** – while a camera is shown, RED / GREEN / YELLOW / BLUE fire a Home Assistant
  event (MQTT event entity `camalert/<id>/button` and the integration's webhook), for example to open the door.
  The colour key chosen under *Camera control* toggles PTZ on cameras that have it. On a keyboard: F1–F4.
- **Mosaic** (up to 9 cameras) and **tour** (◀ ▶, OK = hold, PLAY = live, BACK).

## Camera control (PTZ) and Foscam alarms

Cameras that can move or that report their own alarms are listed in `devices.conf` in the add-on data folder
(*Camera control › Create devices.conf* makes an example and shows where it is):

```
# name|type|host:port|user|password      (name = CamAlert camera name; type = onvif or foscam)
front_door|onvif|192.168.1.20:80|admin|secret
garden|foscam|192.168.1.21:88|admin|secret
```

Empty user/password = the login in the settings. In the photo window or live view press **MENU** (or **INFO**):
arrows pan and tilt, **CH+ / CH−** (or PAGE UP / DOWN) zoom, **OK** = home position, **BACK** leaves PTZ mode.

## Where things are

| | LibreELEC / CoreELEC | Windows | Linux / OSMC | Android |
|---|---|---|---|---|
| Add-on data (`settings.xml`, `devices.conf`, `cameras.conf`, HTTPS certificate) | `/storage/.kodi/userdata/addon_data/service.camalert/` | `%APPDATA%\Kodi\userdata\addon_data\service.camalert\` | `~/.kodi/userdata/addon_data/service.camalert/` | `Android/data/org.xbmc.kodi/files/.kodi/userdata/addon_data/service.camalert/` |
| CamAlert log (`camalert.log` + `camalert.log.1`, 2 × 1 MB) | same folder as the add-on data | same | same | same |
| Kodi log (`kodi.log`, lines start with `[CamAlert]`) | `/storage/.kodi/temp/` | `%APPDATA%\Kodi\` | `~/.kodi/temp/` | `.../files/.kodi/temp/` |

## Differences with the Enigma2 plugin

- Kodi has no standby: *screen off* (DPMS) counts as standby. An **alarm** request with *wake the screen* switches
  the TV on via HDMI-CEC.
- *Pause what is playing* pauses a film or live TV (timeshift has to be supported by your PVR add-on).
- No camera channel list: use the mosaic, the tour, or Kodi favourites.
- Live view plays go2rtc's MP4 stream by default (works with every go2rtc). HLS is the most robust but runs a few
  seconds behind; RTSP needs go2rtc's RTSP port. In *Directly from the cameras* mode Kodi plays the camera's own
  `rtsp://` address (Kodi does not know `rtspt://`).
- Rotate/mirror applies to the photo window, mosaic and tour (not to the live video).
- **Windows**: allow Kodi through the Windows firewall for the API port (8099) if Home Assistant cannot reach it;
  *wake the screen* only works with a CEC adapter.

## Updates

Installed from the CamAlert repository, Kodi updates CamAlert by itself (Kodi checks repositories at start and
every few hours; *Settings › System › Add-ons › Updates* decides whether it installs them automatically or only
notifies).

## Home Assistant

Add the Kodi like a receiver: **Settings › Devices & services › Add integration › CamAlert**, enter the Kodi's IP
address and port 8099 (and the token if you set one). Or switch on MQTT with discovery. Everything in
[home-assistant.md](home-assistant.md) applies.

## Troubleshooting

- *Nothing happens*: check the add-on is enabled (Add-ons › My add-ons › Services) and that
  `http://<kodi>:8099/camalert/status` answers from another computer in your network.
- *Labels look empty right after a manual update*: restart Kodi once (Kodi loads new texts at start).
- *Live picture takes long to start*: keep the camera stream warm in go2rtc, or choose the RTSP live format.
