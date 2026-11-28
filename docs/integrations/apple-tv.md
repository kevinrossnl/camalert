# Apple TV: the doorbell through Apple Home

There is no CamAlert player for Apple TV: tvOS does not let an app draw over other apps (#97). An Apple TV 4K can
show a doorbell alert with the camera by itself, through Apple Home. With Home Assistant's **HomeKit Bridge** the
same doorbell that triggers CamAlert also rings on the Apple TV: CamAlert on the other TVs, Apple Home on the
Apple TV, at the same moment.

## What you need

- Home Assistant with the camera (for example through go2rtc or the camera's own integration) and a doorbell entity:
  a `binary_sensor` that turns on when someone rings, or an `event` entity of the doorbell.
- An Apple TV 4K signed in with the Apple Account of your Apple home.

## Steps

1. **HomeKit Bridge in accessory mode for the camera.** In Home Assistant add the *HomeKit Bridge* integration once
   more, in **accessory** mode, with only the doorbell camera included. Cameras must be in accessory mode; one
   bridge entry per camera.
2. **Link the doorbell.** Give the camera the option `linked_doorbell_sensor` with the entity id of the doorbell
   (`binary_sensor` or `event`). A bridge made in the UI is configured in the UI only; with YAML it goes under
   `entity_config` of the camera:

   ```yaml
   homekit:
     - name: Front door camera
       mode: accessory
       filter:
         include_entities:
           - camera.front_door
       entity_config:
         camera.front_door:
           linked_doorbell_sensor: binary_sensor.front_door_doorbell
   ```

3. **Pair** the new accessory in the Home app on your iPhone (Home Assistant shows the pairing code as a
   notification) and put it in the right room.
4. **CamAlert as usual:** keep the CamAlert doorbell blueprint on the same doorbell entity for the Enigma2, Kodi and
   Android TV players (see [Home Assistant](home-assistant.md)).

When someone rings, Apple Home sends the doorbell alert to the Apple TV; from the camera view in the Apple Home tab
you can keep watching in Picture in Picture.

## Limits

- What the Apple TV shows and for how long is up to Apple Home, not CamAlert: no priorities, no *Do not disturb* of
  CamAlert, no position or size.
- Only for the doorbell (and for cameras you open yourself in the Apple Home tab); motion of other cameras does not
  pop up on the Apple TV this way.
- Notification settings (for example which members of the home get alerts) are in the Home app.

## Sources

- Home Assistant: [HomeKit Bridge, `linked_doorbell_sensor` and accessory mode](https://www.home-assistant.io/integrations/homekit/)
- Apple: [Monitor cameras in the Apple Home tab on Apple TV 4K](https://support.apple.com/guide/tv/atvb90537bb0/tvos)
