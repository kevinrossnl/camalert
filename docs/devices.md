# Cameras with alarms or PTZ (Foscam, ONVIF)

CamAlert can talk to some cameras directly – without Home Assistant – to

- show a **Foscam** camera when it detects motion or sound, and
- **move** a camera (pan / tilt / zoom) from the remote control or Home Assistant: ONVIF (most brands) or Foscam.

## The devices file
Camera passwords are kept in a separate file on the receiver, never in the settings, never in logs or diagnostics:
`/etc/enigma2/camalert_devices.conf` (make it readable for root only: `chmod 600`). One line per camera:

```text
# name|type|host:port|user|password
garden|foscam|192.168.1.50:88|admin|secret
drive|onvif|192.168.1.51:80|admin|secret
```

- `name` = the camera name as in go2rtc (so CamAlert knows which camera to show or move),
- `type` = `foscam` or `onvif`,
- port: Foscam HD models usually `88`, ONVIF usually `80` (some use `8000`, `8080` or `2020`).

Exclude this file from backups or settings dumps that leave the house.

## Foscam motion and sound alarms
*Foscam motion alarms* (on by default, only does something when the file lists Foscam cameras) asks every Foscam camera
every 2 seconds for its state (`getDevState`). When `motionDetectAlarm`, `soundAlarm` or `humanDetectAlarmState` becomes 2
(alarm), that camera is shown once with the label "Motion" and the *Foscam priority*. Motion detection itself must be
switched on in the camera.

## PTZ from the remote
In the photo window or in live view of a camera that is listed in the devices file, press the *PTZ key* (default BLUE):

| Key | Action |
|---|---|
| arrows | pan / tilt (about half a second per press; hold to keep moving) |
| CH+ / CH- | zoom in / out |
| OK | home position |
| EXIT or the PTZ key | leave PTZ mode |

The photo window stays open while PTZ mode is on. Home Assistant: action `camalert.ptz`; API: `/camalert/ptz?cam=drive&move=left`.

## What is supported
| Brand / protocol | How | Tested |
|---|---|---|
| ONVIF Profile S cameras with PTZ (Hikvision, Dahua, Reolink, Amcrest, TP-Link Tapo/VIGI, Axis, Uniview, Annke, ...) | SOAP: GetCapabilities, GetProfiles, ContinuousMove + Stop, GotoHomePosition; WS-Security UsernameToken (digest), clock corrected with GetSystemDateAndTime | unit tests and a local mock ONVIF camera (also end-to-end on a receiver); no real PTZ camera |
| Foscam HD (CGIProxy.fcgi) | ptzMoveUp/Down/Left/Right + ptzStopRun, zoomIn/zoomOut + zoomStop, ptzReset; getDevState for alarms | unit tests and a local mock camera (also end-to-end on a receiver) |

Cameras without PTZ simply answer that they have no PTZ service; CamAlert logs it and does nothing. UniFi Protect cameras
do not offer ONVIF PTZ.
