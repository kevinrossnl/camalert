# MQTT

With MQTT the player appears in Home Assistant without the integration (MQTT discovery), and any MQTT client can
control it. The same topics on Enigma2, Kodi and Android TV.

1. In CamAlert on the player: **MQTT** on, enter the broker address, user and password, keep **Home Assistant
   discovery** on, save.
2. The player appears automatically under **Settings › Devices & services › MQTT** with the same buttons and sensor
   as with the integration.
3. In automations, use the action *Button: Press* on e.g. "Show Front door".

The player keeps the discovered entities tidy: a camera that is renamed or removed in go2rtc (or a helper stream of
*Keep cameras ready*) loses its button, and turning discovery off removes all of the player's entities. It reads its
own retained discovery messages (`homeassistant/+/camalert_<id>/+/config`) after connecting and clears the stale ones
with an empty retained message, so this also works after a reinstall. While the camera list cannot be fetched (go2rtc
not reachable) nothing is removed.

Topics (`<id>` = player id, see the device in Home Assistant or `/camalert/status`):

| Topic | Payload |
|---|---|
| `camalert/<id>/show` | camera name, or JSON `{"cam": "garden", "sec": 20, "mode": "live", "priority": "high", "label": "Person"}` (`"sec": 0` = until `hide`, at most 600 s) |
| `camalert/<id>/mosaic` | empty, or `cam1,cam2,...` |
| `camalert/<id>/hide` | empty |
| `camalert/<id>/state` | (published) camera on screen or `none` |
| `camalert/<id>/dnd/set` | `ON` / `OFF`: do not disturb (discovery creates a switch) |
| `camalert/<id>/dnd` | (published) `ON` / `OFF` |
| `camalert/<id>/button` | (published) `{"event_type": "green", "camera": "front_door", ...}` when a colour key is pressed while a camera is on screen (discovery creates an event entity) |
| `camalert/<id>/availability` | (published) `online` / `offline` |

The blueprints need the integration; with MQTT only, use the discovered buttons or publish to `camalert/<id>/show`.
[Frigate](frigate.md) events can come in over the same broker.
