# Settings

Every setting of CamAlert, from the one settings schema of both players (`core/camalert_core/schema.py`). The labels
are the English ones; on the player they appear in your menu language. *Level*: **basic** is always shown,
**advanced** and **expert** follow the settings level of the player (Enigma2: *Menu › Setup › System › Settings
level*; Kodi: the level button in the settings dialog). Settings marked with one player only exist there.

How the settings look: [Enigma2 receiver](../players/enigma2.md#settings), [Kodi](../players/kodi.md#settings).

<!-- BEGIN generated: settings (tools/docs.py) -->
### General

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Enable CamAlert | Yes |  | basic | both | Turn the HTTP API and the camera display on or off. |
| Cameras via | `go2rtc` | `go2rtc` / `direct` | basic | both | go2rtc is recommended. Without go2rtc, list your cameras in the camera file |
| go2rtc address | – |  | basic | both | Address of your go2rtc server, e.g. http://192.168.1.10:1984 |
| go2rtc RTSP port | `8554` | 1–65535 | expert | both | Usually 8554. Used for live view and the camera list. |
| Default camera | – |  | basic | both | Press OK to choose from the cameras in go2rtc. |
| Check certificates | Yes |  | expert | both | Turn off for a self-signed certificate (only in your own network). |
| Mosaic cameras | – |  | advanced | both | Press OK to choose up to 9 cameras for the mosaic. Empty = all. |
| Camera names | – |  | advanced | both | Press OK to give a camera its own name (empty = automatic). |
| Live view substreams | – |  | expert | both | For cameras the receiver cannot play (H.265/4K): front_door=front_door_sub uses that go2rtc stream for live view. |
| Camera file (direct mode) | – |  | expert | Kodi | Empty = cameras.conf in the add-on data folder. One camera per line: name \| rtsp-url \| snapshot-url |

### Display

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Display mode | `photo` | `photo` / `live` / `notify` | basic | both | Photo window keeps watching TV; live switches the channel to the camera. |
| Duration (seconds) | `30` s | 5–300, step 5 | basic | both | How long the camera stays on screen. |
| Window position | `top_right` | `top_right` / `top_left` / `bottom_right` / `bottom_left` | basic | both |  |
| Window size | `medium` | `small` / `medium` / `large` | basic | both |  |
| Return to what was playing | Yes |  | advanced | both | Switch back to what you were watching when the time is up. |
| Pause what is playing meanwhile | No |  | advanced | both | Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift. |
| Volume during live view (%) | `100`% | 0–100, step 10 | advanced | both | Percentage of the current volume while the camera is shown. 100 = unchanged. |
| Remote control in photo window | Yes |  | advanced | both | OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too. |
| Tour: seconds per camera | `8` s | 3–60 | advanced | both |  |
| Turn or mirror image | – |  | advanced | both | Press OK to turn a camera that hangs upside down (needs python3-pillow). |
| Refresh interval | – |  | advanced | both | Press OK to fetch a camera's photos less often (seconds), e.g. for a slow camera. |
| Multi-camera window layout | `auto` | `auto` / `vertical` / `horizontal` / `grid` | advanced | both | A request with 2-4 cameras shows them together in one multi-camera window. |
| Title size | `normal` | `small` / `normal` / `large` | advanced | both |  |
| Doorbell chime | `off` | `off` / `high` / `all` | advanced | both | Plays a short ding-dong for requests with priority high or alarm (doorbell). |
| Picons for the camera channels | No |  | advanced | Enigma2 | Makes a simple picon (camera + name) for every camera channel; existing picons are never replaced. |
| Live stream format | `mp4` | `mp4` / `hls` / `rtsp` | expert | Kodi | MP4 over HTTP works with every go2rtc set-up; RTSP needs go2rtc's RTSP port; HLS is the most robust but lags a few seconds. |

### Rules

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Not during a recording | No |  | advanced | Enigma2 | Ignore normal requests while the receiver is recording. |
| Only between certain times | No |  | basic | both | Ignore normal requests outside the chosen times. High and alarm always come through. |
| From | `07:00` |  | basic | both |  |
| Until | `23:00` |  | basic | both | May pass midnight, e.g. 07:00 to 23:00. |
| Wake up on alarm | No |  | advanced | both | Requests with priority 'alarm' switch the receiver (and TV via HDMI-CEC) on. |
| Do not disturb | No |  | basic | both | Ignores requests with normal priority (with 'Do not disturb blocks' also high). Alarm always comes through. Also via the API, MQTT and Home Assistant. |
| Do not disturb blocks | `normal` | `normal` / `high` | advanced | both |  |
| Cooldown per camera | – |  | expert | both | Seconds before the same camera is shown again, e.g. *=30\|garden=120 (* = all cameras). Alarm always. |
| Not while playing | `off` | `off` / `video` / `all` | advanced | both | Ignore normal requests while a video or recording plays (video) or while anything plays (all). High and alarm always come through. |

### Triggers

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Frigate events | No |  | advanced | both | Shows the camera when Frigate detects something (via MQTT, without Home Assistant). |
| Frigate MQTT prefix | `frigate` |  | expert | both | Usually 'frigate'. |
| Frigate objects | `person` |  | advanced | both | Comma separated, e.g. person,car. Empty = all objects. |
| Frigate camera names | – |  | advanced | both | Only if the names differ from go2rtc: frigate=go2rtc\|other=other_stream |
| Frigate priority | `normal` | `normal` / `high` / `alarm` | advanced | both |  |
| Foscam motion and sound alarms | No |  | advanced | both | Asks the Foscam cameras in the camera file for motion and sound alarms. |
| Foscam priority | `normal` | `normal` / `high` / `alarm` | advanced | both |  |
| Frigate address (for clips) | – |  | expert | both | Optional, e.g. http://192.168.1.10:5000 - lets you play the clip of an event from the event list. |
| Display mode | `photo` | `photo` / `live` / `notify` | advanced | both |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | both |  |
| Check every (seconds) | `2` s | 1–60 | expert | both |  |
| Display mode | `photo` | `photo` / `live` / `notify` | advanced | both |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | both |  |
| UniFi Protect events | No |  | advanced | both | Asks the UniFi Protect consoles in the camera file for events (doorbell, person, vehicle, ...). |
| UniFi Protect event types | `ring,person` |  | advanced | both | Comma separated: ring, person, vehicle, animal, package, motion. |
| UniFi Protect camera names | – |  | advanced | both | Only if the names differ from go2rtc: protect=go2rtc\|other=other_stream |
| UniFi Protect priority | `normal` | `normal` / `high` / `alarm` | advanced | both | A doorbell ring always gets at least the priority High. |
| Display mode | `photo` | `photo` / `live` / `notify` / `log` | advanced | both |  |
| Duration (seconds) | `30` s | 5–300, step 5 | advanced | both |  |
| Check every (seconds) | `5` s | 2–60 | expert | both |  |
| Per event type | – |  | expert | both | Optional: type=priority/mode/camera, e.g. ring=alarm/live\|motion=normal/log |
| Per camera | – |  | expert | both | Optional, wins over the event type: camera=priority/mode/seconds, e.g. front_door=high/photo/30\|driveway=normal/log |

### Camera control

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Camera control (PTZ) key | `blue` | `blue` / `yellow` / `red` / `green` / `off` | advanced | both | For cameras with PTZ in the camera file: this key switches PTZ mode on (arrows, CH+/CH-, OK = home). |
| Colour keys to Home Assistant | Yes |  | advanced | both | While a camera is on screen the colour keys send an event to Home Assistant (e.g. open the gate). |
| Camera user (default) | – |  | advanced | Kodi | Used when devices.conf has no user or password for a camera. |
| Camera password (default) | – |  | advanced | Kodi | Used when devices.conf has no user or password for a camera. |

### Home Assistant / MQTT

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| MQTT (Home Assistant without YAML) | No |  | advanced | both | Connects to your MQTT broker; with discovery the receiver appears in Home Assistant automatically. |
| MQTT broker address | – |  | advanced | both | IP address or name of the MQTT broker, e.g. 192.168.1.10 |
| MQTT port | `1883` | 1–65535 | advanced | both | Usually 1883. |
| MQTT user | – |  | advanced | both |  |
| MQTT password | – |  | advanced | both |  |
| Home Assistant discovery | Yes |  | advanced | both | Creates a device with a button per camera in Home Assistant. |
| Name in Home Assistant | – |  | advanced | both | Empty = CamAlert + the receiver's host name. |

### API

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Use HTTPS for the API | No |  | expert | both | Uses a self-signed certificate; callers must turn off certificate checking. |
| HTTP port | `8099` | 1024–65535 | expert | both | Port of the CamAlert API on this receiver (default 8099). |
| Allowed callers | `lan` | `lan` / `any` | advanced | both | 'Local network only' is recommended. |
| Access token (optional) | – |  | advanced | both | If set, callers must add ?token=... to every request. |

### Channel list (Enigma2)

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Camera list name | `Cameras` |  | advanced | Enigma2 | Name of the channel list created with the yellow button. |
| Update camera list automatically | Yes |  | advanced | Enigma2 | Checks every 30 minutes for new or removed cameras and updates the channel list. |
| Camera list position | `keep` | `keep` / `bottom` / `top` | expert | Enigma2 | Where the camera list appears among your channel lists. |

### Log and diagnostics

| Setting | Default | Values | Level | Players | What it does |
|---|---|---|---|---|---|
| Log level | `normal` | `off` / `errors` / `normal` / `verbose` | advanced | both | camalert.log in /home/root/logs (or /tmp). Passwords and tokens are never logged. |
| Remote syslog (host:port) | – |  | expert | both | Optional: also send the log via UDP (RFC 5424), e.g. to Loki/Alloy. |
| Event snapshots folder | `/tmp/camalert_events` |  | expert | Enigma2 | Small photos of the last 20 events (default /tmp/camalert_events). |
| Check for updates | Yes |  | advanced | Enigma2 | Looks once a day on GitHub for a new version and shows a message. |
<!-- END generated: settings -->
