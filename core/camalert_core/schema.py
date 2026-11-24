# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""One settings schema for every player (#38, #7): id, section, level, type, default, range/step, unit,
label/help message ids and the platforms that have the setting.

The values here are the TARGET (UI guideline in #2). Where a player differs today (other default, step, id or
type), the tests list the difference as KNOWN with issue #39, which aligns the players. The Enigma2 settings
(`_add()` in __init__.py, the setup list) and the Kodi settings.xml / klogic.DEFAULTS are checked against this
schema by tests/enigma2/test_settings_schema.py and tests/kodi/test_settings_schema.py.

Validation is done by hand (no jsonschema on the boxes): validate(values) keeps every valid value and falls
back to the default for anything broken, like `_add()` does on Enigma2 and parse_settings() on Kodi.
Export/import and migrations (#7) build on SCHEMA_VERSION and validate().

    label  gettext msgid of the label (English, as on Enigma2); help = msgid of the help line
    kodi_label  string id of the label in the Kodi strings.po
    keys  {platform: key} where a player stores the setting under another name today (#39)
    level  basic / advanced / expert (shown to more experienced users) / internal (never shown)
"""
SCHEMA_VERSION = 1
SECTIONS = ("general", "display", "rules", "triggers", "camera_control", "home_assistant", "api", "channels", "log")
LEVELS = ("basic", "advanced", "expert", "internal")
TYPES = ("bool", "int", "choice", "text", "password", "time")
PLATFORMS = ("enigma2", "kodi")


class Setting(object):
    __slots__ = ("id", "section", "level", "type", "default", "min", "max", "step", "unit", "choices", "label",
                 "help", "kodi_label", "platforms", "keys")

    def __init__(self, id, section, level, type, default, min=None, max=None, step=None, unit=None, choices=None,
                 platforms=PLATFORMS, keys=None, label=None, help=None, kodi_label=None):
        self.id, self.section, self.level, self.type, self.default = id, section, level, type, default
        self.min, self.max, self.step, self.unit, self.choices = min, max, step, unit, choices
        self.platforms, self.keys = tuple(platforms), dict(keys or {})
        self.label, self.help, self.kodi_label = label, help, kodi_label

    def key(self, platform):
        """Name of the setting on a platform (the id, unless it still differs, see keys)."""
        return self.keys.get(platform, self.id)

    def __repr__(self):
        return "Setting(%r)" % self.id


S = Setting
SETTINGS = [
    S('enabled', 'general', 'basic', 'bool', True, platforms=('enigma2', 'kodi'), label='Enable CamAlert', help='Turn the HTTP API and the camera display on or off.', kodi_label=30010),
    S('source', 'general', 'basic', 'choice', 'go2rtc', choices=('go2rtc', 'direct'), platforms=('enigma2', 'kodi'), label='Cameras via', help='go2rtc is recommended. Without go2rtc, list your cameras in %s', kodi_label=30012),
    S('server', 'general', 'basic', 'text', 'http://192.168.1.10:1984', platforms=('enigma2', 'kodi'), label='go2rtc address', help='Address of your go2rtc server, e.g. http://192.168.1.10:1984', kodi_label=30016),
    S('rtsp_port', 'general', 'expert', 'int', 8554, min=1, max=65535, step=1, platforms=('enigma2', 'kodi'), label='go2rtc RTSP port', help='Usually 8554. Used for live view and the camera list.', kodi_label=30018),
    S('camera', 'general', 'basic', 'text', '', platforms=('enigma2', 'kodi'), label='Default camera', help='Press OK to choose from the cameras in go2rtc.', kodi_label=30024),
    S('verify_ssl', 'general', 'expert', 'bool', True, platforms=('enigma2', 'kodi'), label='Check certificates', help='Turn off for a self-signed certificate (only in your own network).', kodi_label=30020),
    S('mosaic', 'general', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Mosaic cameras', help='Press OK to choose up to 9 cameras for the mosaic. Empty = all.', kodi_label=30029),
    S('titles', 'general', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Camera names', help='Press OK to give a camera its own name (empty = automatic).', kodi_label=30027),
    S('substreams', 'general', 'expert', 'text', '', platforms=('enigma2', 'kodi'), label='Live view substreams', help='For cameras the receiver cannot play (H.265/4K): front_door=front_door_sub uses that go2rtc stream for live view.', kodi_label=30257),
    S('camera_file', 'general', 'expert', 'text', '', platforms=('kodi',), label='Camera file (direct mode)', help='Empty = cameras.conf in the add-on data folder. One camera per line: name | rtsp-url | snapshot-url', kodi_label=30022),
    S('mode', 'display', 'basic', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('enigma2', 'kodi'), label='Display mode', help='Photo window keeps watching TV; live switches the channel to the camera.', kodi_label=30040),
    S('duration', 'display', 'basic', 'int', 30, min=5, max=300, step=5, unit='s', platforms=('enigma2', 'kodi'), label='Duration (seconds)', help='How long the camera stays on screen.', kodi_label=30045),
    S('position', 'display', 'basic', 'choice', 'top_right', choices=('top_right', 'top_left', 'bottom_right', 'bottom_left'), platforms=('enigma2', 'kodi'), label='Window position', kodi_label=30047),
    S('size', 'display', 'basic', 'choice', 'medium', choices=('small', 'medium', 'large'), platforms=('enigma2', 'kodi'), label='Window size', kodi_label=30052),
    S('live_return', 'display', 'advanced', 'bool', True, platforms=('enigma2', 'kodi'), keys={'kodi': 'live_resume'}, label='Return to previous channel', help='Switch back to what you were watching when the time is up.', kodi_label=30070),
    S('pause_tv', 'display', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), label='Pause TV meanwhile', help='Pauses the channel (timeshift) while the camera is shown. Needs a hard disk or USB stick for timeshift.', kodi_label=30068),
    S('live_volume', 'display', 'advanced', 'int', 100, min=0, max=100, step=10, unit='%', platforms=('enigma2', 'kodi'), label='Volume during live view (%)', help='Percentage of the current volume while the camera is shown. 100 = unchanged.', kodi_label=30072),
    S('window_keys', 'display', 'advanced', 'bool', True, platforms=('enigma2', 'kodi'), label='Remote control in photo window', help='OK = live, LEFT/RIGHT = other camera, EXIT = close. Any other key closes it too.', kodi_label=30066),
    S('tour_interval', 'display', 'advanced', 'int', 8, min=3, max=60, step=1, unit='s', platforms=('enigma2', 'kodi'), label='Tour: seconds per camera', kodi_label=30078),
    S('orientation', 'display', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Turn or mirror image', help='Press OK to turn a camera that hangs upside down (needs python3-pillow).', kodi_label=30062),
    S('refresh', 'display', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), keys={'kodi': 'refresh_map'}, label='Refresh interval', help="Press OK to fetch a camera's photos less often (seconds), e.g. for a slow camera.", kodi_label=30064),
    S('strip_layout', 'display', 'advanced', 'choice', 'auto', choices=('auto', 'vertical', 'horizontal', 'grid'), platforms=('enigma2', 'kodi'), label='Multi-camera window layout', help='A request with 2-4 cameras shows them together in one multi-camera window.', kodi_label=30056),
    S('title_size', 'display', 'advanced', 'choice', 'normal', choices=('small', 'normal', 'large'), platforms=('enigma2', 'kodi'), label='Title size', kodi_label=30230),
    S('chime', 'display', 'advanced', 'choice', 'off', choices=('off', 'high', 'all'), platforms=('enigma2', 'kodi'), label='Doorbell chime', help='Plays a short ding-dong for requests with priority high or alarm (doorbell).', kodi_label=30232),
    S('picons', 'display', 'advanced', 'bool', False, platforms=('enigma2',), label='Picons for the camera channels', help='Makes a simple picon (camera + name) for every camera channel; existing picons are never replaced.'),
    S('live_format', 'display', 'expert', 'choice', 'mp4', choices=('mp4', 'hls', 'rtsp'), platforms=('kodi',), label='Live stream format', help="MP4 over HTTP works with every go2rtc set-up; RTSP needs go2rtc's RTSP port; HLS is the most robust but lags a few seconds.", kodi_label=30074),
    S('skip_recording', 'rules', 'advanced', 'bool', False, platforms=('enigma2',), label='Not during a recording', help='Ignore requests while the receiver is recording.'),
    S('limit_hours', 'rules', 'basic', 'bool', False, platforms=('enigma2', 'kodi'), label='Only between certain times', help='Ignore requests outside the chosen times.', kodi_label=30090),
    S('from_time', 'rules', 'basic', 'time', '07:00', platforms=('enigma2', 'kodi'), label='From', kodi_label=30092),
    S('until_time', 'rules', 'basic', 'time', '23:00', platforms=('enigma2', 'kodi'), label='Until', help='May pass midnight, e.g. 07:00 to 23:00.', kodi_label=30093),
    S('alarm_wake', 'rules', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), label='Wake receiver on alarm', help="Requests with priority 'alarm' switch the receiver (and TV via HDMI-CEC) on.", kodi_label=30100),
    S('dnd', 'rules', 'basic', 'bool', False, platforms=('enigma2', 'kodi'), label='Do not disturb', help='Blocks requests with normal priority. Also via the API, MQTT and Home Assistant.', kodi_label=30102),
    S('dnd_level', 'rules', 'advanced', 'choice', 'normal', choices=('normal', 'high'), platforms=('enigma2', 'kodi'), label='Do not disturb blocks', kodi_label=30104),
    S('skip_media', 'rules', 'advanced', 'bool', False, platforms=('enigma2',), label='Not while playing a recording or video', help='Ignore normal requests while you watch a recording or a video file.'),
    S('cooldown', 'rules', 'expert', 'text', '', platforms=('enigma2', 'kodi'), label='Cooldown per camera', help='Seconds before the same camera is shown again, e.g. *=30|garden=120 (* = all cameras). Alarm always.', kodi_label=30255),
    S('skip_playing', 'rules', 'advanced', 'choice', 'off', choices=('off', 'video', 'all'), platforms=('kodi',), label='Not while playing', help='Normal-priority requests are ignored while you watch this. High and alarm always pass.', kodi_label=30095),
    S('frigate_enabled', 'triggers', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), label='Frigate events', help='Shows the camera when Frigate detects something (via MQTT, without Home Assistant).', kodi_label=30130),
    S('frigate_prefix', 'triggers', 'expert', 'text', 'frigate', platforms=('enigma2', 'kodi'), label='Frigate MQTT prefix', help="Usually 'frigate'.", kodi_label=30132),
    S('frigate_labels', 'triggers', 'advanced', 'text', 'person', platforms=('enigma2', 'kodi'), label='Frigate objects', help='Comma separated, e.g. person,car. Empty = all objects.', kodi_label=30134),
    S('frigate_map', 'triggers', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Frigate camera names', help='Only if the names differ from go2rtc: frigate=go2rtc|other=other_stream', kodi_label=30136),
    S('frigate_priority', 'triggers', 'advanced', 'choice', 'normal', choices=('normal', 'high', 'alarm'), platforms=('enigma2', 'kodi'), label='Frigate priority', kodi_label=30139),
    S('foscam_enabled', 'triggers', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), keys={'enigma2': 'foscam_poll'}, label='Foscam motion alarms', help='Asks Foscam cameras from %s every 2 seconds for a motion or sound alarm.', kodi_label=30143),
    S('foscam_priority', 'triggers', 'advanced', 'choice', 'normal', choices=('normal', 'high', 'alarm'), platforms=('enigma2', 'kodi'), keys={'enigma2': 'device_priority'}, label='Foscam priority', kodi_label=30139),
    S('frigate_url', 'triggers', 'expert', 'text', '', platforms=('enigma2', 'kodi'), label='Frigate address (for clips)', help='Optional, e.g. http://192.168.1.10:5000 - lets you play the clip of an event from the event list.', kodi_label=30237),
    S('frigate_mode', 'triggers', 'advanced', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('kodi',), label='Display mode', kodi_label=30040),
    S('frigate_seconds', 'triggers', 'advanced', 'int', 30, min=5, max=300, step=1, unit='s', platforms=('kodi',), label='Duration (seconds)', kodi_label=30045),
    S('foscam_interval', 'triggers', 'expert', 'int', 2, min=1, max=60, step=1, unit='s', platforms=('kodi',), label='Check every (seconds)', kodi_label=30145),
    S('foscam_mode', 'triggers', 'advanced', 'choice', 'photo', choices=('photo', 'live', 'notify'), platforms=('kodi',), label='Display mode', kodi_label=30040),
    S('foscam_seconds', 'triggers', 'advanced', 'int', 30, min=5, max=300, step=1, unit='s', platforms=('kodi',), label='Duration (seconds)', kodi_label=30045),
    S('ptz_key', 'camera_control', 'advanced', 'choice', 'blue', choices=('blue', 'yellow', 'red', 'green', 'off'), platforms=('enigma2', 'kodi'), label='PTZ key', help='For cameras with PTZ in %s: this key switches PTZ mode on (arrows, CH+/CH-, OK = home).', kodi_label=30239),
    S('ha_buttons', 'camera_control', 'advanced', 'bool', True, platforms=('enigma2', 'kodi'), label='Colour keys to Home Assistant', help='While a camera is on screen the colour keys send an event to Home Assistant (e.g. open the gate).', kodi_label=30245),
    S('ptz_user', 'camera_control', 'advanced', 'text', '', platforms=('kodi',), label='Camera user (default)', help='Used when devices.conf has no user or password for a camera.', kodi_label=30152),
    S('ptz_password', 'camera_control', 'advanced', 'password', '', platforms=('kodi',), label='Camera password (default)', help='Used when devices.conf has no user or password for a camera.', kodi_label=30154),
    S('mqtt_enabled', 'home_assistant', 'advanced', 'bool', False, platforms=('enigma2', 'kodi'), label='MQTT (Home Assistant without YAML)', help='Connects to your MQTT broker; with discovery the receiver appears in Home Assistant automatically.', kodi_label=30110),
    S('mqtt_host', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='MQTT broker address', help='IP address or name of the MQTT broker, e.g. 192.168.1.10', kodi_label=30112),
    S('mqtt_port', 'home_assistant', 'advanced', 'int', 1883, min=1, max=65535, step=1, platforms=('enigma2', 'kodi'), label='MQTT port', help='Usually 1883.', kodi_label=30114),
    S('mqtt_user', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='MQTT user', kodi_label=30116),
    S('mqtt_password', 'home_assistant', 'advanced', 'password', '', platforms=('enigma2', 'kodi'), label='MQTT password', kodi_label=30117),
    S('mqtt_discovery', 'home_assistant', 'advanced', 'bool', True, platforms=('enigma2', 'kodi'), label='Home Assistant discovery', help='Creates a device with a button per camera in Home Assistant.', kodi_label=30118),
    S('mqtt_name', 'home_assistant', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Name in Home Assistant', help="Empty = CamAlert + the receiver's host name.", kodi_label=30120),
    S('ha_webhook', 'home_assistant', 'internal', 'text', '', platforms=('enigma2', 'kodi'), label='Home Assistant webhook', kodi_label=30253),
    S('api_https', 'api', 'expert', 'bool', False, platforms=('enigma2', 'kodi'), label='Use HTTPS for the API', help='Uses a self-signed certificate; callers must turn off certificate checking.', kodi_label=30168),
    S('http_port', 'api', 'expert', 'int', 8099, min=1024, max=65535, step=1, platforms=('enigma2', 'kodi'), label='HTTP port', help='Port of the CamAlert API on this receiver (default 8099).', kodi_label=30160),
    S('allow', 'api', 'advanced', 'choice', 'lan', choices=('lan', 'any'), platforms=('enigma2', 'kodi'), label='Allowed callers', help="'Local network only' is recommended.", kodi_label=30162),
    S('token', 'api', 'advanced', 'text', '', platforms=('enigma2', 'kodi'), label='Access token (optional)', help='If set, callers must add ?token=... to every request.', kodi_label=30166),
    S('bouquet_name', 'channels', 'advanced', 'text', 'Cameras', platforms=('enigma2',), label='Camera list name', help='Name of the channel list created with the yellow button.'),
    S('auto_bouquet', 'channels', 'advanced', 'bool', True, platforms=('enigma2',), label='Update camera list automatically', help='Checks every 30 minutes for new or removed cameras and updates the channel list.'),
    S('bouquet_position', 'channels', 'expert', 'choice', 'keep', choices=('keep', 'bottom', 'top'), platforms=('enigma2',), label='Camera list position', help='Where the camera list appears among your channel lists.'),
    S('log_level', 'log', 'advanced', 'choice', 'normal', choices=('off', 'errors', 'normal', 'verbose'), platforms=('enigma2', 'kodi'), label='Log level', help='camalert.log in /home/root/logs (or /tmp). Passwords and tokens are never logged.', kodi_label=30247),
    S('log_syslog', 'log', 'expert', 'text', '', platforms=('enigma2', 'kodi'), label='Remote syslog (host:port)', help='Optional: also send the log via UDP (RFC 5424), e.g. to Loki/Alloy.', kodi_label=30251),
    S('event_folder', 'log', 'expert', 'text', '/tmp/camalert_events', platforms=('enigma2',), label='Event snapshots folder', help='Small photos of the last 20 events (default /tmp/camalert_events).'),
    S('update_check', 'log', 'advanced', 'bool', True, platforms=('enigma2',), label='Check for updates', help='Looks once a day on GitHub for a new version and shows a message.'),
    S('update_checked', 'log', 'internal', 'text', '0', platforms=('enigma2',), label=None),
    S('update_seen', 'log', 'internal', 'text', '', platforms=('enigma2',), label=None),
]
BY_ID = {s.id: s for s in SETTINGS}


def for_platform(platform):
    """Settings of one platform, in schema order."""
    return [s for s in SETTINGS if platform in s.platforms]


def defaults(platform):
    """{platform key: default} of one platform."""
    return {s.key(platform): s.default for s in for_platform(platform)}


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
            clean[k] = s.default
            continue
        try:
            clean[k] = coerce(s, values[k])
        except (TypeError, ValueError):
            clean[k] = s.default
            problems.append(k)
    return clean, problems
