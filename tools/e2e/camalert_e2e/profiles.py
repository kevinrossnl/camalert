"""Device profiles: tools/e2e/devices.local.yaml (never in git: .gitignore + tests/e2e/test_profiles.py).

Secrets are never values in the file, only the names of environment variables (`*_env`), read at run time and never
printed. A key that looks like a literal secret (token, password, ...) is refused.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_FILE = os.path.join(HERE, "devices.local.yaml")
EXAMPLE_FILE = os.path.join(HERE, "devices.example.yaml")

TYPES = ("enigma2", "kodi")
CAMERAS = ("fake", "real")
WATCHING = ("confirm", "ha")
SECRET_WORDS = re.compile(r"(token|password|passwd|secret|key)$", re.I)

COMMON = {
    "type": None, "host": None, "camalert_port": 8099, "token_env": "", "allowed_hours": "09:00-22:00",
    "quiet": False, "sleep_hours": "", "watching": "confirm", "ha_media_player": "", "ha_device_id": "",
    "ssh": "", "cameras": "real", "real_cameras": [], "timeout": 600, "scenarios": [],
}
PER_TYPE = {
    "enigma2": {"openwebif_port": 80, "openwebif_user_env": "", "openwebif_password_env": "",
                "fake_go2rtc_port": 19841, "fake_ptz_port": 19842},
    "kodi": {"jsonrpc": "tcp", "jsonrpc_port": 9090, "jsonrpc_user_env": "", "jsonrpc_password_env": ""},
}
HA_KEYS = {"url": "", "token_env": "HA_TOKEN"}
WINDOW = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


class ProfileError(Exception):
    pass


def parse_window(text):
    """'HH:MM-HH:MM' -> (start minute, end minute); may cross midnight. '' -> None."""
    text = (text or "").strip()
    if not text:
        return None
    m = WINDOW.match(text)
    if not m:
        raise ProfileError("time window must be HH:MM-HH:MM: %r" % text)
    a, b = int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4))
    if a == b:
        raise ProfileError("empty time window: %r" % text)
    return a, b


def in_window(window, minute):
    """True if the minute of the day lies inside the (start, end) window (end exclusive, may cross midnight)."""
    if window is None:
        return False
    a, b = window
    return a <= minute < b if a < b else minute >= a or minute < b


def _check_keys(where, given, allowed):
    for k in given:
        if k not in allowed:
            if SECRET_WORDS.search(k):
                raise ProfileError("%s: %r looks like a literal secret; use %s_env (an environment variable name)"
                                   % (where, k, k))
            raise ProfileError("%s: unknown key %r" % (where, k))


def device(name, raw):
    if not isinstance(raw, dict):
        raise ProfileError("device %s: must be a mapping" % name)
    kind = raw.get("type")
    if kind not in TYPES:
        raise ProfileError("device %s: type must be one of %s" % (name, ", ".join(TYPES)))
    allowed = dict(COMMON, **PER_TYPE[kind])
    _check_keys("device %s" % name, raw, allowed)
    out = dict(allowed, **raw)
    out["name"] = name
    if not out["host"]:
        raise ProfileError("device %s: host missing" % name)
    if out["cameras"] not in CAMERAS:
        raise ProfileError("device %s: cameras must be fake or real" % name)
    if out["cameras"] == "fake" and (kind != "enigma2" or not out["ssh"]):
        raise ProfileError("device %s: fake cameras need an Enigma2 receiver with ssh" % name)
    if out["watching"] not in WATCHING:
        raise ProfileError("device %s: watching must be confirm or ha" % name)
    if out["watching"] == "ha" and not out["ha_media_player"]:
        raise ProfileError("device %s: watching: ha needs ha_media_player" % name)
    if kind == "kodi" and out["jsonrpc"] not in ("tcp", "http", "ssh"):
        raise ProfileError("device %s: jsonrpc must be tcp, http or ssh" % name)
    if kind == "kodi" and out["jsonrpc"] == "ssh" and not out["ssh"]:
        raise ProfileError("device %s: jsonrpc: ssh needs ssh" % name)
    out["allowed"] = parse_window(out["allowed_hours"])
    if out["allowed"] is None:
        raise ProfileError("device %s: allowed_hours missing" % name)
    out["sleep"] = parse_window(out["sleep_hours"])
    if out["quiet"] and out["sleep"] is None:
        raise ProfileError("device %s: a quiet device needs sleep_hours" % name)
    if not isinstance(out["real_cameras"], list) or not isinstance(out["scenarios"], list):
        raise ProfileError("device %s: real_cameras and scenarios are lists" % name)
    return out


def parse(data):
    """{'devices': {name: {...}}, 'ha': {...}} -> (devices dict, ha dict)."""
    if not isinstance(data, dict):
        raise ProfileError("profile file must be a mapping")
    _check_keys("file", data, {"devices": 1, "ha": 1})
    raw = data.get("devices") or {}
    if not isinstance(raw, dict) or not raw:
        raise ProfileError("no devices")
    ha = data.get("ha") or {}
    _check_keys("ha", ha, HA_KEYS)
    return {n: device(n, d) for n, d in raw.items()}, dict(HA_KEYS, **ha)


def load(path=None):
    path = path or LOCAL_FILE
    if not os.path.exists(path):
        raise ProfileError("no profile file %s (copy devices.example.yaml to devices.local.yaml)" % path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        return parse(json.loads(text))
    try:
        import yaml
    except ImportError:
        raise ProfileError("PyYAML is needed for %s (or use a .json file)" % path)
    return parse(yaml.safe_load(text))


def secret(env_name, environ=None):
    """The value of an environment variable named in the profile ('' if not set). Never print it."""
    environ = os.environ if environ is None else environ
    return environ.get(env_name, "") if env_name else ""
