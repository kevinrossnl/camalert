# Settings

Every setting of CamAlert, from the one settings schema of all players (`core/camalert_core/schema.py`). The labels
are the English ones; on the player they appear in your menu language. *Level*: **basic** is always shown,
**advanced** and **expert** follow the settings level of the player (Enigma2: *Menu › Setup › System › Settings
level*; Kodi: the level button in the settings dialog). *Players* says which players have a setting (**all** =
Enigma2, Kodi and Android TV); a player with its own default is named next to the default.

How the settings look: [Enigma2 receiver](../players/enigma2.md#settings), [Kodi](../players/kodi.md#settings),
[Android TV](../players/androidtv.md#settings).

<!-- BEGIN generated: settings (tools/docs.py) -->
### General

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Enable CamAlert | Yes |  | basic | all | Turn the HTTP API and the camera display on or off. |
| Cameras via | `go2rtc` | `go2rtc` / `direct` | basic | Enigma2, Kodi | go2rtc is recommended. Without go2rtc, list your cameras in the camera file |
| go2rtc address | – |  | basic | all | Address of your go2rtc server, e.g. http://192.168.1.10:1984 |
| go2rtc RTSP port | `8554` | 1–65535 | expert | all | Usually 8554. Used for live view and the camera list. |
| Default camera | – |  | basic | all | Press OK to choose from the cameras in go2rtc. |
| Check certificates | Yes |  | expert | all | Turn off for a self-signed certificate (only in your own network). |
| Mosaic cameras | – |  | advanced | all | Press OK to choose up to 9 cameras for the mosaic. Empty = all. |
| Camera names | – |  | advanced | all | Press OK to give a camera its own name (empty = automatic). |
| Live view substreams | – |  | expert | all | For cameras the receiver cannot play (H.265/4K): front_door=front_door_sub uses that go2rtc stream for live view. |
| Language | `system` | `system` / `en` / `nl` / `de` / `fr` / `it` / `pl` | advanced | all | Language of the CamAlert texts on this device. System language: the language of the device itself. |
| Camera file (direct mode) | – |  | expert | Kodi | Empty = cameras.conf in the add-on data folder. One camera per line: name \| rtsp-url \| snapshot-url |

### Display

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Display mode | `photo` | `photo` / `live` / `notify` | basic | all | Photo window keeps watching TV; live switches the channel to the camera. |
| Duration (seconds) | `30` s | 5–300, step 5 | basic | all | How long the camera stays on screen. |
| Window position | `top_right` | `top_right` / `top_left` / `bottom_right` / `bottom_left` | basic | all |  |
| Window size | `medium` | `small` / `medium` / `large` | basic | all |  |
| Return to what was playing | Yes |  | advanced | Enigma2, Kodi | Switch back to what you were watching when the time is up. |
| Pause what is playing meanwhile | No |  | advanced | Enigma2, Kodi | Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift. |
| Volume during live view (%) | `100`% (Android TV: `0`) | 0–100, step 10 | advanced | all | Percentage of the current volume while the camera is shown. 100 = unchanged. |
| Remote control in photo window | Yes |  | advanced | all | OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too. |
| Tour: seconds per camera | `8` s | 3–60 | advanced | all |  |
| Turn or mirror image | – |  | advanced | all | Press OK to turn a camera that hangs upside down (needs python3-pillow). |
| Pictures from UniFi Protect | Yes |  | advanced | all | UniFi cameras get their pictures from the UniFi Protect console in the devices file: faster than go2rtc. |
| Keep cameras ready | – |  | advanced | all | Only while this player is on: keeps the MJPEG stream of these cameras open so the photo window shows them at once, e.g. front_door=front_door_jpeg. Empty = off. |
| Refresh interval | – |  | advanced | all | Press OK to fetch a camera's photos less often (seconds), e.g. for a slow camera. |
| Multi-camera window layout | `auto` | `auto` / `vertical` / `horizontal` / `grid` | advanced | all | A request with 2-4 cameras shows them together in one multi-camera window. |
| Title size | `normal` | `small` / `normal` / `large` | advanced | all |  |
| Text size | `normal` | `normal` / `large` / `xlarge` | advanced | all | All CamAlert texts: window titles, key hints, camera control, tour, mosaic and lists. |
| Doorbell and alarm marking | `steady` | `off` / `steady` / `flash` | advanced | all | Priority high: orange frame and the word Doorbell. Alarm: red-orange frame and the word ALARM. Flashing: once per second. |
| Doorbell chime | `off` | `off` / `high` / `all` | advanced | all | Plays a short ding-dong for requests with priority high or alarm (doorbell). |
| Picons for the camera channels | No |  | advanced | Enigma2 | Makes a simple picon (camera + name) for every camera channel; existing picons are never replaced. |
| Live stream format | `mp4` | `mp4` / `hls` / `rtsp` | expert | Kodi, Android TV | MP4 over HTTP works with every go2rtc set-up; RTSP needs go2rtc's RTSP port; HLS is the most robust but lags a few seconds. |

### Rules

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Not during a recording | No |  | advanced | Enigma2 | Ignore normal requests while the receiver is recording. |
| Only between certain times | No |  | basic | all | Ignore normal requests outside the chosen times. High and alarm always come through. |
| From | `07:00` |  | basic | all |  |
| Until | `23:00` |  | basic | all | May pass midnight, e.g. 07:00 to 23:00. |
| Wake up on alarm | No |  | advanced | all | Requests with priority 'alarm' switch the receiver (and TV via HDMI-CEC) on. |
| Do not disturb | No |  | basic | all | Ignores requests with normal priority (with 'Do not disturb blocks' also high). Alarm always comes through. Also via the API, MQTT and Home Assistant. |
| Do not disturb blocks | `normal` | `normal` / `high` | advanced | all |  |
| Cooldown per camera | – |  | expert | all | Seconds before the same camera is shown again, e.g. *=30\|garden=120 (* = all cameras). Alarm always. |
| Not while playing | `off` | `off` / `video` / `all` | advanced | all | Ignore normal requests while a video or recording plays (video) or while anything plays (all). High and alarm always come through. |

### Triggers

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Frigate events | No |  | advanced | all | Shows the camera when Frigate detects something (via MQTT, without Home Assistant). |
| Frigate MQTT prefix | `frigate` |  | expert | all | Usually 'frigate'. |
| Frigate objects | `person` |  | advanced | all | Comma separated, e.g. person,car. Empty = all objects. |
| Frigate camera names | – |  | advanced | all | Only if the names differ from go2rtc: frigate=go2rtc\|other=other_stream |
| Frigate priority | `normal` | `normal` / `high` / `alarm` | advanced | all |  |
| Foscam motion and sound alarms | No |  | advanced | all | Asks the Foscam cameras in the camera file for motion and sound alarms. |
| Foscam priority | `normal` | `normal` / `high` / `alarm` | advanced | all |  |
| Frigate address (for clips) | – |  | expert | Enigma2, Kodi | Optional, e.g. http://192.168.1.10:5000 - lets you play the clip of an event from the event list. |
| Display mode | `photo` | `photo` / `live` / `notify` | advanced | all |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | all |  |
| Check every (seconds) | `2` s | 1–60 | expert | all |  |
| Display mode | `photo` | `photo` / `live` / `notify` | advanced | all |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | all |  |
| UniFi Protect events | No |  | advanced | all | Asks the UniFi Protect consoles in the camera file for events (doorbell, person, vehicle, ...). |
| UniFi Protect event types | `ring,person` |  | advanced | all | Comma separated: ring, person, vehicle, animal, package, motion. |
| UniFi Protect camera names | – |  | advanced | all | Only if the names differ from go2rtc: protect=go2rtc\|other=other_stream |
| UniFi Protect priority | `normal` | `normal` / `high` / `alarm` | advanced | all | A doorbell ring always gets at least the priority High. |
| Display mode | `photo` | `photo` / `live` / `notify` / `log` | advanced | all |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | all |  |
| Check every (seconds) | `5` s | 2–60 | expert | all |  |
| Per event type | – |  | expert | all | Optional: type=priority/mode/camera, e.g. ring=alarm/live\|motion=normal/log |
| Per camera | – |  | expert | all | Optional, wins over the event type: camera=priority/mode/seconds, e.g. front_door=high/photo/30\|driveway=normal/log |

### Camera control

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Camera control (PTZ) key | `blue` | `blue` / `yellow` / `red` / `green` / `off` | advanced | all | For cameras with PTZ in the camera file: this key switches PTZ mode on (arrows, CH+/CH-, OK = home). |
| Colour keys to Home Assistant | Yes |  | advanced | all | While a camera is on screen the colour keys send an event to Home Assistant (e.g. open the gate). |
| Camera user (default) | – |  | advanced | Kodi | Used when devices.conf has no user or password for a camera. |
| Camera password (default) | – |  | advanced | Kodi | Used when devices.conf has no user or password for a camera. |

### Home Assistant / MQTT

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| MQTT (Home Assistant without YAML) | No |  | advanced | all | Connects to your MQTT broker; with discovery the receiver appears in Home Assistant automatically. |
| MQTT broker address | – |  | advanced | all | IP address or name of the MQTT broker, e.g. 192.168.1.10 |
| MQTT port | `1883` | 1–65535 | advanced | all | Usually 1883. |
| MQTT user | – |  | advanced | all |  |
| MQTT password | – |  | advanced | all |  |
| Home Assistant discovery | Yes |  | advanced | all | Creates a device with a button per camera in Home Assistant. |
| Name in Home Assistant | – |  | advanced | all | Empty = CamAlert + the receiver's host name. |

### API

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Use HTTPS for the API | No |  | expert | all | Uses a self-signed certificate; callers must turn off certificate checking. |
| HTTP port | `8099` | 1024–65535 | expert | all | Port of the CamAlert API on this receiver (default 8099). |
| Allowed callers | `lan` | `lan` / `any` | advanced | all | 'Local network only' is recommended. |
| Access token (optional) | – |  | advanced | all | If set, callers must send it in the X-CamAlert-Token header; ?token=... in the address still works but is deprecated. |

### Channel list (Enigma2)

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Camera list name | `Cameras` |  | advanced | Enigma2 | Name of the channel list created with the yellow button. |
| Update camera list automatically | Yes |  | advanced | Enigma2 | Checks every 30 minutes for new or removed cameras and updates the channel list. |
| Camera list position | `keep` | `keep` / `bottom` / `top` | expert | Enigma2 | Where the camera list appears among your channel lists. |

### Log and diagnostics

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Log level | `normal` | `off` / `errors` / `normal` / `verbose` | advanced | all | camalert.log in /home/root/logs (or /tmp). Passwords and tokens are never logged. |
| Remote syslog (host:port) | – |  | expert | all | Optional: also send the log via UDP (RFC 5424), e.g. to Loki/Alloy. |
| Event snapshots folder | `/tmp/camalert_events` |  | expert | Enigma2 | Small photos of the last 20 events (default /tmp/camalert_events). |
| Check for updates | Yes |  | advanced | Enigma2 | Looks once a day on GitHub for a new version and shows a message. |
<!-- END generated: settings -->
