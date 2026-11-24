# More features

## Do not disturb
*Do not disturb* (setting, API `/camalert/dnd?on=1|0`, MQTT `camalert/<id>/dnd/set`, switch in Home Assistant) blocks
requests with priority `normal`. *Do not disturb blocks* can also block `high` (doorbell); `alarm` always comes through.
*Not while playing a recording or video* ignores normal requests while you watch a recording or a media file.

## Several cameras in one window
A request with 2–4 cameras (`cam=front_door,garden`, or a list in `camalert.show`) shows them together in one corner
window, so the TV stays visible. *Layout with several cameras*: automatic (2–3 below each other, 4 as 2 x 2), below each
other, next to each other or 2 x 2. More than 4 cameras, or `/camalert/mosaic`, opens the full-screen mosaic.

## Who / what in the title
`label` (API, MQTT JSON, `camalert.show`) is shown before the camera name: "Person · Front door". Frigate events use the
sub label (a recognised face or plate) or the object label; Foscam alarms show "Motion".

## Turning and mirroring the image
*Turn or mirror image* (OK on the row): per camera *mirror*, *upside down (flip)* or *turned 180 degrees*. It is applied to
the snapshots in the photo window, the corner window with several cameras, the mosaic and the tour.

Enigma2 images do not ship an image library by default, so this needs **python3-pillow** (in the openATV and OpenPLi
feeds; the CamAlert package recommends it: `opkg install python3-pillow`). Without it the setting has no effect.
Live view (switching to the stream) is never turned by the receiver: turn the stream itself in go2rtc, which then also
fixes it for every other viewer:

```yaml
streams:
  garden: ffmpeg:rtsp://user:password@192.168.1.20/stream1#video=h264#raw=-vf transpose=2,transpose=2
```

(`#raw=-vf hflip` mirrors, `vflip` flips; this costs CPU on the go2rtc host because the video is re-encoded.)

## Refresh interval
*Refresh interval* (OK on the row): per camera how often the snapshot is fetched (default as fast as possible, about
every 0.2–0.3 s). Useful for slow cameras or a weak network; used by the photo window, the corner window, mosaic and tour.

## Frigate without Home Assistant
*Frigate events* (MQTT section) subscribes to `frigate/events` on your broker. A `new` or `update` event shows that
camera. *Frigate objects*: which labels count (default `person`; empty = all). *Frigate camera names*: only if your
Frigate names differ from go2rtc (`frigate_name=go2rtc_name|...`). *Frigate priority*: normal or high.
*Frigate address (for clips)*: e.g. `http://192.168.1.10:5000`; then the event list can play the clip of a Frigate event
(GREEN).

## Colour keys to Home Assistant
While a camera is on screen (photo window, corner window, live view, mosaic, tour) the colour keys send an event to
Home Assistant (via the integration's webhook and, with MQTT, `camalert/<id>/button`). In the photo window and live
view the key is used for this only; in the mosaic and tour the screen keeps its own function too (GREEN = live).
The *PTZ key* (default BLUE) is not sent for cameras that have PTZ: it switches PTZ mode on. Turn the whole feature off
with *Colour keys to Home Assistant*.

## Doorbell chime
*Doorbell chime* plays a short self-made ding-dong (`chime.wav`, GPL like the rest of CamAlert) when a request with
priority high or alarm is shown. It is played through ALSA with gstreamer, next to the TV sound, so the TV keeps
running. Whether the receiver's mute also silences it depends on the model.

## Picons for the camera channels
*Picons for the camera channels* draws a simple picon (camera icon and the camera name) for every channel in the camera
list, named the way Enigma2 looks up picons of stream channels (service name, e.g. `frontdoor.png`). It needs
python3-pillow and a writable picon folder (`/media/*/picon` or `/usr/share/enigma2/picon`); picons that already exist
are never replaced, and a read-only (network) picon folder is left alone.

## Event list and diagnostics
*CamAlert events* (blue/extensions menu, or MENU in the settings) shows the last 20 requests with time, camera, who/what,
source (API, Home Assistant, MQTT, Frigate, Foscam), priority, what CamAlert did and why, and a small snapshot
(*Event snapshots folder*, default `/tmp/camalert_events`). OK shows that camera again.

*Diagnostics* (MENU in the settings) checks: go2rtc reachable, a snapshot of every camera (with time), the API port,
MQTT, the last API call (and whether it came from Home Assistant), the devices file, do not disturb, and shows the end of
the log.

## Logging
CamAlert writes its own log `camalert.log` (in `/home/root/logs`, or `/tmp` when there is no room), at most 2 x 1 MB.
*Log level*: off / errors only / normal (every request with source, decision and reason) / verbose. Passwords, tokens and
`user:password@` in addresses are always removed. *Remote syslog*: `host:port` to also send it via UDP (RFC 5424,
facility local0), e.g. to Grafana Alloy / Loki or rsyslog. Read it on the TV (Diagnostics), via `/camalert/log`, or with
*Download diagnostics* in Home Assistant.

## Updates
*Check for updates* looks once a day on GitHub for a newer release and shows a message once per version.
Each release is also published as an opkg feed, so the receiver's normal software update picks it up:

```sh
wget -O /etc/opkg/camalert-feed.conf https://kevinrossnl.github.io/camalert/camalert-feed.conf
opkg update && opkg install enigma2-plugin-extensions-camalert
```

or create `/etc/opkg/camalert-feed.conf` yourself with the line
`src/gz camalert https://kevinrossnl.github.io/camalert`.
