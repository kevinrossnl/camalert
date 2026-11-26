# Home Assistant

There are three ways to connect CamAlert to Home Assistant. **The integration is recommended**: everything is done in
the user interface, no YAML. It works the same for Enigma2 receivers and Kodi: both are a CamAlert **player**.

| | Integration (recommended) | [MQTT](mqtt.md) | REST command |
|---|---|---|---|
| Set up via the UI only | yes | yes | no (YAML) |
| Needs | nothing extra | an MQTT broker | nothing extra |
| Works with the blueprints below | yes | no | no |

## 1. Integration

### Install

1. Open **Settings › Marketplace** (in older versions: HACS), search for **CamAlert**, install it and restart
   Home Assistant. CamAlert is in the HACS default list, so no extra repository is needed.
2. Only if CamAlert does not show up (for example an older HACS): menu **⋮ › Custom repositories**, add
   `https://github.com/kevinrossnl/camalert` with type **Integration**, then search again.
3. Without HACS: download `camalert-homeassistant-x.y.z.zip` from the
   [latest release](https://github.com/kevinrossnl/camalert/releases/latest) and unpack it into your Home Assistant
   `config` folder (it contains `custom_components/camalert/`), then restart.
4. **Settings › Devices & services › Add integration › CamAlert**. Enter the host name or IP address of the player
   (and the port, HTTPS and token if you changed them in CamAlert). Repeat for every player. *Reconfigure* on the
   entry changes the address, port, HTTPS or token later.

The device model shows *Enigma2 receiver* or *Kodi*. Certificates are checked by default; turn *Check certificates*
off only for the player's own self-signed certificate.

### What you get per player

- A **button per camera** ("Show Front door"), a **Mosaic** button and **Hide camera** (only what the player supports).
- A sensor **Camera on screen** (*Nothing* when no camera is shown).
- A switch **Do not disturb** (blocks normal requests; doorbell and alarm still come through, configurable on the
  player).
- An event entity **Remote button**: while a camera is on screen, the colour keys of the remote fire an event
  (`red`, `green`, `yellow`, `blue`, with the camera as attribute). The integration also fires the bus event
  `camalert_button` (`device_id`, `player`, `camera`, `button`; `receiver` is kept for older automations). Use the
  blueprint *CamAlert - remote button does something* to, for example, open the gate with GREEN when the doorbell
  camera shows who is there ([remote keys](../user/keys.md#colour-keys-to-home-assistant)).
- **Download diagnostics** on the integration entry: version, platform, capabilities, status, last events and the
  player's log (redacted).
- Actions for automations and scripts:

| Action | Fields |
|---|---|
| `camalert.show` | players (target), cameras (one or more: 2–4 are shown together in one multi-camera window), seconds, mode (photo / live / notify / strip), priority (normal / high / alarm), label (who/what, e.g. Person) |
| `camalert.ptz` | players, camera, move (up / down / left / right / zoom_in / zoom_out / home / stop) |
| `camalert.mosaic` | players, cameras (list), seconds |
| `camalert.hide` | players |

Target (*players*): one or more CamAlert players (devices), their entities or their areas; no target = every
player. Existing automations with `target: device_id:` keep working.

An action that fails (player not reachable, unknown camera, not supported) raises a translated error in the
automation trace; with several players all are tried first.

### Priority

What `normal`, `high` and `alarm` do on the player: [features › priorities](../user/features.md#priorities).

### Ready-made blueprints

Import them via **Settings › Automations & scenes › Blueprints › Import blueprint** and paste the address:

| Blueprint | What it does |
|---|---|
| [Doorbell or person](../../homeassistant/blueprints/camalert_doorbell.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_doorbell.yaml` | Always shows the door camera (priority high) |
| [Motion when armed or at set times](../../homeassistant/blueprints/camalert_motion.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_motion.yaml` | Motion → camera(s), only when the alarm is armed and/or between two times. Leave *Cameras* empty to show the camera named after the sensor (`binary_sensor.garden_motion` → `garden`) |
| [Alarm triggered](../../homeassistant/blueprints/camalert_alarm.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_alarm.yaml` | Wakes the players and shows a camera or live mosaic (priority alarm) |
| [Doorbell on the players and an LG TV](../../homeassistant/blueprints/camalert_doorbell_webos.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_doorbell_webos.yaml` | As *Doorbell or person*, plus a notification with a snapshot on an LG webOS TV (LG webOS TV integration); use *Snapshot URL* for a small picture, the TV refuses pictures over 100 KB; optional live view in the TV's browser ([details](../user/recipes.md)) |
| [Doorbell on the players and other screens](../../homeassistant/blueprints/camalert_doorbell_screens.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_doorbell_screens.yaml` | As *Doorbell or person*, plus live view on a Chromecast / Google TV and a notification on an Android TV / Fire TV, for TVs without CamAlert ([details](../user/recipes.md#other-screens)) |
| [Remote button does something](../../homeassistant/blueprints/camalert_button.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_button.yaml` | A colour key on the remote runs an action while a camera is on screen |

Then press **Create automation** on a blueprint and fill in the fields. Every input, its default and the rules for
changing them (frozen for 1.x): [blueprint inputs](../../homeassistant/blueprints/README.md).

**UniFi Protect users:** motion and person sensors only work when detection is enabled for that camera
(`switch.<camera>_detections_motion`).

## 2. MQTT (no integration needed)

See [MQTT](mqtt.md).

## 3. REST command (YAML)

For setups without the integration or MQTT: copy
[`homeassistant/camalert_package.yaml`](../../homeassistant/camalert_package.yaml) to
`<config>/packages/camalert.yaml` (with `homeassistant: packages: !include_dir_named packages` in
`configuration.yaml`) and restart. Then use `rest_command.camalert_show` with `host`, `cam`, `sec`, `mode`, `token`.
