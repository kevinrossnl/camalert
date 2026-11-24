# Remote buttons -> Home Assistant

While a camera is on screen, RED, GREEN, YELLOW and BLUE on the remote send an event to Home Assistant. Example: the
doorbell rings, the camera appears, you see the parcel courier and press GREEN to open the gate.

1. Add the receiver with the CamAlert integration (it sets up a local webhook on the receiver automatically), or use
   MQTT discovery (event entity *Remote button*).
2. Import the blueprint *CamAlert - remote button does something*
   (`homeassistant/blueprints/camalert_button.yaml`), choose the receivers, the key, optionally the camera, and the action.

Or write your own automation:

```yaml
triggers:
  - trigger: event
    event_type: camalert_button
    event_data:
      button: green
      camera: front_door
actions:
  - action: cover.open_cover
    target:
      entity_id: cover.gate
```

The *PTZ key* (default BLUE) is not sent for cameras that have PTZ (see [devices](devices.md)); choose another PTZ key or
switch it off in the settings if you need BLUE in Home Assistant.
