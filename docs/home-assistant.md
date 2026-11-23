# Home Assistant: show a camera on motion or doorbell

## 1. Add the CamAlert package

1. Make sure `configuration.yaml` contains:

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

2. Copy [`homeassistant/camalert_package.yaml`](../homeassistant/camalert_package.yaml) to `<config>/packages/camalert.yaml` (for example with the *File editor* app).
3. **Developer tools › YAML › Check configuration**, then restart Home Assistant (first time only).

You now have two actions: `rest_command.camalert_show` and `rest_command.camalert_hide`.

## 2. Import the blueprint

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkevinrossnl%2Fcamalert%2Fblob%2Fmain%2Fhomeassistant%2Fblueprints%2Fcamalert_show_camera.yaml)

Or: **Settings › Automations & scenes › Blueprints › Import blueprint** and paste
`https://github.com/kevinrossnl/camalert/blob/main/homeassistant/blueprints/camalert_show_camera.yaml`

## 3. Create the automation

Press **Create automation** on the blueprint and fill in:

| Field | Example |
|---|---|
| Trigger | `binary_sensor.front_door_motion` (or a person / doorbell sensor) |
| Receiver IP address | `192.168.1.30` |
| Receiver media player | the receiver's media player from the *Enigma2* integration (optional) |
| Camera | `front_door` (the name in go2rtc) |
| Duration | 30 |
| Display mode | Photo window |

Make one automation per receiver (living room, kitchen, ...).

**UniFi Protect users:** the camera's motion sensor only works when *motion detection* is enabled for that camera (switch `switch.<camera>_detections_motion`).

## Manual test

**Developer tools › Actions**:

```yaml
action: rest_command.camalert_show
data:
  host: 192.168.1.30
  cam: front_door
  sec: 15
```
