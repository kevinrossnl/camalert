# Remote keys

Which key does what is defined once, in the core key map (`core/camalert_core/keymap.py`); the screens, their key
hints and this table all come from it. The same actions on both players; Kodi uses its own key names (BACK for EXIT,
SELECT/ENTER for OK). On both players a key that CamAlert does not use in the photo window closes the window and then
does its normal job, so you can just keep zapping or navigating.

<!-- BEGIN generated: keys (tools/docs.py) -->
### Photo window and multi-camera window

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| live | OK | OK | OK |
| other camera | ◀, ▶ | ◀, ▶ | ◀, ▶ |
| camera control | PTZ colour key | PTZ colour key / MENU / INFO | PTZ colour key |
| actions | – | – | MENU |
| close | EXIT | BACK | BACK |
| keep working | volume, mute | volume, mute | volume, mute |

### Camera control (PTZ)

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| move | ▲, ▼, ◀, ▶ | ▲, ▼, ◀, ▶ | ▲, ▼, ◀, ▶ |
| zoom | CH+, CH- | CH+, CH- | FF / CH+, REW / CH- |
| home position | OK | OK | OK |
| end camera control | EXIT / PTZ colour key | BACK / MENU / INFO / PTZ colour key | BACK / MENU / PTZ colour key |
| keep working | volume, mute | volume, mute | volume, mute |

### Tour

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| other camera | ◀, ▶ | ◀, ▶ | ◀, ▶ |
| pause | OK | OK | OK |
| live | GREEN / PLAY | GREEN / PLAY / ▲ | GREEN / PLAY |
| close | EXIT | BACK / STOP | BACK / STOP |

### Mosaic

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| close | OK / EXIT | OK / BACK / STOP | OK / BACK / STOP |

### Live view

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| other camera | – | ◀, ▶ | ◀, ▶ |
| pause | – | PAUSE / PLAY | PLAY / PAUSE |
| camera control | PTZ colour key | PTZ colour key / MENU / INFO | PTZ colour key |
| actions | – | – | MENU |
| close | – | BACK / STOP | BACK / STOP |
| (Enigma2: the camera is a normal channel; zap away or wait) | – | – | – |

### Action menu (Android TV: MENU)

| Action | Enigma2 | Kodi | Android TV |
|---|---|---|---|
| choose | – | – | ▲, ▼ |
| confirm | – | – | OK |
| back | – | – | BACK / MENU |

Kodi's skin fonts have no ◀ ▶: its on-screen hints show `< >` and `^ v` instead.
The *PTZ colour key* is the colour key chosen in *Camera control (PTZ) key* (default BLUE); it only
switches camera control on for cameras with PTZ. Fire TV remotes have no colour keys: there MENU
switches camera control on, FF/REW zoom and PLAY/PAUSE starts live view in the tour.
<!-- END generated: keys -->

## Look at the door: one key for the default camera

One key that always shows the default camera at once, in your display mode (#13). It comes through *Do not disturb*
and the time rules, and plays no doorbell chime: you asked for it yourself.

- **Enigma2:** the plugin adds *CamAlert: default camera* to the extensions (BLUE) menu. Put it on a key of your
  choice with the image's key settings (openATV: *Menu > Setup > System > Hotkey*; OpenPLi: *Menu > Setup >
  Usage and GUI > Button setup*), for example a long press of a colour key.
- **Kodi:** map a key to `RunScript(service.camalert,door)` in a keymap, for example in
  `userdata/keymaps/camalert.xml`:

  ```xml
  <keymap><global><keyboard><f9>RunScript(service.camalert,door)</f9></keyboard>
    <remote><red mod="longpress">RunScript(service.camalert,door)</red></remote></global></keymap>
  ```
- **Android TV:** remotes have no free key for apps; use the camera list of the app or a button in Home Assistant.

On every CamAlert screen the bottom line shows which keys do what; the mosaic shows it in its title.

## Colour keys to Home Assistant

While a camera is on screen, RED, GREEN, YELLOW and BLUE on the remote send an event to Home Assistant. Example: the
doorbell rings, the camera appears, you see the parcel courier and press GREEN to open the gate.

1. Add the player with the CamAlert integration (it sets up a local webhook on the player automatically), or use
   MQTT discovery (event entity *Remote button*).
2. Import the blueprint *CamAlert - remote button does something*
   (`homeassistant/blueprints/camalert_button.yaml`), choose the players, the key, optionally the camera, and the action.

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

The *Camera control (PTZ) key* (default BLUE) is not sent for cameras that have PTZ (see
[camera control](devices.md)); choose another key or switch it off in the settings if you need BLUE in Home
Assistant. In the tour, GREEN also switches to live view. Kodi on a keyboard: F1–F4.
