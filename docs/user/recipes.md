# Recipes: other cameras, systems and situations

CamAlert itself only needs **one URL**: `http://<player>:8099/camalert/show?cam=<go2rtc name>` (see [API](../integrations/api.md)).
Use `POST` where the tool can (token in the `X-CamAlert-Token` header); the `GET` URLs below still work, but
are deprecated in API version 1 and may go away in a later major version.
Anything that can call a URL can trigger it. go2rtc does the camera side: whatever go2rtc can read, CamAlert can show.

## Cameras in a separate VLAN or subnet
Keep the cameras isolated and let go2rtc be the only bridge: go2rtc needs access to the camera VLAN, the players only
need access to go2rtc (port 1984 for snapshots, 8554 for live view). The players never talk to the cameras directly
(except the optional [devices file](devices.md) for Foscam/ONVIF). Firewall rule of thumb:

| From | To | Ports |
|---|---|---|
| go2rtc host | camera VLAN | RTSP 554 (or the camera's port) |
| players | go2rtc host | 1984, 8554 |
| Home Assistant / NVR | players | 8099 (CamAlert API) |

IPv6 works too: use a literal address such as `fd00::10` or `[fd00::10]:1984` as go2rtc address.

## Several sites (holiday home, office)
Run one go2rtc per site and add the other site's cameras to your local go2rtc as a relay
(`remote_garden: rtsp://other-site-go2rtc:8554/garden`), preferably over a VPN. A name prefix per site keeps them
apart in the camera list and in Home Assistant.

## H.265 / 4K cameras the player cannot play
Older Enigma2 receivers and small Kodi devices cannot decode H.265 or 4K. Two options:

1. Use the camera's substream for live view: add it to go2rtc (`front_door_sub: rtsp://.../stream2`) and set
   *Live view substreams* to `front_door=front_door_sub`. Snapshots keep using the main stream.
2. Let go2rtc transcode: `front_door_h264: ffmpeg:front_door#video=h264` (costs CPU on the go2rtc host).

## NVRs and event sources
| Source | How to trigger CamAlert |
|---|---|
| Frigate | built in (MQTT, see [Frigate](../integrations/frigate.md)), or Home Assistant |
| UniFi Protect | Home Assistant integration (motion / person / doorbell entities) + blueprint; Protect alarm manager webhook to the CamAlert URL |
| Blue Iris | Alert action "Web request or MQTT": `http://<player>:8099/camalert/show?cam=&CAM` (camera short name = go2rtc name) |
| Synology Surveillance Station | Action Rule, action type "Webhook" (or Notifications › Webhook) with the CamAlert URL |
| Scrypted | Home Assistant, or a webhook/automation plugin calling the URL |
| ZoneMinder | Event filter "Execute command": `wget -qO- "http://<player>:8099/camalert/show?cam=%MN%"` |
| Shinobi | Monitor settings › Global detector › Webhook on detection with the CamAlert URL |
| MotionEye | Motion notifications › "Call a web hook" with the CamAlert URL |
| go2rtc / anything else | any HTTP GET; MQTT `camalert/<id>/show` |

Add `&label=Person&priority=high` where the system can tell you what it saw.

## Cloud cameras without RTSP (Ring, Nest, Eufy, Arlo, Tapo cloud)
Add them to Home Assistant with their integration, then let go2rtc read the Home Assistant camera entity
(go2rtc `hass:` source, e.g. `front_door: hass:camera.front_door` with go2rtc's Home Assistant connection) – from then on
they are normal go2rtc cameras for CamAlert. Expect a few seconds of delay.

## Doorbells with their own protocol (without Home Assistant)
| Doorbell | Direct trigger |
|---|---|
| Reolink | Push/webhook in the app or web UI (newer firmware) to the CamAlert URL with `priority=high` |
| DoorBird | HTTP(S) "Favorites" + schedule for the doorbell button: call the CamAlert URL |
| Dahua VTO | Event to an HTTP server/alarm centre, or via Home Assistant |
| Hikvision doorbell | "Notify surveillance center"/HTTP listening host, or via Home Assistant |

Two-way audio is not possible on the player. To talk, also send a notification with the camera to your phone (a
`notify` action in the same automation, next to `camalert.show`) and answer in the doorbell's own app; the
blueprints do not have an input for that yet.

## Without Home Assistant or MQTT
| System | Example |
|---|---|
| Node-RED | `http request` node, method POST, URL `http://<player>:8099/camalert/show`, payload `{"cam": "front_door", "priority": "high"}` |
| ioBroker | Script: `httpGet('http://<player>:8099/camalert/show?cam=front_door')` |
| openHAB | Rule action: `sendHttpGetRequest("http://<player>:8099/camalert/show?cam=front_door")` |
| Domoticz | Device "On action": `http://<player>:8099/camalert/show?cam=front_door` |
| Homey | Flow card "HTTP request" (HTTP request flow cards app) with the URL |
| Jeedom | Scenario "HTTP request" with the URL |

## Presence, quiet hours, several players
- *Only when someone is home*: the doorbell, LG TV and motion blueprints have *Only when someone is home*
  (`presence`): pick persons, device trackers or `zone.home`; empty = always. *Only when away* (for example a
  notification on the phone instead): use a plain automation with a `state` condition, or *Take control* of the
  blueprint automation in Home Assistant.
- *Doorbell on the phone too*: in the doorbell blueprints fill in *Also notify a phone* (`phone_notify`, the
  notify action of the Companion app) and optionally *Camera entity for the phone*: the phone shows the picture,
  tapping it opens the camera. It also arrives when nobody is home (the TV part waits for *Only when someone is
  home*). Talking back from the TV is not possible (#98). *Do not disturb* with *Do not disturb blocks* = normal and doorbell: everything is logged in the event
  list, only alarms are shown.
- *Cooldown per camera*: `*=30` avoids showing the same camera again and again; a camera that is still on screen is
  extended instead.
- *Per player camera sets*: each player has its own camera list/mosaic; in Home Assistant pick only the players
  that should react. *Follow me*: target all players – players in standby ignore normal and doorbell requests, so
  only the box that is on shows the camera.

## Other screens
Home Assistant can show the same camera on screens without CamAlert. The blueprint *CamAlert - doorbell on the
players and other screens* does the CamAlert players plus:

- **Chromecast / Google TV** (*Chromecast / Google TV* + *Camera entity for Chromecast*): live view full screen with
  `camera.play_stream`, stopped after the duration. The Chromecast then shows its home screen, not the app from
  before.
- **Android TV / Fire TV** (*Android TV / Fire TV notification*, the notify action of the "Notifications for Android
  TV / Fire TV" integration): a small window with the text and, with *Picture for Android TV*, a small go2rtc frame
  that the TV downloads itself.
- **Samsung Tizen** has no window over other apps and no notification with a picture in Home Assistant: use the
  Chromecast input if the TV has Chromecast built in.

For an LG TV there is a ready-made blueprint, *CamAlert - doorbell on the players and an LG webOS TV*
([home-assistant.md](../integrations/home-assistant.md#ready-made-blueprints)): the players show the camera and the
LG TV gets a notification with a snapshot (only while it is on). Find the TV's notify action under
**Developer tools › Actions** (`notify.lg_webos_tv_...`). The snapshot is saved in `/media` by default; do not
use `www`, which Home Assistant serves without login.

**Live view on the LG TV** (*Live view on the LG TV*, needs *LG TV media player*): the TV opens a page with the
stream in its web browser for the duration, for example go2rtc's
`http://192.168.1.10:1984/stream.html?src=front_door&mode=mse`, and then goes back to the input or app it showed
before (the blueprint saves a scene of the TV, `scene.camalert_webos_before`). The TV must reach that address.

The LG TV refuses pictures over **100 KB** (102400 bytes); a snapshot of a main stream is usually larger, and then
the TV shows nothing at all (#74). Use **Snapshot URL** instead: a small go2rtc frame such as
`http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640` (about 25 KB). It is downloaded with the
**Downloader** integration (Settings › Devices & services › Add integration › Downloader; download folder `/media`,
the folder of *Snapshot file*). No YAML and no restart needed. If the download fails or takes more than 15 seconds,
the notification is sent as text only.

## Monitoring
See [monitoring](../integrations/monitoring.md).
