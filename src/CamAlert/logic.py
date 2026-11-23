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


def window_geometry(position, size, screen_w, screen_h):
    """(x, y, w, h, title_h) for the photo window, scaled from a 1920x1080 design."""
    f = screen_w / 1920.0
    w, h = SIZES.get(size, SIZES["medium"])
    w, h = int(w * f), int(h * f)
    title, margin = int(40 * f), int(40 * f)
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
        return {k: d[k] for k in ("cam", "sec", "mode", "priority") if k in d}
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
    return msgs


PRIORITIES = ("normal", "high", "alarm")


def pick_priority(value):
    return value if value in PRIORITIES else "normal"


def blocked_by_rules(priority, limit_hours, in_hours, skip_recording, recording):
    """Receiver rules (active hours, not while recording) only apply to normal priority."""
    if priority != "normal":
        return False
    return (limit_hours and not in_hours) or (skip_recording and recording)


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
