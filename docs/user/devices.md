# Cameras with alarms or PTZ (Foscam, ONVIF, UniFi Protect)

CamAlert can talk to some cameras directly – without Home Assistant – to

- show a **Foscam** camera when it detects motion or sound,
- show a camera when a **UniFi Protect** console reports a doorbell ring, a person, a vehicle, ... and
- **move** a camera (pan / tilt / zoom) from the remote control or Home Assistant: ONVIF (most brands) or Foscam.

## The devices file
Camera passwords are kept in a separate file on the player, never in the settings, never in logs or diagnostics.
Enigma2: `/etc/enigma2/camalert_devices.conf` (make it readable for root only: `chmod 600`); Kodi: `devices.conf`
in the add-on data folder (*Camera control › Create devices.conf* makes an example; an empty user/password there
means the default camera login of the settings). One line per camera:

```text
# name|type|host:port|user|password
garden|foscam|192.168.1.50:88|admin|secret
drive|onvif|192.168.1.51:80|admin|secret
protect|unifi|192.168.1.1:443|camalert|<password>
```

- `name` = the camera name as in go2rtc (so CamAlert knows which camera to show or move); for `unifi` any name for
  the console,
- `type` = `foscam`, `onvif` or `unifi` (a UniFi Protect console),
- port: Foscam HD models usually `88`, ONVIF usually `80` (some use `8000`, `8080` or `2020`).

Exclude this file from backups or settings dumps that leave the house.

## Foscam motion and sound alarms
*Foscam motion and sound alarms* (off by default; only does something when the file lists Foscam cameras) asks every
Foscam camera every *Check every (seconds)* (default 2) for its state (`getDevState`). When `motionDetectAlarm`, `soundAlarm` or `humanDetectAlarmState` becomes 2
(alarm), that camera is shown once with the label "Motion", the *Foscam priority* and its own display mode and duration. Motion detection itself must be
switched on in the camera.

## UniFi Protect events
*UniFi Protect events* (section *Triggers*, off by default) asks every console of type `unifi` in the devices file
every *Check every (seconds)* (default 5) for the events of the last minute. Use a **local Protect user with the
role *View Only*** (UniFi OS › Admins & Users › add a local user, *Restrict to local access only*): CamAlert only
reads the camera list, the events and snapshots and never changes anything. After a 401 it logs in again with a
fresh session.

- *UniFi Protect event types*: which events count, comma separated: `ring`, `person`, `vehicle`, `animal`,
  `package`, `motion` (default `ring,person`).
- *UniFi Protect camera names*: only when the camera names in Protect differ from the go2rtc stream names, for
  example `Front Door=front_door|Garden=garden` (Protect name or camera id on the left).
- *UniFi Protect priority*, *Display mode* and *Duration (seconds)*: for every event; a doorbell ring always gets at
  least the priority *High*. Display mode *Log only* writes the event to the event list and the log and shows
  nothing (no doorbell chime): handy to try the source first.
- *Per event type* (expert): `type=priority/mode/camera`, for example `ring=alarm/live|motion=normal/log`; an empty
  part keeps the general setting, `camera` sends the event to another go2rtc stream.

The first answer after a start, a setting change or an error only remembers what is there: old events never pop up.
When several new events arrive in one check, the most important one is shown (ring, person, vehicle, animal,
package, motion). Events get the source *UniFi Protect* in the event list. The diagnostics screen shows the last
check, the last event and the last error (never a password or cookie). Both players make the devices file readable
for its owner only (`chmod 600`) when they read it; on Kodi a `unifi` line never gets the default camera login.

Where to turn it on: Enigma2 *Settings › Triggers › UniFi Protect* (setup level *Advanced*, or MENU › *Show all
settings*); Kodi 19 or newer *Add-ons › My add-ons › Services › CamAlert › Configure › Triggers* (settings level
*Advanced*).

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
| ONVIF Profile S cameras with PTZ (Hikvision, Dahua, Reolink, Amcrest, TP-Link Tapo/VIGI, Axis, Uniview, Annke, ...) | SOAP: GetCapabilities, GetProfiles, ContinuousMove + Stop, GotoHomePosition; WS-Security UsernameToken (digest), clock corrected with GetSystemDateAndTime | unit tests and a local mock ONVIF camera (also end-to-end on a player); no real PTZ camera |
| Foscam HD (CGIProxy.fcgi) | ptzMoveUp/Down/Left/Right + ptzStopRun, zoomIn/zoomOut + zoomStop, ptzReset; getDevState for alarms | unit tests and a local mock camera (also end-to-end on a player) |

Cameras without PTZ simply answer that they have no PTZ service; CamAlert logs it and does nothing. UniFi Protect cameras
do not offer ONVIF PTZ; `unifi` lines are consoles, never PTZ cameras.
