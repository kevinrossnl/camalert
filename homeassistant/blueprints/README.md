# CamAlert blueprints – inputs (frozen for 1.x)

Since v1.0.0 the input **keys, their order and their defaults** are part of the CamAlert API (#45): automations
made from a blueprint keep working after an update within a major version. A new input may only be added (optional,
with a default) after the existing ones of its group; a key is never renamed or removed before 2.0.
`tests/test_blueprints.py` (`FROZEN`) fails on any change.

Order in every blueprint: **trigger → `players` → `camera`/`cameras` → `mode` → `seconds` → `label` → conditions
(`when`, `alarm_panel`, `from_time`, `until_time`) → `action` → other screens (`webos_notify`, `message`,
`snapshot_camera`, `snapshot_file`, `tv`, `snapshot_url`)**.

| Key | Meaning | Default | Blueprints |
|---|---|---|---|
| `doorbell` / `motion` / `alarm_panel` / `button` | What starts the automation (trigger) | – (button: `green`) | doorbell (+ webOS) / motion / alarm / button |
| `players` | Players (Enigma2 receivers and/or Kodi) as devices of the CamAlert integration | – | all |
| `camera` | One camera name as in go2rtc (alarm: also a live mosaic stream) | – (button: empty = any camera) | doorbell, doorbell webOS, alarm, button |
| `cameras` | Comma-separated camera names; empty = camera named after the sensor | empty | motion |
| `mode` | Display mode: `photo` (Photo window), `live` (Live view), `notify` (Notification) | `photo` (alarm: `live`) | doorbell, doorbell webOS, motion, alarm |
| `several` | 2+ cameras: `strip` (Multi-camera window, 2–4 cameras) or `mosaic` (full screen) | `strip` | motion |
| `seconds` | Duration, 5–300 s | `30` (alarm: `300`) | doorbell, doorbell webOS, motion, alarm |
| `label` | Who/what before the camera name in the title; empty = none (motion: Person / Motion) | empty (alarm: `Alarm`) | doorbell, doorbell webOS, motion, alarm |
| `when` | `armed`, `time`, `armed_or_time`, `armed_and_time`, `always` | `armed` | motion |
| `alarm_panel` | Alarm panel (motion: condition, optional) | – (motion: empty) | motion, alarm (trigger) |
| `from_time` / `until_time` | Time window | `22:00:00` / `07:00:00` | motion |
| `action` | What a colour key does | – | button |
| `webos_notify` | Notify action of the LG TV (LG webOS TV integration), e.g. `notify.lg_webos_tv_living_room`; `notify.` may be left out | – | doorbell webOS |
| `message` | Text of the LG TV notification; empty = who/what (or `Doorbell`) and the camera name | empty | doorbell webOS |
| `snapshot_camera` | Camera entity for the picture in the LG TV notification; empty = text only. The TV refuses pictures over 100 KB (then nothing is shown, #74): prefer `snapshot_url` | empty | doorbell webOS |
| `snapshot_file` | Where that snapshot is saved (an allowed folder, never `www`: public without login) | `/media/camalert_webos.jpg` | doorbell webOS |
| `tv` | The LG TV's media player: notify only while it is on; empty = always try | empty | doorbell webOS |
| `snapshot_url` | Small picture for the LG TV notification (#74), e.g. `http://192.168.1.10:1984/api/frame.jpeg?src=front_door&width=640`; downloaded with the Downloader integration (download folder = folder of `snapshot_file`), used instead of `snapshot_camera`; download failed or no answer within 15 s = text only | empty | doorbell webOS |

**Added in 1.2** (optional, at the end, the default changes nothing):

| Key | Meaning | Default | Blueprints |
|---|---|---|---|
| `presence` | Only when someone is home: persons, device trackers or groups (state `home`) or zones (someone in it, e.g. `zone.home`); empty = always. Only the TV part waits for it (players, LG TV) | empty | doorbell, doorbell webOS, motion |
| `phone_notify` | Notify action of the Companion app, e.g. `notify.mobile_app_my_phone` (`notify.` may be left out): "Doorbell - camera" on the phone, also when nobody is home; empty = none | empty | doorbell, doorbell webOS |
| `phone_camera` | Camera entity for that notification: its picture (`/api/camera_proxy/...`) and tapping opens the camera; empty = text only | empty | doorbell, doorbell webOS |
| `webos_live_url` | Live view on the LG TV: page with the stream that the TV opens in its browser for the duration (e.g. go2rtc `http://192.168.1.10:1984/stream.html?src=front_door&mode=mse`); needs `tv`; afterwards the TV goes back to its input or app (scene `scene.camalert_webos_before`); empty = only the notification | empty | doorbell webOS |

**Doorbell on the players and other screens** (`camalert_doorbell_screens.yaml`, new in 1.2; same frozen rules):
`doorbell`, `players`, `camera`, `mode`, `seconds`, `label` as in the doorbell blueprint, then

| Key | Meaning | Default |
|---|---|---|
| `cast_players` | Chromecast / Google TV media players: live view full screen with `camera.play_stream`, stopped after the duration (the Chromecast then shows its home screen, not the app from before) | empty |
| `cast_camera` | Camera entity that can stream; needed for `cast_players` | empty |
| `androidtv_notify` | Notify action of the "Notifications for Android TV / Fire TV" integration (`notify.` may be left out): a small window with the text for the duration | empty |
| `androidtv_snapshot_url` | Picture the Android TV downloads itself (small go2rtc frame, as `snapshot_url`); empty = text only | empty |
| `presence` | As above (here the whole automation waits for it: all its screens are TVs) | empty |

Samsung Tizen has no overlay for apps of others and no notify with a picture in Home Assistant: use the Chromecast
input when the TV has Chromecast built in, or the LG/Android TV routes (#100).

Priorities are fixed per blueprint: doorbell (also webOS) and motion `high`, alarm `alarm`.
Blueprints cannot be translated: option labels use the English glossary terms (`core/i18n/glossary.json`).

**Changed before 1.0.0** (re-save automations made from an older copy): `receivers` → `players`,
doorbell `triggers_in` → `doorbell`; new `label` (doorbell, motion, alarm) and `mode` (alarm).
