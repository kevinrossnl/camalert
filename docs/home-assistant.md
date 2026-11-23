# Home Assistant

There are three ways to connect CamAlert to Home Assistant. **The integration is recommended**: everything is done in the user interface, no YAML.

| | Integration (recommended) | MQTT | REST command |
|---|---|---|---|
| Set up via the UI only | yes | yes | no (YAML) |
| Needs | nothing extra | an MQTT broker | nothing extra |
| Works with blueprints below | yes | no | no |

## 1. Integration

### Install

1. Open **Settings › Marketplace** (in older versions: HACS) › menu **⋮ › Custom repositories**.
2. Add `https://github.com/kevinrossnl/camalert`, type **Integration**.
3. Search for **CamAlert**, install it and restart Home Assistant.
4. **Settings › Devices & services › Add integration › CamAlert**. Enter the IP address of your receiver (and the port, HTTPS and token if you changed them in CamAlert). Repeat for every receiver.

### What you get per receiver

- A **button per camera** ("Show Front door"), a **Mosaic** button and **Hide camera**.
- A sensor **Camera on screen**.
- Actions you can use in automations and scripts:

| Action | Fields |
|---|---|
| `camalert.show` | receivers (target), camera, seconds, mode (photo / live / notify), priority (normal / high / alarm) |
| `camalert.mosaic` | receivers, cameras (list), seconds |
| `camalert.hide` | receivers |

### Priority

| Priority | Use for | On the receiver |
|---|---|---|
| `normal` | motion around the house | follows the receiver's rules: active hours, not during a recording |
| `high` | doorbell, person at the door | always (but never in standby) |
| `alarm` | alarm goes off | always; wakes the receiver from standby if *Wake receiver on alarm* is on |

### Ready-made blueprints

Import them via **Settings › Automations & scenes › Blueprints › Import blueprint** and paste the address:

| Blueprint | What it does |
|---|---|
| [Doorbell or person](../homeassistant/blueprints/camalert_doorbell.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_doorbell.yaml` | Always shows the door camera (priority high) |
| [Motion when armed or at set times](../homeassistant/blueprints/camalert_motion.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_motion.yaml` | Motion → camera(s), only when the alarm is armed and/or between two times. Leave *Cameras* empty to show the camera named after the sensor (`binary_sensor.garden_motion` → `garden`) |
| [Alarm triggered](../homeassistant/blueprints/camalert_alarm.yaml) `https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_alarm.yaml` | Wakes the receivers and shows a camera or live mosaic (priority alarm) |

Then press **Create automation** on a blueprint and fill in the fields.

**UniFi Protect users:** motion and person sensors only work when detection is enabled for that camera (`switch.<camera>_detections_motion`).

## 2. MQTT (no integration needed)

1. In CamAlert on the receiver: **MQTT** on, enter the broker address, user and password, keep **Home Assistant discovery** on, save.
2. The receiver appears automatically under **Settings › Devices & services › MQTT** with the same buttons and sensor.
3. In automations, use the action *Button: Press* on e.g. "Show Front door".

Topics (`<id>` = receiver id, see the device in Home Assistant):

| Topic | Payload |
|---|---|
| `camalert/<id>/show` | camera name, or JSON `{"cam": "garden", "sec": 20, "mode": "live", "priority": "high"}` |
| `camalert/<id>/mosaic` | empty, or `cam1,cam2,...` |
| `camalert/<id>/hide` | empty |
| `camalert/<id>/state` | (published) camera on screen or `none` |
| `camalert/<id>/availability` | (published) `online` / `offline` |

## 3. REST command (YAML)

For setups without the integration or MQTT: copy [`homeassistant/camalert_package.yaml`](../homeassistant/camalert_package.yaml) to `<config>/packages/camalert.yaml` (with `homeassistant: packages: !include_dir_named packages` in `configuration.yaml`) and restart. Then use `rest_command.camalert_show` with `host`, `cam`, `sec`, `mode`, `token`.
