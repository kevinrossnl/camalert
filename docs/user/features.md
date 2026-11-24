# Features

Everything on this page works the same on an [Enigma2 receiver](../players/enigma2.md) and on
[Kodi](../players/kodi.md), unless it says otherwise. Every setting is listed in [settings](settings.md).

## Priorities

| Priority | Use for | On the player |
|---|---|---|
| `normal` | motion around the house | follows the rules below: do not disturb, active hours, cooldown, not while playing |
| `high` | doorbell, person at the door | always (never in standby); *Do not disturb blocks* can block it too |
| `alarm` | alarm goes off | always; wakes the player from standby (Enigma2) or switches the screen on (Kodi, HDMI-CEC) with *Wake up on alarm* |

## Do not disturb and other rules

*Do not disturb* (setting, API `POST /camalert/dnd`, MQTT `camalert/<id>/dnd/set`, switch in Home Assistant) blocks
requests with priority `normal`. *Do not disturb blocks* can also block `high` (doorbell); `alarm` always comes
through. Ignored requests are still listed in the event list, with the reason.

- *Only between certain times* (*From* / *Until*): normal requests outside these hours are ignored.
- *Cooldown per camera* (`*=30` or `front_door=60`): the same camera is not shown again within that time; a camera
  that is still on screen is extended instead.
- *Not while playing*: off / while a recording or video plays / while anything plays (Enigma2: except a camera
  channel). Enigma2 also has *Not during a recording*.

## Multi-camera window

A request with 2–4 cameras (`cam=front_door,garden`, or a list in `camalert.show`) shows them together in one
**multi-camera window**, so the TV stays visible. *Multi-camera window layout*: automatic (2–3 below each other, 4 as
2 x 2), below each other, next to each other or 2 x 2. More than 4 cameras, or `/camalert/mosaic`, opens the
full-screen [mosaic](mosaic.md).

## Who / what in the title

`label` (API, MQTT JSON, `camalert.show`, blueprints) is shown before the camera name: "Person · Front door".
Frigate events use the sub label (a recognised face or plate) or the object label; Foscam alarms show "Motion".

## Camera names

*Camera names* (OK on the row): give a camera its own name (`front_door` → "Front door (street)"). Without one,
CamAlert makes a name from the go2rtc name ("front_door" → "Front door"). The name is used everywhere: channel list,
photo window, mosaic, tour and Home Assistant.

## Turning and mirroring the image

*Turn or mirror image* (OK on the row): per camera *mirror*, *upside down (flip)* or *turned 180 degrees*. It is
applied to the snapshots in the photo window, the multi-camera window, the mosaic and the tour (Enigma2 needs
python3-pillow). Live view is never turned by the player: turn the stream itself in go2rtc, which then also fixes it
for every other viewer:

```yaml
streams:
  garden: ffmpeg:rtsp://user:password@192.168.1.20/stream1#video=h264#raw=-vf transpose=2,transpose=2
```

(`#raw=-vf hflip` mirrors, `vflip` flips; this costs CPU on the go2rtc host because the video is re-encoded.)

## Refresh interval

*Refresh interval* (OK on the row): per camera how often the snapshot is fetched (default as fast as possible, about
every 0.2–0.3 s). Useful for slow cameras or a weak network; used by the photo window, the multi-camera window, the
mosaic and the tour. A camera that does not answer twice in a row shows *Camera not reachable* in its tile.

## Colour keys to Home Assistant

While a camera is on screen (photo window, multi-camera window, live view, mosaic, tour) the colour keys send an
event to Home Assistant (via the integration's webhook and, with MQTT, `camalert/<id>/button`). In the photo window
and live view the key is used for this only; in the mosaic and tour the screen keeps its own function too (GREEN =
live view in the tour). The *Camera control (PTZ) key* (default BLUE) is not sent for cameras that have PTZ: it
switches camera control on. Turn the whole feature off with *Colour keys to Home Assistant*. Example:
[remote keys › colour keys](keys.md#colour-keys-to-home-assistant).

## Doorbell chime

*Doorbell chime*: off / for high and alarm requests / for every request. Enigma2 plays its own ding-dong next to the
TV sound ([details](../players/enigma2.md#doorbell-chime)); Kodi follows Kodi's volume and mute.

## Event list and diagnostics

The **event list** shows the last 20 requests with time, camera, who/what, source (API, Home Assistant, MQTT,
Frigate, Foscam), priority, what CamAlert did and why, and a small snapshot. OK shows that camera again.
**Diagnostics** checks go2rtc, a snapshot of every camera, the API port, MQTT, the last API call (and whether it came
from Home Assistant), the devices file and do not disturb, and shows the end of the log. Where to find them:
[Enigma2](../players/enigma2.md#what-you-see), [Kodi](../players/kodi.md#settings).

## Logging

CamAlert writes its own log `camalert.log` (2 x 1 MB). *Log level*: off / errors only / normal (every request with
source, decision and reason) / verbose. Passwords, tokens and `user:password@` in addresses are always removed.
*Remote syslog*: `host:port` to also send it via UDP (RFC 5424, facility local0), e.g. to Grafana Alloy / Loki or
rsyslog ([monitoring](../integrations/monitoring.md)). Read it on the TV (diagnostics), via `/camalert/log`, or with
*Download diagnostics* in Home Assistant.

## Frigate and Foscam without Home Assistant

See [Frigate](../integrations/frigate.md) and [camera control and Foscam alarms](devices.md).
