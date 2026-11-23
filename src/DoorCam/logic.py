# -*- coding: utf-8 -*-
# DoorCam - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 DoorCam developers. Licensed under the GNU GPL v2 (see LICENSE).
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
BOUQUET_FILE = "userbouquet.doorcam.tv"


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


def bouquet_text(title, server, streams, port=8554, cameras=None):
    """Channel list. go2rtc mode: `streams` names via `server`; direct mode: `cameras` from parse_camera_file."""
    lines = ["#NAME %s" % title]
    entries = [(c["title"], tcp_url(c["rtsp"])) for c in cameras] if cameras else \
        [(display_name(s), rtsp_url(server, s, port)) for s in streams]
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
