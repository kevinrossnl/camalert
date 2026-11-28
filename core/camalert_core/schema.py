# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""One settings schema for every player (#38, #7): id, section, level, type, default, range/step, unit,
label/help message ids and the platforms that have the setting.

The values here are the TARGET (UI guideline in #2). Where a player differs today (other default, step, id or
type), the tests list the difference as KNOWN with issue #39, which aligns the players. The Enigma2 settings
(`_add()` in __init__.py, the setup list) and the Kodi settings.xml / klogic.DEFAULTS are checked against this
schema by tests/enigma2/test_settings_schema.py and tests/kodi/test_settings_schema.py.

Version 2 (#39) = the target semantics on every player: chime off/high/all, skip_playing off/video/all (also on
Enigma2, replaces skip_media), trigger priority normal/high/alarm, Frigate/Foscam with own display mode, duration
(step 5) and Foscam check interval, Foscam alarms off by default, UniFi Protect events (#70, new settings with
defaults: nothing to migrate; display mode 'log' = only the event list and the log), no default go2rtc address
(#73: empty = not set, nothing is contacted; a saved address is kept), UniFi Protect rules per camera (#9, new
setting with an empty default: nothing to migrate), duration step 5, live volume step 10, HTTP port
1024-65535, certificates checked by default. migrate() turns settings saved by a version-1 player into this.

Validation is done by hand (no jsonschema on the boxes): validate(values) keeps every valid value and falls
back to the default for anything broken, like `_add()` does on Enigma2 and parse_settings() on Kodi.
Export/import and migrations (#7) build on SCHEMA_VERSION and validate().

    label  gettext msgid of the label (English, as on Enigma2); help = msgid of the help line
    kodi_label  string id of the label in the Kodi strings.po
    keys  {platform: key} where a player stores the setting under another name today (#39)
    level  basic / advanced / expert (shown to more experienced users) / internal (never shown)
"""
SCHEMA_VERSION = 2
SECTIONS = ("general", "display", "rules", "triggers", "camera_control", "home_assistant", "api", "channels", "log")
LEVELS = ("basic", "advanced", "expert", "internal")
TYPES = ("bool", "int", "choice", "text", "password", "time")
PLATFORMS = ("enigma2", "kodi", "androidtv")


class Setting(object):
    __slots__ = ("id", "section", "level", "type", "default", "min", "max", "step", "unit", "choices", "label",
                 "help", "kodi_label", "platforms", "keys", "defaults")

    def __init__(self, id, section, level, type, default, min=None, max=None, step=None, unit=None, choices=None,
                 platforms=PLATFORMS, keys=None, label=None, help=None, kodi_label=None, defaults=None):
        self.id, self.section, self.level, self.type, self.default = id, section, level, type, default
        self.min, self.max, self.step, self.unit, self.choices = min, max, step, unit, choices
        self.platforms, self.keys = tuple(platforms), dict(keys or {})
        self.label, self.help, self.kodi_label = label, help, kodi_label
        self.defaults = dict(defaults or {})  # {platform: default} where a player has another default (#67)

    def key(self, platform):
        """Name of the setting on a platform (the id, unless it still differs, see keys)."""
        return self.keys.get(platform, self.id)

    def default_for(self, platform=None):
        """The default on a platform (the schema default, unless that player has its own, see defaults)."""
        return self.defaults.get(platform, self.default)

    def __repr__(self):
        return "Setting(%r)" % self.id


S = Setting
SETTINGS = [
    S('enabled', 'general', 'basic', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Enable CamAlert', help='Turn the HTTP API and the camera display on or off.', kodi_label=30010),
    S('source', 'general', 'basic', 'choice', 'go2rtc', choices=('go2rtc', 'direct'), platforms=('enigma2', 'kodi'), label='Cameras via', help='go2rtc is recommended. Without go2rtc, list your cameras in %s', kodi_label=30012),
    S('server', 'general', 'basic', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='go2rtc address', help='Address of your go2rtc server, e.g. http://192.168.1.10:1984', kodi_label=30016),
    S('rtsp_port', 'general', 'expert', 'int', 8554, min=1, max=65535, step=1, platforms=('enigma2', 'kodi', 'androidtv'), label='go2rtc RTSP port', help='Usually 8554. Used for live view and the camera list.', kodi_label=30018),
    S('camera', 'general', 'basic', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Default camera', help='Press OK to choose from the cameras in go2rtc.', kodi_label=30024),
    S('verify_ssl', 'general', 'expert', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Check certificates', help='Turn off for a self-signed certificate (only in your own network).', kodi_label=30020),
    S('mosaic', 'general', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Mosaic cameras', help='Press OK to choose up to 9 cameras for the mosaic. Empty = all.', kodi_label=30029),
    S('titles', 'general', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Camera names', help='Press OK to give a camera its own name (empty = automatic).', kodi_label=30027),
    S('substreams', 'general', 'expert', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Live view substreams', help='For cameras the receiver cannot play (H.265/4K): front_door=front_door_sub uses that go2rtc stream for live view.', kodi_label=30257),
    S('wizard_done', 'general', 'internal', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='First-start wizard done', kodi_label=30440),
    S('language', 'general', 'advanced', 'choice', 'system', choices=('system', 'en', 'nl', 'de', 'fr', 'it', 'pl'), platforms=('enigma2', 'kodi', 'androidtv'), label='Language', help='Language of the CamAlert texts on this device. System language: the language of the device itself.', kodi_label=30727),
    S('camera_file', 'general', 'expert', 'text', '', platforms=('kodi',), label='Camera file (direct mode)', help='Empty = cameras.conf in the add-on data folder. One camera per line: name | rtsp-url | snapshot-url', kodi_label=30022),
    S('mode', 'display', 'basic', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('enigma2', 'kodi', 'androidtv'), label='Display mode', help='Photo window keeps watching TV; live switches the channel to the camera.', kodi_label=30040),
    S('duration', 'display', 'basic', 'int', 30, min=5, max=300, step=5, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Duration (seconds)', help='How long the camera stays on screen.', kodi_label=30045),
    S('position', 'display', 'basic', 'choice', 'top_right', choices=('top_right', 'top_left', 'bottom_right', 'bottom_left'), platforms=('enigma2', 'kodi', 'androidtv'), label='Window position', kodi_label=30047),
    S('size', 'display', 'basic', 'choice', 'medium', choices=('small', 'medium', 'large'), platforms=('enigma2', 'kodi', 'androidtv'), label='Window size', kodi_label=30052),
    S('live_return', 'display', 'advanced', 'bool', True, platforms=('enigma2', 'kodi'), label='Return to what was playing', help='Switch back to what you were watching when the time is up.', kodi_label=30070),
    S('video_window', 'display', 'advanced', 'choice', 'idle', choices=('off', 'idle', 'pause'), platforms=('kodi',), label='Video in the photo window', help='Smooth video instead of photos. When nothing plays: only while Kodi plays nothing. Also pause what plays: a film or live TV stops for the window and plays on from where it was afterwards.', kodi_label=30820),
    S('pause_tv', 'display', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), label='Pause what is playing meanwhile', help='Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift.', kodi_label=30068),
    S('live_volume', 'display', 'advanced', 'int', 100, min=0, max=100, step=10, unit='%', platforms=('enigma2', 'kodi', 'androidtv'), label='Volume during live view (%)', help='Percentage of the current volume while the camera is shown. 100 = unchanged.', kodi_label=30072, defaults={'androidtv': 0}),
    S('window_keys', 'display', 'advanced', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Remote control in photo window', help='OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too.', kodi_label=30066),
    S('tour_interval', 'display', 'advanced', 'int', 8, min=3, max=60, step=1, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Tour: seconds per camera', kodi_label=30078),
    S('orientation', 'display', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Turn or mirror image', help='Press OK to turn a camera that hangs upside down (needs python3-pillow).', kodi_label=30062),
    S('protect_snapshots', 'display', 'advanced', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Pictures from UniFi Protect', help='UniFi cameras get their pictures from the UniFi Protect console in the devices file: faster than go2rtc.', kodi_label=30350),
    S('ready_cameras', 'display', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Keep cameras ready', help='Only while this player is on: keeps the MJPEG stream of these cameras open so the photo window shows them at once, e.g. front_door=front_door_jpeg. Empty = off.', kodi_label=30352),
    S('refresh', 'display', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Refresh interval', help="Press OK to fetch a camera's photos less often (seconds), e.g. for a slow camera.", kodi_label=30064),
    S('strip_layout', 'display', 'advanced', 'choice', 'auto', choices=('auto', 'vertical', 'horizontal', 'grid'), platforms=('enigma2', 'kodi', 'androidtv'), label='Multi-camera window layout', help='A request with 2-4 cameras shows them together in one multi-camera window.', kodi_label=30056),
    S('title_size', 'display', 'advanced', 'choice', 'normal', choices=('small', 'normal', 'large'), platforms=('enigma2', 'kodi', 'androidtv'), label='Title size', kodi_label=30230),
    S('text_size', 'display', 'advanced', 'choice', 'normal', choices=('normal', 'large', 'xlarge'), platforms=('enigma2', 'kodi', 'androidtv'), label='Text size', help='All CamAlert texts: window titles, key hints, camera control, tour, mosaic and lists.', kodi_label=30720),
    S('priority_border', 'display', 'advanced', 'choice', 'steady', choices=('off', 'steady', 'flash'), platforms=('enigma2', 'kodi', 'androidtv'), label='Doorbell and alarm marking', help='Priority high: orange frame and the word Doorbell. Alarm: red-orange frame and the word ALARM. Flashing: once per second.', kodi_label=30723),
    S('chime', 'display', 'advanced', 'choice', 'off', choices=('off', 'high', 'all'), platforms=('enigma2', 'kodi', 'androidtv'), label='Doorbell chime', help='Plays a short ding-dong for requests with priority high or alarm (doorbell).', kodi_label=30232),
    S('picons', 'display', 'advanced', 'bool', False, platforms=('enigma2',), label='Picons for the camera channels', help='Makes a simple picon (camera + name) for every camera channel; existing picons are never replaced.'),
    S('live_format', 'display', 'expert', 'choice', 'mp4', choices=('mp4', 'hls', 'rtsp'), platforms=('kodi', 'androidtv'), label='Live stream format', help="MP4 over HTTP works with every go2rtc set-up; RTSP needs go2rtc's RTSP port; HLS is the most robust but lags a few seconds.", kodi_label=30074),
    S('skip_recording', 'rules', 'advanced', 'bool', False, platforms=('enigma2',), label='Not during a recording', help='Ignore normal requests while the receiver is recording.'),
    S('limit_hours', 'rules', 'basic', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Only between certain times', help='Ignore normal requests outside the chosen times. High and alarm always come through.', kodi_label=30090),
    S('from_time', 'rules', 'basic', 'time', '07:00', platforms=('enigma2', 'kodi', 'androidtv'), label='From', kodi_label=30092),
    S('until_time', 'rules', 'basic', 'time', '23:00', platforms=('enigma2', 'kodi', 'androidtv'), label='Until', help='May pass midnight, e.g. 07:00 to 23:00.', kodi_label=30093),
    S('alarm_wake', 'rules', 'advanced', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Wake up on alarm', help="Requests with priority 'alarm' switch the receiver (and TV via HDMI-CEC) on.", kodi_label=30100),
    S('dnd', 'rules', 'basic', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Do not disturb', help="Ignores requests with normal priority (with 'Do not disturb blocks' also high). Alarm always comes through. Also via the API, MQTT and Home Assistant.", kodi_label=30102),
    S('dnd_level', 'rules', 'advanced', 'choice', 'normal', choices=('normal', 'high'), platforms=('enigma2', 'kodi', 'androidtv'), label='Do not disturb blocks', kodi_label=30104),
    S('cooldown', 'rules', 'expert', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Cooldown per camera', help='Seconds before the same camera is shown again, e.g. *=30|garden=120 (* = all cameras). Alarm always.', kodi_label=30255),
    S('skip_playing', 'rules', 'advanced', 'choice', 'off', choices=('off', 'video', 'all'), platforms=('enigma2', 'kodi', 'androidtv'), label='Not while playing', help='Ignore normal requests while a video or recording plays (video) or while anything plays (all). High and alarm always come through.', kodi_label=30095),
    S('frigate_enabled', 'triggers', 'advanced', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Frigate events', help='Shows the camera when Frigate detects something (via MQTT, without Home Assistant).', kodi_label=30130),
    S('frigate_prefix', 'triggers', 'expert', 'text', 'frigate', platforms=('enigma2', 'kodi', 'androidtv'), label='Frigate MQTT prefix', help="Usually 'frigate'.", kodi_label=30132),
    S('frigate_labels', 'triggers', 'advanced', 'text', 'person', platforms=('enigma2', 'kodi', 'androidtv'), label='Frigate objects', help='Comma separated, e.g. person,car. Empty = all objects.', kodi_label=30259),
    S('frigate_map', 'triggers', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Frigate camera names', help='Only if the names differ from go2rtc: frigate=go2rtc|other=other_stream', kodi_label=30136),
    S('frigate_priority', 'triggers', 'advanced', 'choice', 'normal', choices=('normal', 'high', 'alarm'), platforms=('enigma2', 'kodi', 'androidtv'), label='Frigate priority', kodi_label=30260),
    S('foscam_enabled', 'triggers', 'advanced', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Foscam motion and sound alarms', help='Asks the Foscam cameras in %s for motion and sound alarms.', kodi_label=30143),
    S('foscam_priority', 'triggers', 'advanced', 'choice', 'normal', choices=('normal', 'high', 'alarm'), platforms=('enigma2', 'kodi', 'androidtv'), label='Foscam priority', kodi_label=30261),
    S('frigate_url', 'triggers', 'expert', 'text', '', platforms=('enigma2', 'kodi'), label='Frigate address (for clips)', help='Optional, e.g. http://192.168.1.10:5000 - lets you play the clip of an event from the event list.', kodi_label=30237),
    S('frigate_mode', 'triggers', 'advanced', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('enigma2', 'kodi', 'androidtv'), label='Display mode', kodi_label=30040),
    S('frigate_seconds', 'triggers', 'advanced', 'int', 30, min=5, max=300, step=5, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Duration (seconds)', kodi_label=30045),
    S('foscam_interval', 'triggers', 'expert', 'int', 2, min=1, max=60, step=1, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Check every (seconds)', kodi_label=30145),
    S('foscam_mode', 'triggers', 'advanced', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('enigma2', 'kodi', 'androidtv'), label='Display mode', kodi_label=30040),
    S('foscam_seconds', 'triggers', 'advanced', 'int', 30, min=5, max=300, step=5, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Duration (seconds)', kodi_label=30045),
    S('unifi_enabled', 'triggers', 'advanced', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='UniFi Protect events', help='Asks the UniFi Protect consoles in %s for events (doorbell, person, vehicle, ...).', kodi_label=30262),
    S('unifi_kinds', 'triggers', 'advanced', 'text', 'ring,person', platforms=('enigma2', 'kodi', 'androidtv'), label='UniFi Protect event types', help='Comma separated: ring, person, vehicle, animal, package, motion.', kodi_label=30264),
    S('unifi_cameras', 'triggers', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='UniFi Protect camera names', help='Only if the names differ from go2rtc: protect=go2rtc|other=other_stream', kodi_label=30266),
    S('unifi_priority', 'triggers', 'advanced', 'choice', 'normal', choices=('normal', 'high', 'alarm'), platforms=('enigma2', 'kodi', 'androidtv'), label='UniFi Protect priority', help='A doorbell ring always gets at least the priority High.', kodi_label=30268),
    S('unifi_mode', 'triggers', 'advanced', 'choice', 'photo', choices=('photo', 'live', 'notify', 'log'), platforms=('enigma2', 'kodi', 'androidtv'), label='Display mode', kodi_label=30040),
    S('unifi_seconds', 'triggers', 'advanced', 'int', 30, min=5, max=300, step=5, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Duration (seconds)', kodi_label=30045),
    S('unifi_interval', 'triggers', 'expert', 'int', 5, min=2, max=60, step=1, unit='s', platforms=('enigma2', 'kodi', 'androidtv'), label='Check every (seconds)', kodi_label=30145),
    S('unifi_rules', 'triggers', 'expert', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Per event type', help='Optional: type=priority/mode/camera, e.g. ring=alarm/live|motion=normal/log', kodi_label=30271),
    S('unifi_camera_rules', 'triggers', 'expert', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Per camera', help='Optional, wins over the event type: camera=priority/mode/seconds, e.g. front_door=high/photo/30|driveway=normal/log', kodi_label=30273),
    S('ptz_key', 'camera_control', 'advanced', 'choice', 'blue', choices=('blue', 'yellow', 'red', 'green', 'off'), platforms=('enigma2', 'kodi', 'androidtv'), label='Camera control (PTZ) key', help='For cameras with PTZ in %s: this key switches PTZ mode on (arrows, CH+/CH-, OK = home).', kodi_label=30239),
    S('ha_buttons', 'camera_control', 'advanced', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Colour keys to Home Assistant', help='While a camera is on screen the colour keys send an event to Home Assistant (e.g. open the gate).', kodi_label=30245),
    S('ptz_user', 'camera_control', 'advanced', 'text', '', platforms=('kodi',), label='Camera user (default)', help='Used when devices.conf has no user or password for a camera.', kodi_label=30152),
    S('ptz_password', 'camera_control', 'advanced', 'password', '', platforms=('kodi',), label='Camera password (default)', help='Used when devices.conf has no user or password for a camera.', kodi_label=30154),
    S('mqtt_enabled', 'home_assistant', 'advanced', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='MQTT (Home Assistant without YAML)', help='Connects to your MQTT broker; with discovery the receiver appears in Home Assistant automatically.', kodi_label=30110),
    S('mqtt_host', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='MQTT broker address', help='IP address or name of the MQTT broker, e.g. 192.168.1.10', kodi_label=30112),
    S('mqtt_port', 'home_assistant', 'advanced', 'int', 1883, min=1, max=65535, step=1, platforms=('enigma2', 'kodi', 'androidtv'), label='MQTT port', help='Usually 1883.', kodi_label=30114),
    S('mqtt_user', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='MQTT user', kodi_label=30116),
    S('mqtt_password', 'home_assistant', 'advanced', 'password', '', platforms=('enigma2', 'kodi', 'androidtv'), label='MQTT password', kodi_label=30117),
    S('mqtt_discovery', 'home_assistant', 'advanced', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Home Assistant discovery', help='Creates a device with a button per camera in Home Assistant.', kodi_label=30118),
    S('mqtt_name', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Name in Home Assistant', help="Empty = CamAlert + the receiver's host name.", kodi_label=30120),
    S('ha_webhook', 'home_assistant', 'internal', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Home Assistant webhook', kodi_label=30253),
    S('ha_webhook_secret', 'home_assistant', 'internal', 'password', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Colour keys: signing secret (Home Assistant)', kodi_label=30880),
    S('api_https', 'api', 'expert', 'bool', False, platforms=('enigma2', 'kodi', 'androidtv'), label='Use HTTPS for the API', help='Uses a self-signed certificate; callers must turn off certificate checking.', kodi_label=30168),
    S('http_port', 'api', 'expert', 'int', 8099, min=1024, max=65535, step=1, platforms=('enigma2', 'kodi', 'androidtv'), label='HTTP port', help='Port of the CamAlert API on this receiver (default 8099).', kodi_label=30160),
    S('allow', 'api', 'advanced', 'choice', 'lan', choices=('lan', 'any'), platforms=('enigma2', 'kodi', 'androidtv'), label='Allowed callers', help="'Local network only' is recommended.", kodi_label=30162),
    S('token', 'api', 'advanced', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Access token (optional)', help='If set, callers must send it in the X-CamAlert-Token header; ?token=... in the address still works but is deprecated.', kodi_label=30166),
    S('bouquet_name', 'channels', 'advanced', 'text', 'Cameras', platforms=('enigma2',), label='Camera list name', help='Name of the channel list created with the yellow button.'),
    S('auto_bouquet', 'channels', 'advanced', 'bool', True, platforms=('enigma2',), label='Update camera list automatically', help='Checks every 30 minutes for new or removed cameras and updates the channel list.'),
    S('bouquet_position', 'channels', 'expert', 'choice', 'keep', choices=('keep', 'bottom', 'top'), platforms=('enigma2',), label='Camera list position', help='Where the camera list appears among your channel lists.'),
    S('log_level', 'log', 'advanced', 'choice', 'normal', choices=('off', 'errors', 'normal', 'verbose'), platforms=('enigma2', 'kodi', 'androidtv'), label='Log level', help='camalert.log in /home/root/logs (or /tmp). Passwords and tokens are never logged.', kodi_label=30247),
    S('log_syslog', 'log', 'expert', 'text', '', platforms=('enigma2', 'kodi', 'androidtv'), label='Remote syslog (host:port)', help='Optional: also send the log via UDP (RFC 5424), e.g. to Loki/Alloy.', kodi_label=30251),
    S('event_folder', 'log', 'expert', 'text', '/tmp/camalert_events', platforms=('enigma2',), label='Event snapshots folder', help='Small photos of the last 20 events (default /tmp/camalert_events).'),
    S('allow_update', 'log', 'advanced', 'bool', True, platforms=('enigma2', 'kodi', 'androidtv'), label='Allow updates from Home Assistant', help='Home Assistant can install a new CamAlert release on this player (only the official release, only a newer version, checked with its checksum).', kodi_label=30800),
    S('update_check', 'log', 'advanced', 'bool', True, platforms=('enigma2',), label='Check for updates', help='Looks once a day on GitHub for a new version and shows a message.'),
    S('update_checked', 'log', 'internal', 'text', '0', platforms=('enigma2',), label=None),
    S('update_seen', 'log', 'internal', 'text', '', platforms=('enigma2',), label=None),
]
BY_ID = {s.id: s for s in SETTINGS}

# Why a player lacks a setting that the others have, or has its own default (#67; listed on the Android TV page
# and exported for the Android TV player). Every Kodi setting that Android TV lacks needs a reason here.
MISSING = {
    "androidtv": {
        "source": "go2rtc only for now (direct mode with a camera file: follow-up, #124)",
        "camera_file": "go2rtc only for now (#124)",
        "pause_tv": "Android cannot pause another app",
        "live_return": "live view is an overlay: what was playing keeps playing underneath",
        "video_window": "the photo window is an overlay over the other app; video in it: follow-up (#129 is Kodi)",
        "frigate_url": "no clip playback from the event list yet (#124)",
        "ptz_user": "the default camera login is kept with the camera devices, never with the settings (#66)",
        "ptz_password": "the default camera login is kept with the camera devices, never with the settings (#66)",
    },
}
DEFAULT_REASONS = {
    "androidtv": {
        "live_volume": "live view is an overlay: the app underneath keeps playing its own sound, so the camera is "
                       "muted unless the user turns it up (#64)",
    },
}


def for_platform(platform):
    """Settings of one platform, in schema order."""
    return [s for s in SETTINGS if platform in s.platforms]


def defaults(platform):
    """{platform key: default} of one platform."""
    return {s.key(platform): s.default_for(platform) for s in for_platform(platform)}


def _time(value):
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(text)
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return "%02d:%02d" % (h, m)


def coerce(setting, value):
    """The value as the setting's type, or ValueError."""
    t = setting.type
    if t == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off", ""):
            return False
        raise ValueError(value)
    if t == "int":
        n = int(float(str(value).strip()))
        if (setting.min is not None and n < setting.min) or (setting.max is not None and n > setting.max):
            raise ValueError(value)
        return n
    if t == "choice":
        v = str(value).strip()
        if v not in setting.choices:
            raise ValueError(value)
        return v
    if t == "time":
        return _time(value)
    return str(value) if t == "password" else str(value).strip()


def validate(values, platform=None):
    """(clean values, problems): every known setting with a valid value; broken or missing ones get the default.
    values use the schema ids, or the platform keys when platform is given. Unknown keys are dropped."""
    settings = for_platform(platform) if platform else SETTINGS
    clean, problems = {}, []
    for s in settings:
        k = s.key(platform) if platform else s.id
        if k not in values:
            clean[k] = s.default_for(platform)
            continue
        try:
            clean[k] = coerce(s, values[k])
        except (TypeError, ValueError):
            clean[k] = s.default_for(platform)
            problems.append(k)
    return clean, problems


# Saved settings of a version-1 player -> schema ids (#39). Kept after the players are aligned, so old settings
# files still load.
RENAMED_V1 = {
    "enigma2": {"foscam_poll": "foscam_enabled", "device_priority": "foscam_priority"},
    "kodi": {"live_resume": "live_return", "refresh_map": "refresh"},
}
_TRUE = ("true", "1", "yes", "on")


def migrate(values, platform):
    """Settings as a player saved them (its own keys, version-1 meanings) -> {schema id: value} with version-2
    meanings; run validate() on the result. Renamed keys move (the new key wins if both are there), the
    Enigma2 yes/no chime becomes 'high' / 'off' (it rang for high and alarm), skip_media = yes becomes
    skip_playing = 'video'. Unknown keys stay (validate() drops them)."""
    out = dict(values)
    for old, new in RENAMED_V1.get(platform, {}).items():
        if old in out:
            value = out.pop(old)
            out.setdefault(new, value)
    chime = out.get("chime")
    if isinstance(chime, bool) or str(chime).strip().lower() in _TRUE + ("false", "0", "no", ""):
        out["chime"] = "high" if chime is True or str(chime).strip().lower() in _TRUE else "off"
    if "skip_media" in out:
        media = out.pop("skip_media")
        if "skip_playing" not in out:
            out["skip_playing"] = "video" if media is True or str(media).strip().lower() in _TRUE else "off"
    return out
