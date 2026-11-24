# CamAlert blueprints – inputs (frozen for 1.x)

Since v1.0.0 the input **keys, their order and their defaults** are part of the CamAlert API (#45): automations
made from a blueprint keep working after an update within a major version. A new input may only be added (optional,
with a default) after the existing ones of its group; a key is never renamed or removed before 2.0.
`tests/test_blueprints.py` (`FROZEN`) fails on any change.

Order in every blueprint: **trigger → `players` → `camera`/`cameras` → `mode` → `seconds` → `label` → conditions
(`when`, `alarm_panel`, `from_time`, `until_time`) → `action`**.

| Key | Meaning | Default | Blueprints |
|---|---|---|---|
| `doorbell` / `motion` / `alarm_panel` / `button` | What starts the automation (trigger) | – (button: `green`) | doorbell / motion / alarm / button |
| `players` | Players (Enigma2 receivers and/or Kodi) as devices of the CamAlert integration | – | all |
| `camera` | One camera name as in go2rtc (alarm: also a live mosaic stream) | – (button: empty = any camera) | doorbell, alarm, button |
| `cameras` | Comma-separated camera names; empty = camera named after the sensor | empty | motion |
| `mode` | Display mode: `photo` (Photo window), `live` (Live view), `notify` (Notification) | `photo` (alarm: `live`) | doorbell, motion, alarm |
| `several` | 2+ cameras: `strip` (Multi-camera window, 2–4 cameras) or `mosaic` (full screen) | `strip` | motion |
| `seconds` | Duration, 5–300 s | `30` (alarm: `300`) | doorbell, motion, alarm |
| `label` | Who/what before the camera name in the title; empty = none (motion: Person / Motion) | empty (alarm: `Alarm`) | doorbell, motion, alarm |
| `when` | `armed`, `time`, `armed_or_time`, `armed_and_time`, `always` | `armed` | motion |
| `alarm_panel` | Alarm panel (motion: condition, optional) | – (motion: empty) | motion, alarm (trigger) |
| `from_time` / `until_time` | Time window | `22:00:00` / `07:00:00` | motion |
| `action` | What a colour key does | – | button |

Priorities are fixed per blueprint: doorbell and motion `high`, alarm `alarm`.
Blueprints cannot be translated: option labels use the English glossary terms (`core/i18n/glossary.json`).

**Changed before 1.0.0** (re-save automations made from an older copy): `receivers` → `players`,
doorbell `triggers_in` → `doorbell`; new `label` (doorbell, motion, alarm) and `mode` (alarm).
