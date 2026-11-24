# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Pure helper functions without Enigma2 dependencies, so they can be unit tested."""
import ipaddress
import json
import re
from urllib.parse import quote, unquote, urlsplit

MODES = ("photo", "live", "notify")
POSITIONS = ("top_right", "top_left", "bottom_right", "bottom_left")
SIZES = {"small": (480, 270), "medium": (640, 360), "large": (960, 540)}
MIN_SECONDS, MAX_SECONDS = 5, 300
SERVICE_TYPE = 4097  # GStreamer media player
BOUQUET_FILE = "userbouquet.camalert.tv"


def slug(name):
    """'Front Door' -> 'front_door' (also handles umlauts)."""
    n = (name or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("é", "e"), ("è", "e"), ("à", "a")):
        n = n.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "_", n).strip("_")


def display_name(stream):
    """'front_door' -> 'Front door'."""
    s = (stream or "").replace("_", " ").replace("-", " ").strip()
    return s[:1].upper() + s[1:]


def normalize_server(url):
    """Accepts '192.168.1.10', '192.168.1.10:1984' or 'http://host:1984/'; returns 'http://host:port' or None."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return None
    if "://" not in u:
        u = "http://" + u
    p = urlsplit(u)
    if p.scheme not in ("http", "https") or not p.hostname:
        return None
    port = p.port or (443 if p.scheme == "https" else 1984)
    host = "[%s]" % p.hostname if ":" in p.hostname else p.hostname
    return "%s://%s:%d" % (p.scheme, host, port)


def server_host(server):
    p = urlsplit(server or "")
    return p.hostname


def streams_from_json(text):
    """Stream names from the go2rtc /api/streams answer, sorted."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    return sorted(k for k in data.keys() if re.match(r"^[A-Za-z0-9_.-]+$", k))


def rtsp_url(server, stream, port=8554):
    """RTSP over TCP (rtspt://) towards go2rtc. Plain HTTP-TS gives a black picture on many boxes."""
    host = server_host(server)
    if not host or not stream:
        return None
    if ":" in host:
        host = "[%s]" % host
    return "rtspt://%s:%d/%s" % (host, int(port), quote(stream, safe="_.-"))


def snapshot_url(server, stream, width=640):
    if not server or not stream:
        return None
    return "%s/api/frame.jpeg?src=%s&width=%d" % (server, quote(stream, safe="_.-"), int(width))


def service_ref(url, name, number=1):
    """Enigma2 service reference for a stream URL (':' must be encoded as %3a)."""
    return "%d:0:1:DC%02X:0:0:0:0:0:0:%s:%s" % (SERVICE_TYPE, number % 256, url.replace(":", "%3a"), name.replace(":", " "))


def url_from_ref(ref):
    parts = (ref or "").split(":")
    if len(parts) < 12:
        return None
    return unquote(":".join(parts[10:-1]))


def stream_from_ref(ref, cameras=None):
    """Camera name from a service reference, or None. `cameras` (direct mode): list from parse_camera_file."""
    url = url_from_ref(ref)
    if not url:
        return None
    if cameras:
        for cam in cameras:
            if tcp_url(cam["rtsp"]) == url or cam["rtsp"] == url:
                return cam["name"]
        return None
    m = re.match(r"^rtspt?://[^/]+/([A-Za-z0-9_.-]+)$", url)
    return m.group(1) if m else None


def tcp_url(url):
    """rtsp:// -> rtspt:// (RTSP over TCP; UDP often fails between networks)."""
    return "rtspt://" + url[len("rtsp://"):] if url.startswith("rtsp://") else url


def parse_camera_file(text):
    """Direct mode (no go2rtc). One camera per line:  name | rtsp-url | snapshot-url (optional).  # = comment."""
    cams = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[1].startswith(("rtsp://", "rtsps://", "rtspt://", "http://", "https://")):
            continue
        name = slug(parts[0])
        if not name or any(c["name"] == name for c in cams):
            continue
        snap = parts[2] if len(parts) > 2 and parts[2].startswith(("http://", "https://")) else None
        cams.append({"name": name, "title": parts[0], "rtsp": parts[1], "snapshot": snap})
    return cams


def split_credentials(url):
    """'http://user:pw@host/x' -> ('http://host/x', 'user', 'pw'); without credentials user/pw are None."""
    p = urlsplit(url)
    if p.username is None:
        return url, None, None
    host = p.hostname + (":%d" % p.port if p.port else "")
    clean = "%s://%s%s%s" % (p.scheme, host, p.path, ("?" + p.query) if p.query else "")
    return clean, unquote(p.username), unquote(p.password or "")


def bouquet_text(title, server, streams, port=8554, cameras=None, titles=None):
    """Channel list. go2rtc mode: `streams` names via `server` (names from `titles`); direct mode: `cameras`."""
    lines = ["#NAME %s" % title]
    entries = [(c["title"], tcp_url(c["rtsp"])) for c in cameras] if cameras else \
        [((titles or {}).get(s) or display_name(s), rtsp_url(server, s, port)) for s in streams]
    for i, (name, url) in enumerate(entries, 1):
        lines.append("#SERVICE " + service_ref(url, name, i))
        lines.append("#DESCRIPTION " + name)
    return "\n".join(lines) + "\n"


def add_to_bouquets(bouquets_tv, filename=BOUQUET_FILE):
    """Returns bouquets.tv text with our bouquet appended (unchanged if already present)."""
    if filename in bouquets_tv:
        return bouquets_tv
    line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
    text = bouquets_tv if bouquets_tv.endswith("\n") or not bouquets_tv else bouquets_tv + "\n"
    return text + line + "\n"


def clamp_seconds(value, default=30):
    try:
        s = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_SECONDS, min(MAX_SECONDS, s))


def pick_mode(value, default="photo"):
    return value if value in MODES else default


def decide(in_standby, current_stream, window_stream, requested_stream):
    """What to do for a request: 'ignore', 'extend' or 'show'."""
    if in_standby or not requested_stream:
        return "ignore"
    if current_stream == requested_stream:  # already watching this camera
        return "ignore"
    if window_stream == requested_stream:
        return "extend"
    return "show"


TITLE_SIZES = {"small": (32, 22), "normal": (40, 26), "large": (56, 38)}  # (title bar height, font) at 1080p


def title_font(title_size, screen_w):
    return int(TITLE_SIZES.get(title_size, TITLE_SIZES["normal"])[1] * screen_w / 1920.0)


def window_geometry(position, size, screen_w, screen_h, title_size="normal"):
    """(x, y, w, h, title_h) for the photo window, scaled from a 1920x1080 design."""
    f = screen_w / 1920.0
    w, h = SIZES.get(size, SIZES["medium"])
    w, h = int(w * f), int(h * f)
    title, margin = int(TITLE_SIZES.get(title_size, TITLE_SIZES["normal"])[0] * f), int(40 * f)
    total_h = h + title
    x = margin if position in ("top_left", "bottom_left") else screen_w - w - margin
    y = margin if position in ("top_left", "top_right") else screen_h - total_h - margin
    return x, y, w, h, title


def client_allowed(ip, allow="lan"):
    """'lan' allows private, loopback and link-local addresses only; 'any' allows everything."""
    if allow == "any":
        return True
    try:
        a = ipaddress.ip_address((ip or "").replace("::ffff:", ""))
    except ValueError:
        return False
    return a.is_private or a.is_loopback or a.is_link_local


def token_ok(expected, given):
    import hmac
    if not expected:
        return True
    return bool(given) and hmac.compare_digest(str(expected), str(given))


def should_pause(enabled, mode, watching_camera):
    """Pause (timeshift) the TV only for photo window / notification while watching a normal channel."""
    return bool(enabled) and mode in ("photo", "notify") and not watching_camera


def in_time_window(now, start, end):
    """now/start/end as (hour, minute). The window may pass midnight (22:00-06:00). start == end means all day."""
    n, a, b = now[0] * 60 + now[1], start[0] * 60 + start[1], end[0] * 60 + end[1]
    if a == b:
        return True
    return a <= n < b if a < b else n >= a or n < b


def lowered_volume(current, percent):
    """Volume while the live camera is shown: percent of the current volume (100 = unchanged)."""
    return max(0, min(100, int(round(current * max(0, min(100, int(percent))) / 100.0))))


def parse_cams(value):
    """'front_door, garden' -> ['front_door', 'garden'] (max 9, duplicates removed)."""
    out = []
    for c in re.split(r"[,\s]+", value or ""):
        if re.match(r"^[A-Za-z0-9_.-]+$", c) and c not in out:
            out.append(c)
    return out[:9]


def grid(n, screen_w, screen_h, gap=8):
    """Tiles (x, y, w, h) for n cameras in a 1x1, 2x2 or 3x3 grid with 16:9 tiles, centred on the screen."""
    cols = 1 if n <= 1 else 2 if n <= 4 else 3
    rows = (n + cols - 1) // cols
    w = (screen_w - gap * (cols + 1)) // cols
    h = w * 9 // 16
    if h * rows + gap * (rows + 1) > screen_h:
        h = (screen_h - gap * (rows + 1)) // rows
        w = h * 16 // 9
    x0 = (screen_w - (w * cols + gap * (cols - 1))) // 2
    y0 = (screen_h - (h * rows + gap * (rows - 1))) // 2
    return [(x0 + (i % cols) * (w + gap), y0 + (i // cols) * (h + gap), w, h) for i in range(n)]


# --- MQTT 3.1.1 (minimal, QoS 0 only) ------------------------------------------------------------------------
def _mqtt_len(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _mqtt_str(s):
    b = s.encode("utf-8") if isinstance(s, str) else s
    return len(b).to_bytes(2, "big") + b


def mqtt_connect(client_id, user=None, password=None, will_topic=None, will_payload=b"offline", keepalive=60):
    flags = 0x02  # clean session
    payload = _mqtt_str(client_id)
    if will_topic:
        flags |= 0x04 | 0x20  # will flag, will retain (QoS 0)
        payload += _mqtt_str(will_topic) + _mqtt_str(will_payload)
    if user:
        flags |= 0x80
        payload += _mqtt_str(user)
        if password:
            flags |= 0x40
            payload += _mqtt_str(password)
    var = _mqtt_str("MQTT") + bytes([4, flags]) + keepalive.to_bytes(2, "big")
    body = var + payload
    return bytes([0x10]) + _mqtt_len(len(body)) + body


def mqtt_publish(topic, payload, retain=False):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    body = _mqtt_str(topic) + payload
    return bytes([0x30 | (1 if retain else 0)]) + _mqtt_len(len(body)) + body


def mqtt_subscribe(packet_id, topics):
    body = packet_id.to_bytes(2, "big") + b"".join(_mqtt_str(t) + b"\x00" for t in topics)
    return bytes([0x82]) + _mqtt_len(len(body)) + body


MQTT_PING = b"\xc0\x00"
MQTT_DISCONNECT = b"\xe0\x00"


def mqtt_split(buffer):
    """Splits a byte buffer into complete packets: returns ([(type, flags, body)], rest)."""
    packets, i = [], 0
    while True:
        if len(buffer) - i < 2:
            break
        mult, length, j = 1, 0, i + 1
        while True:
            if j >= len(buffer):
                return packets, buffer[i:]
            b = buffer[j]
            length += (b & 0x7F) * mult
            mult *= 128
            j += 1
            if not b & 0x80:
                break
        if len(buffer) - j < length:
            break
        packets.append((buffer[i] >> 4, buffer[i] & 0x0F, buffer[j:j + length]))
        i = j + length
    return packets, buffer[i:]


def mqtt_parse_publish(flags, body):
    """(topic, payload) of an incoming PUBLISH packet."""
    n = int.from_bytes(body[:2], "big")
    topic = body[2:2 + n].decode("utf-8", "replace")
    rest = body[2 + n:]
    if (flags >> 1) & 0x03:  # QoS > 0 has a packet id
        rest = rest[2:]
    return topic, rest


def mqtt_command(payload):
    """Payload of a show command: 'front_door' or JSON {"cam": ..., "sec": ..., "mode": ...}."""
    text = payload.decode("utf-8", "replace").strip() if isinstance(payload, bytes) else str(payload).strip()
    if text.startswith("{"):
        try:
            d = json.loads(text)
        except ValueError:
            return {}
        return {k: d[k] for k in ("cam", "sec", "mode", "priority", "label") if k in d}
    return {"cam": text} if text else {}


def discovery(node, name, cameras, prefix="camalert", base="homeassistant"):
    """Home Assistant MQTT discovery messages: [(topic, json payload)]. cameras: [(name, title)]."""
    avail = "%s/%s/availability" % (prefix, node)
    device = {"identifiers": ["camalert_%s" % node], "name": name, "manufacturer": "CamAlert", "model": "Enigma2 receiver"}
    msgs = []

    def add(kind, oid, conf):
        conf.update({"unique_id": "camalert_%s_%s" % (node, oid), "object_id": "camalert_%s_%s" % (node, oid),
                     "availability_topic": avail, "device": device})
        msgs.append(("%s/%s/camalert_%s/%s/config" % (base, kind, node, oid), json.dumps(conf, sort_keys=True)))

    for cam, title in cameras:
        add("button", "show_" + cam, {"name": "Show %s" % title, "icon": "mdi:cctv",
                                      "command_topic": "%s/%s/show" % (prefix, node), "payload_press": cam})
    add("button", "mosaic", {"name": "Mosaic", "icon": "mdi:view-grid", "command_topic": "%s/%s/mosaic" % (prefix, node),
                             "payload_press": ""})
    add("button", "hide", {"name": "Hide camera", "icon": "mdi:close-box", "command_topic": "%s/%s/hide" % (prefix, node),
                           "payload_press": ""})
    add("sensor", "on_screen", {"name": "Camera on screen", "icon": "mdi:television",
                                "state_topic": "%s/%s/state" % (prefix, node)})
    add("switch", "dnd", {"name": "Do not disturb", "icon": "mdi:bell-off",
                          "command_topic": "%s/%s/dnd/set" % (prefix, node), "state_topic": "%s/%s/dnd" % (prefix, node),
                          "payload_on": "ON", "payload_off": "OFF"})
    add("event", "button", {"name": "Remote button", "icon": "mdi:remote", "state_topic": "%s/%s/button" % (prefix, node),
                            "event_types": ["red", "green", "yellow", "blue"]})
    return msgs


PRIORITIES = ("normal", "high", "alarm")


def pick_priority(value):
    return value if value in PRIORITIES else "normal"


def blocked_by_rules(priority, limit_hours, in_hours, skip_recording, recording, skip_media=False, playing_media=False):
    """Receiver rules (active hours, not while recording, not while playing a recording/media file) only apply
    to normal priority."""
    if priority != "normal":
        return False
    return bool((limit_hours and not in_hours) or (skip_recording and recording) or (skip_media and playing_media))


DND_LEVELS = ("normal", "high")


def dnd_blocks(priority, dnd_on, level="normal"):
    """Do not disturb: blocks normal priority; with level 'high' also high priority. Alarm always passes."""
    if not dnd_on or priority == "alarm":
        return False
    return priority == "normal" or (level == "high" and priority == "high")


def is_media_ref(ref):
    """True for a service reference that plays a file (recording, video on the NAS), not a TV channel or stream."""
    parts = (ref or "").split(":")
    if len(parts) < 11:
        return False
    return ":".join(parts[10:]).startswith("/")


def neighbour(items, current, step):
    """Next/previous item in a list (wraps around); first item if current is unknown."""
    if not items:
        return None
    if current not in items:
        return items[0]
    return items[(items.index(current) + step) % len(items)]


def known_camera(name, names):
    """False only if we know the camera list and the name is not in it (an empty list = unknown, allow)."""
    return bool(name) and (not names or name in names)


KEY_OK, KEY_EXIT, KEY_LEFT, KEY_RIGHT = 352, 174, 105, 106
PASS_KEYS = {113, 114, 115}  # mute, volume down, volume up: leave the window open


def key_action(code):
    """What a remote key does while the photo window is open: live / prev / next / close / pass / close_pass."""
    if code == KEY_OK:
        return "live"
    if code == KEY_LEFT:
        return "prev"
    if code == KEY_RIGHT:
        return "next"
    if code == KEY_EXIT:
        return "close"
    if code in PASS_KEYS:
        return "pass"
    return "close_pass"  # close the window and let the key do its normal job (zapping, numbers, menu, ...)


def clock_tuple(value):
    """(hour, minute) from a ConfigClock value: [h, m], (h, m), 'HH:MM' or seconds since midnight."""
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return int(value[0]) % 24, int(value[1]) % 60
    if isinstance(value, str) and ":" in value:
        h, m = value.strip().split(":")[:2]
        return int(h) % 24, int(m) % 60
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0, 0
    return (n // 3600) % 24, (n // 60) % 60


def valid_port(value, default):
    """Port number 1..65535, otherwise the default (ports are free number fields in the settings)."""
    try:
        p = int(value)
    except (TypeError, ValueError):
        return default
    return p if 1 <= p <= 65535 else default


# --- camera names (go2rtc mode) -------------------------------------------------------------------------------
def parse_titles(text):
    """'front_door=Front door|garden=Garden' -> {'front_door': 'Front door', 'garden': 'Garden'}."""
    out = {}
    for part in (text or "").split("|"):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if re.match(r"^[A-Za-z0-9_.-]+$", k) and v:
                out[k] = v
    return out


def format_titles(titles):
    """Inverse of parse_titles; empty names are dropped, '|' and newlines are removed from names."""
    items = []
    for k in sorted(titles):
        v = re.sub(r"[|\r\n]", " ", titles[k] or "").strip()
        if v:
            items.append("%s=%s" % (k, v))
    return "|".join(items)


def title_for(name, titles):
    return (titles or {}).get(name) or display_name(name)


# --- automatic camera list ------------------------------------------------------------------------------------
def place_in_bouquets(bouquets_tv, filename=BOUQUET_FILE, position="bottom"):
    """bouquets.tv with our bouquet at the top (first bouquet) or bottom; every other line is kept as it is.
    position "keep": leave it where the user put it; only add it (at the bottom) when it is missing."""
    line = '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % filename
    if position == "keep" and ('"%s"' % filename) in bouquets_tv:
        return bouquets_tv if bouquets_tv.endswith("\n") else bouquets_tv + "\n"
    lines = [l for l in bouquets_tv.splitlines() if ('"%s"' % filename) not in l]
    if position == "top":
        at = 1 if lines and lines[0].startswith("#NAME") else 0
        lines.insert(at, line)
    else:
        lines.append(line)
    return "\n".join(lines) + "\n"


# --- per-camera settings (orientation, refresh interval, Frigate mapping) -------------------------------------
ORIENTATIONS = ("mirror", "flip", "rot180")


def parse_map(text):
    """'cam=value|cam2=value2' -> {'cam': 'value', ...} (generic form of parse_titles)."""
    return parse_titles(text)


def format_map(values):
    return format_titles(values)


def parse_orientation(text):
    """'garden=rot180|drive=mirror' -> {'garden': 'rot180', 'drive': 'mirror'}; unknown values are dropped."""
    return {k: v.lower() for k, v in parse_map(text).items() if v.lower() in ORIENTATIONS}


def parse_refresh(text):
    """'garden=5|drive=2.5' -> seconds between snapshots per camera (0.5..300); invalid values are dropped."""
    out = {}
    for k, v in parse_map(text).items():
        try:
            f = float(v.replace(",", "."))
        except ValueError:
            continue
        if f > 0:
            out[k] = max(0.5, min(300.0, f))
    return out


def refresh_delay(name, refresh, minimum=0.2):
    """Pause before the next snapshot of a camera: its own interval, or as fast as possible."""
    return max(minimum, (refresh or {}).get(name, 0))


# --- Frigate (motion/object detection without Home Assistant) -------------------------------------------------
def frigate_event(payload):
    """Parses a message from <prefix>/events. Returns {'type', 'camera', 'label', 'id', 'snapshot'} for a new or
    updated detection, None for anything else (end events, false positives, broken JSON)."""
    try:
        d = json.loads(payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict) or d.get("type") not in ("new", "update"):
        return None
    after = d.get("after") or {}
    if not isinstance(after, dict) or after.get("false_positive") or not after.get("camera"):
        return None
    sub = after.get("sub_label")
    if isinstance(sub, (list, tuple)):  # Frigate 0.13+: [name, score]
        sub = sub[0] if sub else None
    return {"type": d["type"], "camera": str(after["camera"]), "label": str(after.get("label") or ""),
            "sub_label": str(sub or ""), "id": str(after.get("id") or ""), "snapshot": bool(after.get("has_snapshot")),
            "clip": bool(after.get("has_clip"))}


def frigate_title(event):
    """Who/what for the window title: the sub label (a recognised face or plate) if any, else the label."""
    if not event:
        return None
    return event.get("sub_label") or (event.get("label") or "").replace("_", " ").capitalize() or None


def frigate_stream(event, labels="", camera_map=""):
    """Stream to show for a Frigate event, or None. labels: 'person,car' (empty = all);
    camera_map: 'frigate_name=go2rtc_name|...' (default: same name)."""
    if not event:
        return None
    wanted = [x.strip().lower() for x in (labels or "").split(",") if x.strip()]
    if wanted and event["label"].lower() not in wanted:
        return None
    stream = parse_map(camera_map).get(event["camera"], event["camera"])
    return stream if re.match(r"^[A-Za-z0-9_.-]+$", stream) else None


# --- several cameras in one corner window ----------------------------------------------------------------------
STRIP_LAYOUTS = ("auto", "vertical", "horizontal", "grid")


def strip_layout(n, layout="auto"):
    if layout in ("vertical", "horizontal", "grid"):
        return layout
    return "grid" if n >= 4 else "vertical"


def strip_geometry(n, layout, position, size, screen_w, screen_h):
    """One corner window with n (2..4) cameras. Returns (x, y, w, h, title_h, tiles) where tiles are (x, y, w, h)
    relative to the window. Tiles use the photo window size and shrink to fit at most 90% of the screen."""
    n = max(1, min(4, n))
    lay = strip_layout(n, layout)
    cols, rows = {"vertical": (1, n), "horizontal": (n, 1), "grid": (2, (n + 1) // 2)}[lay]
    f = screen_w / 1920.0
    tw, th = SIZES.get(size, SIZES["medium"])
    tw, th = int(tw * f), int(th * f)
    gap, title, margin = max(2, int(6 * f)), int(40 * f), int(40 * f)
    max_w, max_h = int(screen_w * 0.9) - margin, int(screen_h * 0.9) - margin
    scale = min(1.0, (max_w - gap * (cols - 1)) / float(tw * cols), (max_h - title - gap * (rows - 1)) / float(th * rows))
    tw, th = int(tw * scale), int(th * scale)
    w, h = tw * cols + gap * (cols - 1), th * rows + gap * (rows - 1)
    x = margin if position in ("top_left", "bottom_left") else screen_w - w - margin
    y = margin if position in ("top_left", "top_right") else screen_h - h - title - margin
    tiles = [((i % cols) * (tw + gap), title + (i // cols) * (th + gap), tw, th) for i in range(n)]
    return x, y, w, h, title, tiles


# --- camera devices (Foscam alarm polling, PTZ via ONVIF or Foscam CGI) -----------------------------------------
# Credentials live only in a local file on the receiver (DEVICES_FILE), never in the settings or in logs.
DEVICES_FILE = "/etc/enigma2/camalert_devices.conf"
DEVICE_TYPES = ("foscam", "onvif")
PTZ_ACTIONS = ("up", "down", "left", "right", "zoom_in", "zoom_out", "home", "stop")
KEY_UP, KEY_DOWN, KEY_YELLOW, KEY_CHANNELUP, KEY_CHANNELDOWN = 103, 108, 400, 402, 403


def parse_devices(text):
    """Lines 'name|type|host:port|user|password' (# = comment) -> {name: {type, host, port, user, password}}.
    The password is the rest of the line, so it may contain '|'. Unknown types and broken lines are skipped."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 4)
        if len(parts) < 3:
            continue
        name, kind, addr = parts[0].strip(), parts[1].strip().lower(), parts[2].strip()
        if not name or kind not in DEVICE_TYPES or not addr:
            continue
        host, _sep, port = addr.rpartition(":") if addr.count(":") == 1 else (addr, "", "")
        default = 88 if kind == "foscam" else 80
        out[name] = {"type": kind, "host": host, "port": valid_port(port, default) if port else default,
                     "user": parts[3].strip() if len(parts) > 3 else "",
                     "password": parts[4] if len(parts) > 4 else ""}
    return out


def device_base(dev):
    return "http://%s:%d" % (dev["host"], dev["port"])


def foscam_url(dev, cmd, **params):
    """CGI url of a Foscam camera (HD models: cgi-bin/CGIProxy.fcgi)."""
    q = [("cmd", cmd)] + sorted(params.items()) + [("usr", dev.get("user", "")), ("pwd", dev.get("password", ""))]
    return "%s/cgi-bin/CGIProxy.fcgi?%s" % (device_base(dev), "&".join("%s=%s" % (k, quote(str(v), safe="")) for k, v in q))


def foscam_values(xml):
    """<CGI_Result><result>0</result><motionDetectAlarm>2</motionDetectAlarm>...</CGI_Result> -> {tag: text}."""
    return dict(re.findall(r"<(\w+)>([^<]*)</\1>", xml or ""))


def foscam_alarm(xml):
    """True if a getDevState answer reports an active motion or sound alarm (value 2; 0 = off, 1 = no alarm)."""
    v = foscam_values(xml)
    if v.get("result", "0") != "0":
        return False
    return any(v.get(k) == "2" for k in ("motionDetectAlarm", "soundAlarm", "humanDetectAlarmState"))


def alarm_edge(previous, now):
    """Show the camera only when an alarm starts, not on every poll while it lasts."""
    return bool(now) and not previous


FOSCAM_PTZ = {"up": "ptzMoveUp", "down": "ptzMoveDown", "left": "ptzMoveLeft", "right": "ptzMoveRight",
              "zoom_in": "zoomIn", "zoom_out": "zoomOut", "home": "ptzReset"}


def foscam_ptz(action):
    """(start command, stop command or None) for a PTZ action on a Foscam camera."""
    if action in ("zoom_in", "zoom_out"):
        return FOSCAM_PTZ[action], "zoomStop"
    if action == "home":
        return "ptzReset", None
    if action == "stop":
        return "ptzStopRun", None
    return FOSCAM_PTZ[action], "ptzStopRun"


PTZ_VECTORS = {"up": (0, 0.5, 0), "down": (0, -0.5, 0), "left": (-0.5, 0, 0), "right": (0.5, 0, 0),
               "zoom_in": (0, 0, 0.5), "zoom_out": (0, 0, -0.5)}


def ptz_key(code):
    """What a remote key does in PTZ mode: up/down/left/right/zoom_in/zoom_out/home/leave, None = let it pass."""
    return {KEY_UP: "up", KEY_DOWN: "down", KEY_LEFT: "left", KEY_RIGHT: "right", KEY_CHANNELUP: "zoom_in",
            KEY_CHANNELDOWN: "zoom_out", KEY_OK: "home", KEY_EXIT: "leave", KEY_YELLOW: "leave"}.get(code)


# ONVIF (SOAP 1.2) -------------------------------------------------------------------------------------------------
ONVIF_NS = ('xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
            'xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl" '
            'xmlns:tt="http://www.onvif.org/ver10/schema"')


def wsse_digest(password, nonce, created):
    """WS-Security UsernameToken PasswordDigest: Base64(SHA1(nonce + created + password)); nonce = raw bytes."""
    import base64
    import hashlib
    return base64.b64encode(hashlib.sha1(nonce + created.encode("utf-8") + password.encode("utf-8")).digest()).decode("ascii")


def onvif_created(timestamp):
    """Unix time -> '2026-11-23T20:15:00Z' (UTC, as ONVIF wants it)."""
    import time as _t
    return _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(int(timestamp)))


def _xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def onvif_envelope(body, user=None, password="", nonce=None, created=None):
    """SOAP envelope; with a user a WS-Security UsernameToken (digest) header is added."""
    header = ""
    if user:
        import base64
        header = ('<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/'
                  'oasis-200401-wss-wssecurity-secext-1.0.xsd"><UsernameToken><Username>%s</Username>'
                  '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0'
                  '#PasswordDigest">%s</Password><Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
                  'oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</Nonce><Created xmlns="http://docs.'
                  'oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">%s</Created>'
                  '</UsernameToken></Security></s:Header>'
                  % (_xml(user), wsse_digest(password, nonce, created), base64.b64encode(nonce).decode("ascii"), created))
    return '<?xml version="1.0" encoding="UTF-8"?><s:Envelope %s>%s<s:Body>%s</s:Body></s:Envelope>' % (ONVIF_NS, header, body)


def onvif_body(action, token=None, vector=None):
    """SOAP body for: GetSystemDateAndTime, GetCapabilities, GetProfiles, ContinuousMove, Stop, GotoHomePosition."""
    if action == "GetSystemDateAndTime":
        return "<tds:GetSystemDateAndTime/>"
    if action == "GetCapabilities":
        return "<tds:GetCapabilities><tds:Category>All</tds:Category></tds:GetCapabilities>"
    if action == "GetProfiles":
        return "<trt:GetProfiles/>"
    tok = "<tptz:ProfileToken>%s</tptz:ProfileToken>" % _xml(token)
    if action == "ContinuousMove":
        x, y, z = vector
        return ('<tptz:ContinuousMove>%s<tptz:Velocity><tt:PanTilt x="%g" y="%g"/><tt:Zoom x="%g"/></tptz:Velocity>'
                '</tptz:ContinuousMove>' % (tok, x, y, z))
    if action == "Stop":
        return "<tptz:Stop>%s<tptz:PanTilt>true</tptz:PanTilt><tptz:Zoom>true</tptz:Zoom></tptz:Stop>" % tok
    if action == "GotoHomePosition":
        return "<tptz:GotoHomePosition>%s</tptz:GotoHomePosition>" % tok
    raise ValueError(action)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def onvif_xaddrs(xml):
    """GetCapabilities answer -> {"media": url, "ptz": url} (only what the camera offers)."""
    import xml.etree.ElementTree as ET
    out = {}
    for el in ET.fromstring(xml).iter():
        name = _local(el.tag).lower()
        if name in ("media", "ptz") and name not in out:
            for child in el:
                if _local(child.tag) == "XAddr" and child.text:
                    out[name] = child.text.strip()
    return out


def onvif_profile_token(xml):
    """First media profile token from GetProfiles (preferably one with a PTZ configuration)."""
    import xml.etree.ElementTree as ET
    first = None
    for el in ET.fromstring(xml).iter():
        if _local(el.tag) == "Profiles" and el.get("token"):
            first = first or el.get("token")
            if any(_local(c.tag) == "PTZConfiguration" for c in el):
                return el.get("token")
    return first


def onvif_time(xml):
    """GetSystemDateAndTime answer -> UTC unix time of the camera (None if missing); used to correct the clock."""
    import calendar
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for el in root.iter():
        if _local(el.tag) == "UTCDateTime":
            v = {}
            for part in el.iter():
                if _local(part.tag) in ("Year", "Month", "Day", "Hour", "Minute", "Second") and part.text:
                    v[_local(part.tag)] = int(part.text)
            if len(v) == 6:
                return calendar.timegm((v["Year"], v["Month"], v["Day"], v["Hour"], v["Minute"], v["Second"], 0, 0, 0))
    return None


def onvif_fault(xml):
    """Fault reason text of a SOAP answer, or None."""
    m = re.search(r"<(?:\w+:)?Text[^>]*>([^<]*)</(?:\w+:)?Text>", xml or "") if "Fault" in (xml or "") else None
    return (m.group(1) if m else "SOAP fault") if xml and "Fault>" in xml else None


# --- logging ------------------------------------------------------------------------------------------------------
LOG_LEVELS = ("off", "errors", "normal", "verbose")
_LEVEL_RANK = {"error": 1, "normal": 2, "verbose": 3}
LOG_MAX_BYTES = 1024 * 1024


def log_allowed(setting, level):
    """Does a message of `level` (error/normal/verbose) go to the log with the setting off/errors/normal/verbose?"""
    limit = LOG_LEVELS.index(setting) if setting in LOG_LEVELS else 2
    return _LEVEL_RANK.get(level, 2) <= limit


_REDACT = [
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@]*:[^/\s@]*@"), r"\1***:***@"),  # user:pass@ in urls
    (re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://)[^/\s:@]+@"), r"\1***@"),               # user@ (token as user)
    (re.compile(r"(?i)([?&](?:token|pwd|pass|password|passwd|usr|user|key|apikey|api_key|access_token|auth)=)[^&\s\"']*"),
     r"\1***"),
    (re.compile(r"(?i)(\bauthorization\s*[:=]\s*)(?:bearer\s+|basic\s+)?[^\s,;\"']+"), r"\1***"),
    (re.compile(r"(?i)(\"(?:token|password|pwd|access_token|api_key)\"\s*:\s*\")[^\"]*(\")"), r"\1***\2"),
    (re.compile(r"(?i)(<(?:\w+:)?(?:Password|Nonce|Username)[^>]*>)[^<]*"), r"\1***"),
    (re.compile(r"(?i)\b((?:password|passwd|token|pwd)\s*[=:]\s*)[^\s&,;|\"']+"), r"\1***"),
]


def redact(text):
    """Removes passwords, tokens and user:pass@ from anything that goes to a log, a status page or diagnostics."""
    text = "" if text is None else str(text)
    for rx, repl in _REDACT:
        text = rx.sub(repl, text)
    return text


SYSLOG_SEVERITY = {"error": 3, "normal": 6, "verbose": 7}


def syslog_line(message, level, hostname, timestamp, app="camalert", facility=16):
    """RFC 5424 line (local0 by default) for a remote syslog (Loki/Alloy, rsyslog, ...)."""
    import time as _t
    pri = facility * 8 + SYSLOG_SEVERITY.get(level, 6)
    ts = _t.strftime("%Y-%m-%dT%H:%M:%S", _t.gmtime(timestamp)) + ".%03dZ" % (int(timestamp * 1000) % 1000)
    host = re.sub(r"[^\x21-\x7e]", "_", hostname or "-")[:255] or "-"
    return "<%d>1 %s %s %s - - - %s" % (pri, ts, host, app, redact(message).replace("\n", " "))


def parse_hostport(text, default_port=514):
    """'host:port' or 'host' -> (host, port) or None."""
    text = (text or "").strip()
    if not text:
        return None
    host, sep, port = text.rpartition(":")
    if not sep or not port.isdigit():
        return text, default_port
    return host, valid_port(port, default_port)


# --- event list ---------------------------------------------------------------------------------------------------
EVENT_LIMIT = 20
SOURCES = ("api", "ha", "mqtt", "frigate", "foscam", "menu")


def add_event(events, event, limit=EVENT_LIMIT):
    """Newest first, at most `limit`; returns the events that fell off (their snapshots can be removed)."""
    events.insert(0, event)
    dropped = events[limit:]
    del events[limit:]
    return dropped


def caller_source(user_agent, path=""):
    """Who called the API: 'ha' for Home Assistant (integration / rest_command use aiohttp), else 'api'."""
    ua = (user_agent or "").lower()
    return "ha" if "homeassistant" in ua or "home assistant" in ua or "aiohttp" in ua else "api"


def event_title(title, label=None):
    """'Person at Front door' style title (label translated by the caller)."""
    return "%s · %s" % (label, title) if label else title


# --- colour buttons -> Home Assistant -----------------------------------------------------------------------------
COLOR_KEYS = {398: "red", 399: "green", 400: "yellow", 401: "blue"}
PTZ_TOGGLE_KEYS = ("blue", "yellow", "red", "green", "off")


def button_for(code, ptz_toggle="blue", has_ptz=False, enabled=True):
    """('ptz' | colour name | None) for a key while a camera is on screen. The PTZ toggle key only counts as PTZ
    for cameras that have PTZ; for all other cameras every colour key goes to Home Assistant."""
    colour = COLOR_KEYS.get(code)
    if colour is None:
        return None
    if has_ptz and colour == ptz_toggle:
        return "ptz"
    return colour if enabled else None


def button_event(node, camera, button):
    """Payload for camalert/<id>/button (MQTT event entity) and the Home Assistant webhook."""
    return json.dumps({"event_type": button, "button": button, "camera": camera or "", "receiver": node},
                      sort_keys=True)


# --- diagnostics / event list -------------------------------------------------------------------------------------
def diag_line(ok, text):
    """One line of the diagnostics screen: ok True / False / None (= note)."""
    return "%s  %s" % ({True: "[ OK ]", False: "[FAIL]", None: "[ -- ]"}[ok], redact(text))


def event_line(e):
    import time as _t
    who = (" · " + e["label"]) if e.get("label") else ""
    return "%s  %s%s  (%s, %s) -> %s" % (_t.strftime("%H:%M:%S", _t.localtime(e["time"])), e["camera"], who,
                                          e["source"], e["priority"], e["action"])


def frigate_clip_url(frigate_url, event_id):
    """Frigate API url of an event clip, or None."""
    base = (frigate_url or "").strip().rstrip("/")
    if not base or not event_id or not re.match(r"^[\w.-]+$", event_id):
        return None
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return "%s/api/events/%s/clip.mp4" % (base, event_id)


# --- update check -------------------------------------------------------------------------------------------------
UPDATE_INTERVAL = 24 * 3600


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", (v or "").lstrip("vV"))[:4]) or (0,)


def newer_version(current, latest):
    """The latest release tag if it is newer than the installed version, else None."""
    return latest.lstrip("vV") if latest and version_tuple(latest) > version_tuple(current) else None


def github_repo(control_text):
    """'owner/camalert' from the Homepage line of the installed package's opkg control file."""
    m = re.search(r"^Homepage:\s*https://github\.com/([\w.-]+/[\w.-]+?)/?\s*$", control_text or "", re.M)
    return m.group(1) if m else None


def latest_tag(release_json):
    try:
        d = json.loads(release_json)
    except (ValueError, TypeError):
        return None
    return d.get("tag_name") if isinstance(d, dict) and not d.get("draft") and not d.get("prerelease") else None


# --- picons for the camera channels -------------------------------------------------------------------------------
def picon_name(title):
    """Service-name picon file name (as Enigma2 looks it up for stream services): 'Grüner Weg' ->
    'grunerweg.png'."""
    import unicodedata
    name = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9]", "", name.replace("&", "and").replace("+", "plus").replace("*", "star").lower())
    return (name + ".png") if name else None


def chime_command(path, sink="alsasink"):
    """gstreamer command for the doorbell chime; ALSA plays next to the TV sound (dvbaudiosink) on Vu+ boxes."""
    return ["gst-launch-1.0", "-q", "filesrc", "location=%s" % path, "!", "wavparse", "!", "audioconvert", "!",
            "audioresample", "!", sink]
