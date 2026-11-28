# CamAlert documentation

CamAlert shows IP cameras on the TV of a **player**: an Enigma2 receiver, a Kodi device (Kodi 19 or newer) or an
Android TV / Fire TV device with the CamAlert app. The
words used on screen and in these pages are listed in the [glossary](user/glossary.md).

## Users

| Page | What |
|---|---|
| [Step-by-step guide](user/guide.md) | From nothing to a camera in the photo window on your TV |
| [go2rtc as Home Assistant app](user/go2rtc-home-assistant.md) | Easiest if you already run Home Assistant OS |
| [go2rtc in Docker / TrueNAS / Synology](user/go2rtc-docker.md) | Run go2rtc as its own container |
| [Camera stream addresses](user/cameras.md) | RTSP addresses for popular camera brands |
| [Without go2rtc](user/without-go2rtc.md) | Connect the player directly to the cameras |
| [Features](user/features.md) | Do not disturb, multi-camera window, labels, turning, colour keys, event list, logging |
| [Several cameras at once](user/mosaic.md) | Photo mosaic or live mosaic channel |
| [Camera control and Foscam alarms](user/devices.md) | PTZ (ONVIF, Foscam) and Foscam motion/sound alarms |
| [Remote keys](user/keys.md) | Which key does what, on both players (generated from the key map) |
| [Settings](user/settings.md) | Every setting with its default (generated from the settings schema) |
| [Recipes](user/recipes.md) | VLANs, several sites, H.265, NVRs, doorbells, other systems |
| [Troubleshooting](user/troubleshooting.md) | Black picture, slow start, nothing appears, ... |
| [Glossary](user/glossary.md) | The CamAlert terms in English, Dutch, German, French, Italian and Polish |

## Players

| Page | What |
|---|---|
| [Enigma2 receiver](players/enigma2.md) | Install, update feed, settings screen, channel list, picons, chime, files |
| [Kodi](players/kodi.md) | Install, settings, what you see, platforms, differences with Enigma2 |
| [Android TV and Fire TV](players/androidtv.md) | The app without Kodi (in development): sideload with ADB, overlay permission, start at boot |
| [Web player and browser extension](players/web.md) | Wall tablets, TV browsers and desktop browsers, served by the Home Assistant integration |

## Integrations

| Page | What |
|---|---|
| [Home Assistant](integrations/home-assistant.md) | Integration, actions, priorities, blueprints, REST command |
| [MQTT](integrations/mqtt.md) | Topics and Home Assistant discovery (no integration needed) |
| [Frigate](integrations/frigate.md) | Frigate events straight from MQTT, without Home Assistant |
| [HTTP API](integrations/api.md) | For other systems and scripts |
| [Monitoring](integrations/monitoring.md) | Prometheus metrics, Grafana dashboard, remote syslog |
| [Loxone, KNX, ioBroker, openHAB, Homey](integrations/smart-home.md) | The doorbell on the TV from other smart-home systems, with examples |
| [Apple TV](integrations/apple-tv.md) | No CamAlert player, but the doorbell through Apple Home and Home Assistant's HomeKit Bridge |

## Developers

| Page | What |
|---|---|
| [Compatibility](dev/compatibility.md) | Which Enigma2 images and Kodi versions are tested, and how |
| [Translating](dev/translating.md) | The master catalogue and how to add or improve a language |
| [Privacy checklist](dev/privacy.md) | What CI checks, and what you check before adding text or images |
| [Screenshots](dev/screenshots.md) | How the screenshots are made without camera or TV content |
| [End-to-end tests](dev/e2e.md) | Scenarios on a real receiver or Kodi player: muted, state restored |
| [Docs](dev/docs.md) | Structure of these pages, generated parts, docs tests |

Repository rules for contributors: [DEVELOPMENT.md](../DEVELOPMENT.md); tests: [tests/README.md](../tests/README.md).
