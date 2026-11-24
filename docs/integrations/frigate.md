# Frigate

CamAlert can listen to [Frigate](https://frigate.video) itself, over MQTT, without Home Assistant. (With Home
Assistant you can also use the Frigate integration's entities with the motion blueprint, see
[Home Assistant](home-assistant.md).)

1. Turn on MQTT on the player (*MQTT broker address*, user, password; see [MQTT](mqtt.md)) – the same broker Frigate
   uses.
2. Turn on *Frigate events* (section Triggers).

A `new` or `update` event on `frigate/events` shows that camera with its label (the sub label – a recognised face or
plate – or the object label: "Person · Driveway").

| Setting | Default | What |
|---|---|---|
| *Frigate MQTT prefix* | `frigate` | topic prefix of your Frigate |
| *Frigate objects* | `person` | which labels count (comma separated; empty = all) |
| *Frigate camera names* | – | only if your Frigate names differ from go2rtc: `frigate_name=go2rtc_name\|...` |
| *Frigate priority* | normal | normal / high / alarm ([priorities](../user/features.md#priorities)) |
| *Display mode*, *Duration (seconds)* | photo window, 30 | how Frigate events are shown |
| *Frigate address (for clips)* | – | e.g. `http://192.168.1.10:5000`; then the event list can play the clip of a Frigate event (GREEN on Enigma2, OK on Kodi) |

Frigate events go through the same rules as every other request (do not disturb, active hours, cooldown) and are
listed in the event list with source *Frigate*.
